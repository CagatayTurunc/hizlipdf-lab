"""Separate conversion process; fixed synthetic targets, no discovery or persistence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

from fixtures import FILES
from packages import read_package
from analysis_docx import analyze_docx


def run(config):
    start = time.monotonic()

    def event(kind, result, **fields):
        print(json.dumps({"event": kind, "result": result,
                          "elapsed_ms": round((time.monotonic() - start) * 1000),
                          "evidence_source": "worker", **fields}, ensure_ascii=False), flush=True)

    def send(kind, source="", content=""):
        request = urllib.request.Request(config["receiver_url"], data=json.dumps({
            "run_id": config["run_id"], "token": config["token"],
            "kind": kind, "source": source, "content": content,
        }).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            # The receiver URL is fixed by the parent; never inherit machine proxy settings.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=1) as response:
                if response.status != 200:
                    raise ValueError("Receiver did not accept the record")
            event(kind, "acknowledged", source=source)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            # A failed connection is not automatically attributed to a policy.
            event(kind, "failed", source=source, error=type(exc).__name__, detail=str(exc)[:180])

    event("PROCESS_STARTED", "ok", uid=os.getuid() if hasattr(os, "getuid") else None,
          profile=config["profile"], sandbox=config["sandbox"])
    try:
        plugin = read_package(Path(config["package_path"]).read_bytes())
        if plugin["manifest"]["id"] != config["plugin_id"] or plugin["sha256"] != config["package_sha256"]:
            raise ValueError("Çalışma paketi kimliği veya özeti eşleşmiyor.")
        steps = plugin["pipeline"]["steps"]
        event("PLUGIN_LOADED", "ok", plugin_id=plugin["manifest"]["id"], version=plugin["manifest"]["version"],
              package_sha256=plugin["sha256"], steps=steps)
        if steps[0] != "analyze_docx":
            raise ValueError("Analiz adımı bulunamadı.")
        analysis = analyze_docx(config["input"])
        (Path(config["output"]) / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
        event("ANALYSIS_FINISHED", "ok", word_count=analysis["word_count"], table_count=analysis["table_count"])
    except (OSError, ValueError, KeyError) as exc:
        event("PLUGIN_FAILED", "failed", detail=str(exc)[:400])
        return 1
    env = {**os.environ, "HOME": config["home"], "TMPDIR": config["tmp"]}
    command = [config["soffice"], "--headless", "--nologo", "--nodefault", "--norestore",
               "-env:UserInstallation=" + Path(config["home"]).as_uri() + "/lo-profile",
               "--convert-to", "pdf:writer_pdf_Export", "--outdir", config["output"], config["input"]]
    conversion_start = time.monotonic()
    event("CONVERSION_STARTED", "running")
    try:
        proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        pdf = Path(config["output"]) / "input.pdf"
        if proc.returncode or not pdf.is_file() or pdf.stat().st_size < 100:
            raise RuntimeError((proc.stderr or proc.stdout or "PDF output is missing")[:400])
        event("CONVERSION_FINISHED", "ok", duration_ms=round((time.monotonic()-conversion_start)*1000))
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        event("CONVERSION_FINISHED", "failed", detail=str(exc)[:400])
        return 1

    if "synthetic_lab_probe" not in steps:
        event("EXTRA_ACTIONS", "not_attempted")
        return 0

    send("LAB_PING")
    for filename, expected in FILES.items():
        event("TASK_READ_ATTEMPT", "running", source=filename)
        try:
            # Fixed file names and size bound. Never follow user-supplied paths.
            with (Path(config["targets"]) / filename).open("rb") as stream:
                data = stream.read(8193)
            if data != expected.encode("utf-8"):
                event("TASK_READ", "rejected_content", source=filename)
                continue
            event("TASK_READ", "ok", source=filename, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            send("CONTENT", filename, expected)
        except (OSError, UnicodeError) as exc:
            event("TASK_READ", "failed", source=filename, error=type(exc).__name__, detail=str(exc)[:180])
    return 0


if __name__ == "__main__":
    with open(sys.argv[1]) as stream:
        config = json.load(stream)
    sys.exit(run(config))
