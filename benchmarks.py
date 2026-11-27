"""Persistent, versioned evidence for a completed benchmark attempt."""
import json
import math
import os
import re
import statistics
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading
import time

from sandbox import PROFILES

REPETITIONS = 5
TERMINAL = ("completed", "failed")
RUN_FIELDS = (
    "run_id", "profile", "filename", "status", "started_at", "total_ms", "error",
    "system_info", "sandbox_applied", "isolation", "independent_file_observer", "input_sha256",
    "plugin_manifest", "package_sha256", "hashes", "syscalls", "receiver_health",
    "file_audit", "network_audit", "metrics", "verdict",
)
RECEIVER_FIELDS = (
    "kind", "source", "content", "accepted_bytes", "evidence_source", "received_at", "run_id",
    "http_record", "http_record_hex", "received_body_bytes",
)
PDF_FIELDS = ("pages", "bytes", "sha256", "structurally_valid", "sample_validation", "content_match_verified")
TIMING_EVENTS = ("CONVERSION_FINISHED", "LAB_PROBE_FINISHED")


def is_hex_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def measurements(values):
    valid = [n for n in values if type(n) in (int, float) and math.isfinite(n) and n >= 0]
    if not valid:
        return None
    return {"median": statistics.median(valid), "min": min(valid), "max": max(valid), "count": len(valid)}


def summarize(attempts):
    completed = [attempt["data"] for attempt in attempts
                 if attempt["round"] > 0 and attempt["data"]["status"] == "completed"
                 and (attempt["data"].get("pdf") or {}).get("structurally_valid")]
    checked = [run["pdf"]["sample_validation"] for run in completed if run["pdf"].get("sample_validation")]
    bytes_accepted = [run.get("metrics", {}).get("accepted_bytes") for run in completed
                      if run.get("receiver") or all((run.get("receiver_health") or {}).get(phase)
                                                   for phase in ("before", "after"))]

    def outcomes(field, labels):
        states = [(run.get(field) or {}).get("status") for run in completed]
        return {**{label: states.count(label) for label in labels},
                "unverified": sum(state not in labels for state in states)}

    def timing(kind):
        return measurements(next((entry.get("duration_ms") for entry in run.get("events", [])
                                  if entry["event"] == kind and entry["result"] == "ok"), None)
                            for run in completed)

    return {
        "valid_pdf": len(completed),
        "pdf_reference_checked": len(checked),
        "pdf_reference_passed": sum(check.get("passed") is True for check in checked),
        "files": outcomes("file_audit", ("opened", "unavailable")),
        "network": outcomes("network_audit", ("reachable", "unreachable")),
        "total": measurements(run.get("total_ms") for run in completed),
        "accepted": measurements(bytes_accepted),
        "conversion": timing("CONVERSION_FINISHED"),
        "extra": timing("LAB_PROBE_FINISHED"),
    }


def recorded_run(record):
    # Keep the observation and measurement data. Leave input bytes, extracted
    # document text and receiver credentials out of this export.
    snapshot = {key: record[key] for key in RUN_FIELDS if key in record}
    snapshot["receiver"] = [
        {key: entry[key] for key in RECEIVER_FIELDS if key in entry}
        for entry in record.get("receiver", [])
    ]
    pdf = record.get("pdf") or {}
    snapshot["pdf"] = {key: pdf[key] for key in PDF_FIELDS if key in pdf} if pdf else None
    snapshot["events"] = [
        {key: event[key] for key in ("event", "result", "duration_ms") if key in event}
        for event in record.get("events", []) if event.get("event") in TIMING_EVENTS
    ]
    return snapshot


class BenchmarkStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.lock = threading.Lock()

    def load(self, series_id):
        if not is_hex_id(series_id):
            return None
        try:
            bundle = json.loads((self.folder / f"{series_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(bundle, dict) or bundle.get("series_id") != series_id or bundle.get("schema_version") != 1:
            return None
        return bundle

    def list(self):
        history = []
        for path in self.folder.glob("*.json"):
            bundle = self.load(path.stem)
            if bundle:
                history.append({key: bundle[key] for key in ("series_id", "saved_at", "document", "state")})
        return sorted(history, key=lambda entry: entry["saved_at"], reverse=True)

    def save(self, payload, lookup_run):
        series_id = payload.get("series_id")
        if not is_hex_id(series_id):
            raise ValueError("Deney serisi kimliği geçersiz.")
        with self.lock:
            if existing := self.load(series_id):
                return existing
            bundle = self._build_bundle(series_id, payload.get("attempts"), lookup_run)
            self.folder.mkdir(parents=True, exist_ok=True)
            temp_path = None
            try:
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.folder, delete=False) as target:
                    temp_path = Path(target.name)
                    json.dump(bundle, target, ensure_ascii=False, indent=2)
                os.replace(temp_path, self.folder / f"{series_id}.json")
            finally:
                if temp_path:
                    temp_path.unlink(missing_ok=True)
            return bundle

    def _build_bundle(self, series_id, entries, lookup_run):
        profile_ids = tuple(PROFILES)
        width = len(profile_ids)
        if not isinstance(entries, list) or len(entries) != width * (REPETITIONS + 1):
            raise ValueError("Bütün profil ve ısınma turları gerekli.")
        trials = {profile: [] for profile in profile_ids}
        seen = set()
        reference = None
        for index, entry in enumerate(entries):
            round_number, offset = divmod(index, width)
            profile = profile_ids[(round_number + offset) % width]
            if not isinstance(entry, dict) or entry.get("profile") != profile or entry.get("round") != round_number:
                raise ValueError("Deney turu ve profil sırası geçersiz.")
            run_id = entry.get("run_id")
            run = None
            if run_id is not None:
                if not is_hex_id(run_id) or run_id in seen:
                    raise ValueError("Çalışma kimliği geçersiz veya tekrar ediyor.")
                seen.add(run_id)
                run = lookup_run(run_id)
                if not run or run.get("profile") != profile or run.get("plugin") != "education":
                    raise ValueError("Çalışma bu profildeki eğitim deneyiyle eşleşmiyor.")
                identity = (run.get("input_sha256"), run.get("package_sha256"))
                if not all(identity):
                    raise ValueError("Çalışmanın belge veya eklenti özeti eksik.")
                if reference and identity != (reference["input_sha256"], reference["package_sha256"]):
                    raise ValueError("Serideki belge veya eğitim paketi değişmiş.")
                if reference is None:
                    reference = run
            if run and run.get("status") in TERMINAL:
                data = recorded_run(run)
            else:
                error = entry.get("error")
                data = {"status": "unknown", "error": error[:240] if isinstance(error, str) else "Çalışma sonucu doğrulanmadı."}
            trials[profile].append({"round": round_number, "data": data})
        summary = {profile: summarize(attempts) for profile, attempts in trials.items()}
        state = "completed" if all(
            summary[profile]["valid_pdf"] == REPETITIONS and trials[profile][0]["data"]["status"] == "completed"
            for profile in profile_ids
        ) else "partial"
        return {
            "schema_version": 1, "series_id": series_id, "saved_at": time.time(), "state": state,
            "document": {key: reference[key] for key in ("filename", "input_sha256", "package_sha256")
                         if reference and key in reference},
            "method": {"warmups_per_profile": 1, "repetitions_per_profile": REPETITIONS, "round_order": "rotating"},
            "profiles": [{"id": profile, **PROFILES[profile]} for profile in profile_ids],
            "trials": trials, "summary": summary,
        }
