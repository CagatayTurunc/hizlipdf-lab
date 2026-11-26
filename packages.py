"""Versioned declarative plugins. Only the two exact lab packages are accepted."""
import hashlib
import io
import json
import os
from pathlib import Path
import threading
import uuid
import zipfile

VERSION = "0.2.0"
CATALOG = {
    "hizlipdf.normal": {"name": "HızlıPDF · Normal referans", "variant": "normal"},
    "hizlipdf.education": {"name": "HızlıPDF · Eğitim eklentisi", "variant": "education"},
}


def definition(plugin_id):
    if plugin_id not in CATALOG:
        raise ValueError("Bilinmeyen laboratuvar eklentisi.")
    meta = CATALOG[plugin_id]
    manifest = {"id": plugin_id, "name": meta["name"], "version": VERSION,
                "api_version": 1, "engine": "declarative-v1", "entry": "pipeline.json"}
    steps = ["analyze_docx", "convert_pdf"]
    if meta["variant"] == "education":
        steps.append("synthetic_lab_probe")
    return manifest, {"steps": steps}


def build_package(plugin_id):
    manifest, pipeline = definition(plugin_id)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in [("manifest.json", manifest), ("pipeline.json", pipeline)]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, json.dumps(value, ensure_ascii=False, sort_keys=True).encode())
    return stream.getvalue()


def read_package(data):
    if not data or len(data) > 32768:
        raise ValueError("Eklenti paketi boş veya 32 KiB sınırını aşıyor.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(entries) != 2 or set(archive.namelist()) != {"manifest.json", "pipeline.json"}
                    or sum(e.file_size for e in entries) > 16384):
                raise ValueError("Paket yalnızca manifest.json ve pipeline.json içermelidir.")
            manifest = json.loads(archive.read("manifest.json"))
            pipeline = json.loads(archive.read("pipeline.json"))
        if not isinstance(manifest, dict):
            raise ValueError("Geçersiz manifest.")
        expected_manifest, expected_pipeline = definition(manifest.get("id"))
        if type(manifest.get("api_version")) is not int or manifest != expected_manifest or pipeline != expected_pipeline:
            raise ValueError("Paket kimliği, sürümü veya işlem planı güvenilen laboratuvar tanımıyla eşleşmiyor.")
        return {"manifest": manifest, "pipeline": pipeline, "variant": CATALOG[manifest["id"]]["variant"],
                "sha256": hashlib.sha256(data).hexdigest()}
    except (zipfile.BadZipFile, KeyError, RuntimeError, UnicodeError, TypeError) as exc:
        raise ValueError("Eklenti arşivi okunamıyor.") from exc


class PluginStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def path(self, plugin_id):
        definition(plugin_id)
        return self.folder / (plugin_id + ".zip")

    def install(self, data):
        info = read_package(data)
        with self.lock:
            target = self.path(info["manifest"]["id"])
            temporary = self.folder / (uuid.uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(data)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return info

    def resolve(self, plugin_id):
        with self.lock:
            try:
                data = self.path(plugin_id).read_bytes()
                info = read_package(data)
                if info["manifest"]["id"] != plugin_id:
                    raise ValueError("Kurulu paket kimliği eşleşmiyor.")
                return info, data
            except OSError as exc:
                raise ValueError("Eklenti kurulu değil. Önce Eklentiler ekranından kurun.") from exc

    def uninstall(self, plugin_id):
        with self.lock:
            self.path(plugin_id).unlink(missing_ok=True)

    def listing(self):
        result = []
        with self.lock:
            for plugin_id in CATALOG:
                manifest, _ = definition(plugin_id)
                row = {**manifest, "variant": CATALOG[plugin_id]["variant"], "installed": False,
                       "download_url": f"/api/plugins/{plugin_id}/package"}
                if self.path(plugin_id).exists():
                    try:
                        info, _ = self.resolve(plugin_id)
                        row.update(installed=True, sha256=info["sha256"])
                    except ValueError as exc:
                        row["error"] = str(exc)
                result.append(row)
        return result
