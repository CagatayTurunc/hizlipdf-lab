import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks import BenchmarkStore, REPETITIONS
from sandbox import PROFILES
from server import Lab


def benchmark_records():
    entries, records = [], {}
    profiles = tuple(PROFILES)
    for round_number in range(REPETITIONS + 1):
        for offset in range(len(profiles)):
            profile = profiles[(offset + round_number) % len(profiles)]
            run_id = f"{len(entries) + 1:032x}"
            entries.append({"profile": profile, "round": round_number, "run_id": run_id})
            records[run_id] = {
                "run_id": run_id, "profile": profile, "plugin": "education",
                "filename": "Musteri_Teklifi.docx", "status": "completed",
                "input_sha256": "docx-test-sha", "package_sha256": "package-test-sha",
                "token": "secret-token",
                "file_audit": {"status": "opened"} if profile in ("A", "C") else {"status": "unavailable"},
                "network_audit": {"status": "reachable"} if profile in ("A", "B") else {"status": "unverified"},
                "syscalls": [{"kind": "openat", "status": "allowed", "source": "fixture",
                              "errno": None, "raw": "test observation"}],
                "pdf": {"pages": 1, "structurally_valid": True, "text_excerpt": "private-extracted-text",
                        "sample_validation": {"passed": True, "checks": [{"label": "Toplam", "matched": True}]}},
                "total_ms": 1000 if round_number == 0 else round_number * 10,
                "metrics": {"accepted_bytes": 122 if profile == "A" else 0},
                "receiver": [{"kind": "CONTENT", "accepted_bytes": 122, "token": "secret-token"}]
                if profile == "A" else [],
                "receiver_health": {"before": True, "after": profile != "C"},
                "events": [{"event": "CONVERSION_FINISHED", "result": "ok", "duration_ms": 8},
                           {"event": "LAB_PROBE_FINISHED", "result": "ok", "duration_ms": 2}],
            }
    return entries, records


class BenchmarkTests(unittest.TestCase):
    def test_reopens_saved_series_and_excludes_warmup_and_failed_runs(self):
        entries, records = benchmark_records()
        failed = next(entry for entry in entries if entry["round"] == 2 and entry["profile"] == "D")
        records[failed["run_id"]]["status"] = "failed"
        series_id = "1" * 32
        payload = {"series_id": series_id, "attempts": entries}

        with tempfile.TemporaryDirectory() as folder:
            store = BenchmarkStore(Path(folder))
            bundle = store.save(payload, records.get)
            resumed = BenchmarkStore(Path(folder))
            self.assertEqual(resumed.load(series_id), bundle)
            self.assertEqual(resumed.list()[0]["series_id"], series_id)
            self.assertEqual(resumed.save(payload, {}.get), bundle)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

        self.assertEqual(bundle["state"], "partial")
        self.assertEqual(bundle["summary"]["A"]["total"], {"median": 30, "min": 10, "max": 50, "count": 5})
        self.assertEqual(bundle["summary"]["D"]["total"], {"median": 35.0, "min": 10, "max": 50, "count": 4})
        self.assertIsNone(bundle["summary"]["C"]["accepted"])
        self.assertEqual(bundle["summary"]["A"]["pdf_reference_passed"], 5)
        self.assertEqual(bundle["trials"]["D"][2]["data"]["status"], "failed")
        self.assertEqual(bundle["trials"]["A"][1]["data"]["syscalls"][0]["raw"], "test observation")
        self.assertEqual(bundle["trials"]["A"][1]["data"]["receiver"][0]["accepted_bytes"], 122)
        self.assertNotIn("secret-token", json.dumps(bundle))
        self.assertNotIn("private-extracted-text", json.dumps(bundle))

    def test_rejects_mixed_documents_and_duplicate_run_references(self):
        entries, records = benchmark_records()
        with tempfile.TemporaryDirectory() as folder:
            store = BenchmarkStore(Path(folder))
            payload = {"series_id": "2" * 32, "attempts": entries}
            records[entries[-1]["run_id"]]["input_sha256"] = "different"
            with self.assertRaisesRegex(ValueError, "belge"):
                store.save(payload, records.get)
            entries[-1]["run_id"] = entries[0]["run_id"]
            with self.assertRaisesRegex(ValueError, "tekrar"):
                store.save(payload, records.get)
            self.assertEqual(store.list(), [])

    def test_reopened_lab_loads_terminal_run_from_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            run_id = "a" * 32
            run_folder = Path(folder) / run_id
            run_folder.mkdir()
            saved = {"run_id": run_id, "status": "completed", "file_audit": {}, "token": "secret-token"}
            (run_folder / "evidence.json").write_text(json.dumps(saved), encoding="utf-8")
            lab = Lab(folder)
            try:
                self.assertEqual(lab.runs, {})
                self.assertEqual(lab.view(run_id), {key: value for key, value in saved.items() if key != "token"})
                self.assertIsNone(lab.view("../"))
            finally:
                lab.receiver.shutdown()
                lab.receiver.server_close()


if __name__ == "__main__":
    unittest.main()
