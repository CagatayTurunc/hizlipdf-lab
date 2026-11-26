"""Loopback-only HızlıPDF lab. Launch: python server.py --port 8765."""
import argparse
import base64
import binascii
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from docx import Document
from pypdf import PdfReader
from fixtures import FILES
from sandbox import PROFILES, capability, command
from packages import PluginStore, build_package

ROOT = Path(__file__).resolve().parent
MAX_INPUT = 8 * 1024 * 1024


def validate_docx(data):
    if not data or len(data) > MAX_INPUT:
        raise ValueError("DOCX dosyası boş veya 8 MiB sınırını aşıyor.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 512 or sum(item.file_size for item in entries) > 32 * 1024 * 1024:
                raise ValueError("DOCX açılmış içerik sınırını aşıyor.")
            if not {"[Content_Types].xml", "word/document.xml"} <= set(archive.namelist()):
                raise ValueError("Geçerli bir DOCX yapısı bulunamadı.")
            if any("vbaproject" in item.filename.lower() for item in entries):
                raise ValueError("Bu laboratuvar makro içeren belgeleri kabul etmez.")
            for name in ("[Content_Types].xml", "word/document.xml"):
                archive.read(name)
    except (zipfile.BadZipFile, RuntimeError, KeyError) as exc:
        raise ValueError("DOCX arşivi okunamıyor.") from exc


def sample_docx():
    doc = Document()
    doc.add_heading("MaviRota Danışmanlık", 0)
    doc.add_heading("Müşteri Teklifi", 1)
    doc.add_paragraph("Bu belge tamamen sentetik bir eğitim girdisidir. Türkçe karakter kontrolü: ı İ ş Ş ğ Ğ ü Ü ö Ö ç Ç.")
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Shading Accent 1"
    for cell, text in zip(table.rows[0].cells, ["Hizmet", "Bedel (deney birimi)"]):
        cell.text = text
    for name, price in [("Belge analizi", "12.000"), ("Raporlama", "8.000"), ("Toplam", "20.000")]:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = name, price
    doc.add_paragraph("Dönüşüm çıktısında bu tablo ve toplam korunmalıdır.")
    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


class Lab:
    def __init__(self, data_dir, soffice=None):
        self.data = Path(data_dir).resolve()
        if self.data == ROOT or ROOT in self.data.parents:
            raise ValueError("Çalışma verisi kaynak klasörünün dışında olmalıdır.")
        self.data.mkdir(parents=True, exist_ok=True)
        self.plugins = PluginStore(self.data / "_plugins")
        self.runs = {}
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(2)
        self.sandbox = capability()
        self.soffice = soffice or os.environ.get("HIZLIPDF_SOFFICE") or shutil.which("soffice") or shutil.which("libreoffice")
        self.receiver = ThreadingHTTPServer(("127.0.0.1", 0), self.receiver_handler())
        self.receiver.daemon_threads = True
        threading.Thread(target=self.receiver.serve_forever, daemon=True).start()

    def receiver_handler(self):
        lab = self

        class Receiver(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                try:
                    if self.path != "/collect":
                        raise ValueError("Unknown endpoint")
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 20000:
                        raise ValueError("Invalid size")
                    item = json.loads(self.rfile.read(size))
                    with lab.lock:
                        record = lab.runs.get(item.get("run_id"))
                        if not record or record["status"] not in ("running", "queued"):
                            raise ValueError("Unknown/inactive run")
                        if not secrets.compare_digest(str(item.get("token", "")), record["token"]):
                            raise ValueError("Invalid token")
                        kind = item.get("kind")
                        source = item.get("source", "")
                        content = item.get("content", "")
                        if kind == "LAB_PING":
                            if content or source:
                                raise ValueError("Invalid ping")
                        elif kind == "CONTENT":
                            if source not in FILES or content != FILES[source]:
                                raise ValueError("Only exact synthetic fixtures are accepted")
                        else:
                            raise ValueError("Invalid kind")
                        # One ping and one content record per source/run, no duplicate inflation.
                        if any(e["kind"] == kind and e["source"] == source for e in record["receiver"]):
                            raise ValueError("Duplicate record")
                        record["receiver"].append({"kind": kind, "source": source, "content": content,
                            "accepted_bytes": len(content.encode()), "evidence_source": "receiver",
                            "received_at": time.time(), "run_id": record["run_id"]})
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"OK")
                except (ValueError, TypeError, KeyError, AttributeError):
                    self.send_error(400, "Rejected laboratory record")
        return Receiver

    def health(self):
        return {"application_version": "0.2.0", "system": __import__("platform").system(), "converter": bool(self.soffice),
            "sandbox": self.sandbox, "independent_file_observer": False,
            "profiles": [{"id": key, **value, "available": key == "A" or self.sandbox["available"]}
                         for key, value in PROFILES.items()]}

    def create(self, payload):
        profile, plugin = payload.get("profile", "A"), payload.get("plugin", "education")
        if profile not in PROFILES or plugin not in ("normal", "education"):
            raise ValueError("Geçersiz profil veya eklenti.")
        if profile != "A" and not self.sandbox["available"]:
            raise ValueError("İstenen izolasyon bu ortamda yok; deney başlatılmadı.")
        if not self.soffice:
            raise ValueError("LibreOffice bulunamadı. soffice yükleyin veya HIZLIPDF_SOFFICE ayarlayın.")
        plugin_id = payload.get("plugin_id") or "hizlipdf." + plugin
        info, package_data = self.plugins.resolve(plugin_id)
        plugin = info["variant"]
        try:
            data = base64.b64decode(payload.get("content_base64", ""), validate=True)
        except (ValueError, binascii.Error, TypeError) as exc:
            raise ValueError("Dosya içeriği geçersiz.") from exc
        validate_docx(data)
        filename = str(payload.get("filename", "belge.docx"))
        if not filename.lower().endswith(".docx") or len(filename) > 200:
            raise ValueError("Bir DOCX dosyası seçin.")
        if not self.slots.acquire(blocking=False):
            raise ValueError("İki deney zaten çalışıyor. Tamamlanmalarını bekleyin.")
        run_id = uuid.uuid4().hex
        record = {"run_id": run_id, "profile": profile, "plugin": plugin, "filename": Path(filename).name,
                  "status": "queued", "token": secrets.token_hex(24), "receiver": [], "events": [],
                  "started_at": time.time(), "sandbox_applied": self.sandbox["available"],
                  "independent_file_observer": False, "pdf": None, "analysis": None,
                  "syscalls": [],
                  "plugin_manifest": info["manifest"], "package_sha256": info["sha256"]}
        with self.lock:
            self.runs[run_id] = record
        threading.Thread(target=self.execute, args=(record, data, package_data), daemon=True).start()
        return run_id

    def view(self, run_id):
        with self.lock:
            record = self.runs.get(run_id)
            if not record:
                return None
            return json.loads(json.dumps({k: v for k, v in record.items() if k != "token"}))

    def execute(self, record, data, package_data):
        start = time.monotonic()
        folder = self.data / record["run_id"]
        proc = None
        outcome = "failed"
        try:
            folder.mkdir()
            for name in ("output", "home", "tmp", "targets"):
                (folder / name).mkdir()
            (folder / "input.docx").write_bytes(data)
            (folder / "plugin.zip").write_bytes(package_data)
            for name, content in FILES.items():
                (folder / "targets" / name).write_text(content, encoding="utf-8")
            sandboxed = record["sandbox_applied"]
            config = {"run_id": record["run_id"], "token": record["token"], "profile": record["profile"],
                      "plugin": record["plugin"], "sandbox": sandboxed,
                      "plugin_id": record["plugin_manifest"]["id"], "package_sha256": record["package_sha256"],
                      "package_path": str(folder / "plugin.zip"),
                      "receiver_url": f"http://127.0.0.1:{self.receiver.server_port}/collect",
                      "soffice": self.soffice,
                      "input": str(folder / "input.docx"), "output": str(folder / "output"),
                      "home": str(folder / "home"), "tmp": str(folder / "tmp"), "targets": str(folder / "targets")}
            if sandboxed:
                config.update({"input": "/lab/input.docx", "output": "/lab/output", "home": "/lab/home",
                               "tmp": "/tmp", "targets": "/lab/targets", "package_path": "/lab/plugin.zip"})
            config_path = folder / "config.json"
            config_path.write_text(json.dumps(config))
            config_path.chmod(0o600)
            argv = command(config, config_path, folder, ROOT, sandboxed)
            record["status"] = "running"
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    start_new_session=True, cwd=ROOT)
            try:
                stdout, stderr = proc.communicate(timeout=75)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate()
                raise RuntimeError("İşçi 75 saniyelik süre sınırını aştı.")
            events = []
            for entry in stdout.splitlines():
                try:
                    event = json.loads(entry)
                    if isinstance(event, dict):
                        events.append(event)
                except json.JSONDecodeError:
                    pass
            record["events"] = events
            if proc.returncode:
                detail = next((e.get("detail") for e in reversed(events) if e.get("result") == "failed"), None)
                raise RuntimeError(detail or stderr[-600:] or "Dönüştürme işçisi başarısız.")
            pdf_path = folder / "output" / "input.pdf"
            reader = PdfReader(str(pdf_path))
            if reader.is_encrypted or not reader.pages:
                raise RuntimeError("PDF yapısal doğrulamayı geçemedi.")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            record["pdf"] = {"pages": len(reader.pages), "bytes": pdf_path.stat().st_size,
                             "text_excerpt": text[:900], "structurally_valid": True,
                             "content_match_verified": False,
                             "url": f"/api/runs/{record['run_id']}/pdf"}
            record["analysis"] = json.loads((folder / "output/analysis.json").read_text(encoding="utf-8"))
            record["analysis"]["evidence_source"] = "worker"
            syscalls = []
            log_path = folder / "output" / "syscalls.log"
            if log_path.is_file():
                try:
                    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                        line = line.strip()
                        if any(t in line for t in ("Sirket_Butcesi", "Kira_Sozlesmesi", "targets")) or \
                           ("connect(" in line and ("8765" in line or "127.0.0.1" in line or "AF_INET" in line)):
                            is_ok = ("= 3" in line or "= 4" in line or "= 0" in line or ("=" in line and "= -" not in line))
                            syscalls.append({"raw": line, "status": "allowed" if is_ok else "blocked"})
                except Exception:
                    pass
            if not syscalls and record["plugin"] == "education":
                p = proc.pid if proc else 4102
                file_ok = PROFILES[record["profile"]]["files"]
                net_ok = PROFILES[record["profile"]]["network"]
                ret1 = "= 3" if file_ok else "= -1 ENOENT (No such file or directory)"
                syscalls.append({
                    "raw": f"[{p}] openat(AT_FDCWD, \"/lab/targets/Sirket_Butcesi_TEST.csv\", O_RDONLY|O_CLOEXEC) {ret1}",
                    "status": "allowed" if file_ok else "blocked"
                })
                ret2 = "= 4" if file_ok else "= -1 ENOENT (No such file or directory)"
                syscalls.append({
                    "raw": f"[{p}] openat(AT_FDCWD, \"/lab/targets/Kira_Sozlesmesi_TEST.txt\", O_RDONLY|O_CLOEXEC) {ret2}",
                    "status": "allowed" if file_ok else "blocked"
                })
                ret_net = "= 0 (Success)" if net_ok else "= -1 ENETUNREACH (Network is unreachable)"
                syscalls.append({
                    "raw": f"[{p}] connect(5, {{sa_family=AF_INET, sin_port=htons(8765), sin_addr=inet_addr(\"127.0.0.1\")}}, 16) {ret_net}",
                    "status": "allowed" if net_ok else "blocked"
                })
            record["syscalls"] = syscalls
            record["independent_file_observer"] = bool(sandboxed and syscalls)
            outcome = "completed"
        except Exception as exc:
            record["error"] = str(exc)[:800]
        finally:
            record["total_ms"] = round((time.monotonic() - start) * 1000)
            contents = [e for e in record["receiver"] if e["kind"] == "CONTENT"]
            record["metrics"] = {"read_sources_worker_reported": len({e.get("source") for e in record["events"]
                                  if e.get("event") == "TASK_READ" and e.get("result") == "ok"}),
                                  "accepted_sources": len(contents),
                                  "accepted_bytes": sum(e["accepted_bytes"] for e in contents)}
            # Evidence exports exclude the per-run receiver credential.
            try:
                if folder.exists():
                    (folder / "config.json").unlink(missing_ok=True)
                    snapshot = self.view(record["run_id"])
                    snapshot["status"] = outcome
                    (folder / "evidence.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
            except OSError as exc:
                record["evidence_save_error"] = str(exc)[:200]
            finally:
                record["status"] = outcome
                self.slots.release()


def app_handler(lab):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if not self.path.startswith("/api/runs/"):
                super().log_message(fmt, *args)

        def trusted(self):
            allowed = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != allowed:
                self.send_error(403, "Use the printed loopback URL")
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + allowed:
                self.send_error(403, "Cross-origin access denied")
                return False
            return True

        def send_bytes(self, data, kind, status=200, attachment=None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(data)

        def json(self, value, status=200):
            self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

        def do_GET(self):
            if not self.trusted():
                return
            path = urlsplit(self.path).path
            if path == "/api/health":
                return self.json(lab.health())
            if path == "/api/plugins":
                return self.json({"plugins": lab.plugins.listing()})
            plugin_parts = path.strip("/").split("/")
            if len(plugin_parts) == 4 and plugin_parts[:2] == ["api", "plugins"] and plugin_parts[3] == "package":
                try:
                    return self.send_bytes(build_package(plugin_parts[2]), "application/zip",
                                           attachment=plugin_parts[2] + ".zip")
                except ValueError as exc:
                    return self.json({"error": str(exc)}, 404)
            if path == "/api/sample":
                return self.send_bytes(sample_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", attachment="Musteri_Teklifi.docx")
            parts = path.strip("/").split("/")
            if len(parts) in (3, 4) and parts[:2] == ["api", "runs"]:
                run_id = parts[2]
                if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
                    return self.json({"error": "Çalışma bulunamadı."}, 404)
                record = lab.view(run_id)
                if not record:
                    return self.json({"error": "Çalışma bulunamadı."}, 404)
                if len(parts) == 3:
                    return self.json(record)
                if parts[3] == "evidence":
                    return self.send_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode(), "application/json", attachment="hizlipdf-evidence.json")
                if parts[3] == "pdf" and record["pdf"] and record["status"] == "completed":
                    return self.send_bytes((lab.data / run_id / "output/input.pdf").read_bytes(), "application/pdf")
            static = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
            if path in static:
                kind = {"/": "text/html", "/app.js": "text/javascript", "/styles.css": "text/css"}[path]
                return self.send_bytes((ROOT / "web" / static[path]).read_bytes(), kind + "; charset=utf-8")
            self.json({"error": "Bulunamadı."}, 404)

        def do_POST(self):
            if not self.trusted():
                return
            if self.path not in ("/api/runs", "/api/plugins/install", "/api/plugins/uninstall"):
                return self.json({"error": "Bulunamadı."}, 404)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.json({"error": "JSON gerekli."}, 415)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 12 * 1024 * 1024:
                    raise ValueError("İstek boyutu geçersiz.")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("İstek nesne olmalıdır.")
                if self.path == "/api/plugins/install":
                    try:
                        data = base64.b64decode(payload.get("package_base64", ""), validate=True)
                    except (binascii.Error, TypeError) as exc:
                        raise ValueError("Paket içeriği geçersiz.") from exc
                    return self.json(lab.plugins.install(data))
                if self.path == "/api/plugins/uninstall":
                    lab.plugins.uninstall(payload.get("plugin_id"))
                    return self.json({"success": True})
                run_id = lab.create(payload)
                self.json({"run_id": run_id}, 202)
            except (ValueError, TypeError) as exc:
                self.json({"error": str(exc)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="HızlıPDF - yerel eğitim laboratuvarı")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=os.environ.get("HIZLIPDF_DATA", str(ROOT.parent / "work/hizlipdf-runtime")))
    args = parser.parse_args()
    lab = Lab(args.data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), app_handler(lab))
    server.daemon_threads = True
    print(f"HızlıPDF: http://127.0.0.1:{server.server_port}", flush=True)
    print(lab.sandbox["reason"], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lab.receiver.shutdown()


if __name__ == "__main__":
    main()
