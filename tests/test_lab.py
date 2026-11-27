import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import FILES
from linux_isolation import isolation_evidence, read_target_mount
from sandbox import command
from observations import assess, read_syscalls
from server import Lab, check_sample_pdf, generate_forensic_html_report, make_hexdump, sample_docx, validate_docx
from packages import build_package


class InputTests(unittest.TestCase):
    def test_real_docx_and_invalid_inputs(self):
        validate_docx(sample_docx())
        for content in (b"", b"not a docx"):
            with self.assertRaises(ValueError):
                validate_docx(content)

    def test_archive_expansion_limit(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "x")
            archive.writestr("word/document.xml", "x" * (33 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, "sınır"):
            validate_docx(stream.getvalue())

    def test_sample_pdf_checks_row_value_and_page_count(self):
        text = "MaviRota Danışmanlık\nMüşteri Teklifi\nBelge analizi 12.000\nRaporlama 8.000\nToplam 20.000"
        self.assertTrue(check_sample_pdf(text, 1)["passed"])

        wrong_total = text.replace("Toplam 20.000", "Toplam 120.000")
        checks = check_sample_pdf(wrong_total, 2)
        self.assertFalse(checks["passed"])
        failures = {check["label"]: check["actual"] for check in checks["checks"] if not check["matched"]}
        self.assertEqual(failures, {"Sayfa sayısı": 2, "Toplam": "120.000"})

    def test_unavailable_isolation_never_falls_back(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            command({"profile": "D"}, Path("config"), Path("run"), Path("root"), False)


class ObservationTests(unittest.TestCase):
    def test_failed_or_missing_d_run_has_unverified_report(self):
        failed = {"profile": "D", "plugin": "education", "status": "failed", "syscalls": []}
        report = generate_forensic_html_report(failed)
        self.assertIn("Doğrulanmadı", report)
        for invented in ("TAM İZOLASYON", "ENETUNREACH", "POST /collect", "%100"):
            self.assertNotIn(invented, report)
        completed = {**failed, "status": "completed", "pdf": {"structurally_valid": True}}
        self.assertIn("Doğrulanmadı", generate_forensic_html_report(completed))
        self.assertEqual(assess({**completed, "profile": "A"}, True),
                         assess(completed, True))

    def test_only_completed_calls_for_current_targets_count(self):
        prefix = '42 connect(5, {sa_family=AF_INET, sin_port=htons('
        suffix = '), sin_addr=inet_addr("127.0.0.1")}, 16)'
        names = list(FILES)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.txt"
            self.assertEqual(read_syscalls(path, 32123), [])
            path.write_text("\n".join([
                '42 openat(AT_FDCWD, "/lab/input.docx", O_RDONLY|O_CLOEXEC) = 5',
                f'42 openat(AT_FDCWD, "/lab/targets/{names[0]}", O_RDONLY|O_CLOEXEC) = -1 ENOENT (Missing)',
                f'[pid 42] openat(AT_FDCWD, "/lab/targets/{names[1]}", O_RDONLY|O_CLOEXEC <unfinished ...>',
                '[pid 43] openat(AT_FDCWD, "/lib/test", O_RDONLY|O_CLOEXEC) = 5',
                '[pid 42] <... openat resumed>) = -1 EACCES (Permission denied)',
                prefix + "8765" + suffix + " = 0",
                prefix + "32123" + suffix + " = -1 ENETUNREACH (Network is unreachable)",
            ]), encoding="utf-8")
            calls = read_syscalls(path, 32123)
        self.assertEqual([call["source"] for call in calls], [*names, "127.0.0.1:32123"])
        self.assertEqual([call["errno"] for call in calls], ["ENOENT", "EACCES", "ENETUNREACH"])

        record = {"plugin": "education", "syscalls": calls, "receiver_health": {"before": True, "after": True}}
        files, network, verdict = assess(record, True)
        self.assertEqual(files["status"], "unavailable")
        self.assertEqual(network["status"], "unreachable")
        self.assertEqual(verdict["status"], "observed")
        self.assertEqual(assess({**record, "syscalls": calls[:1]}, True)[0]["status"], "unverified")
        self.assertEqual(assess({**record, "receiver_health": {"before": True}}, True)[1]["status"], "unverified")
        self.assertEqual(assess({**record, "receiver": [{"kind": "LAB_PING"}]}, True)[1]["status"], "reachable")
        self.assertEqual(assess(record, False)[2]["status"], "unverified")


class IsolationObservationTests(unittest.TestCase):
    def test_mountinfo_matches_only_the_exact_target(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mountinfo"
            self.assertIsNone(read_target_mount(path))
            base = "30 22 0:15 / / rw - tmpfs tmpfs rw\n"
            nested = "33 30 8:1 /fixture /lab/targets/nested ro - ext4 /dev/vda1 rw\n"
            path.write_text(base + nested, encoding="utf-8")
            self.assertEqual(read_target_mount(path), {"present": False, "id": None, "read_only": None})
            path.write_text(base + "34 30 8:1 /fixture /lab/targets ro - ext4 /dev/vda1 rw\n",
                            encoding="utf-8")
            self.assertEqual(read_target_mount(path), {"present": True, "id": "34", "read_only": True})
            path.write_text("", encoding="utf-8")
            self.assertIsNone(read_target_mount(path))

    def test_namespace_relation_requires_both_observed_identities(self):
        receiver = {"id": "net:[321]", "device": 4}
        self.assertEqual(isolation_evidence([], receiver)["network_relation"], "unverified")
        worker = {"event": "ISOLATION_OBSERVED", "worker_network": receiver.copy()}
        self.assertEqual(isolation_evidence([worker], None)["network_relation"], "unverified")
        self.assertEqual(isolation_evidence([worker], receiver)["network_relation"], "shared")
        other = {"id": "net:[321]", "device": 5}
        self.assertEqual(isolation_evidence([worker], other)["network_relation"], "separate")


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lab = Lab(self.temp.name)

    def tearDown(self):
        self.lab.receiver.shutdown()
        self.lab.receiver.server_close()
        self.temp.cleanup()

    def post_receiver(self, payload):
        request = urllib.request.Request(f"http://127.0.0.1:{self.lab.receiver.server_port}/collect",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(request, timeout=2)

    def test_receiver_rejects_non_synthetic_content_and_duplicate(self):
        record = {"run_id": "test", "token": "secret", "status": "running", "receiver": []}
        self.lab.runs["test"] = record
        payload = {"run_id": "test", "token": "secret", "kind": "CONTENT",
                   "source": "Sirket_Butcesi_TEST.csv", "content": "arbitrary text"}
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post_receiver(payload)
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(record["receiver"], [])
        payload["content"] = FILES[payload["source"]]
        payload["token"] = "wrong"
        with self.assertRaises(urllib.error.HTTPError):
            self.post_receiver(payload)
        payload["token"] = "secret"
        with self.post_receiver(payload) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(len(record["receiver"]), 1)
        with self.assertRaises(urllib.error.HTTPError):
            self.post_receiver(payload)
        self.assertEqual(len(record["receiver"]), 1)
        self.assertNotIn("token", self.lab.view("test"))
        entry, = record["receiver"]
        headers, body = entry["http_record"].split("\r\n\r\n", 1)
        self.assertIn(f"Content-Length: {len(body.encode('utf-8'))}", headers)
        self.assertNotIn("token", json.loads(body))
        self.assertEqual(entry["http_record_hex"], make_hexdump(entry["http_record"].encode("utf-8")))
        self.assertTrue(self.lab.receiver_ready())


    def test_api_layer_refuses_unsupported_profile(self):
        self.lab.sandbox = {"available": False, "reason": "test"}
        with self.assertRaisesRegex(ValueError, "izolasyon"):
            self.lab.create({"profile": "B", "plugin": "education"})
        self.assertEqual(self.lab.runs, {})

    def test_view_reads_complete_worker_events_during_run(self):
        folder = Path(self.temp.name) / "demo"
        folder.mkdir()
        event_path = folder / "worker-events.jsonl"
        started = {"event": "CONVERSION_STARTED", "result": "running"}
        finished = {"event": "CONVERSION_FINISHED", "result": "ok"}
        self.lab.runs["demo"] = {"status": "running", "events": [], "token": "secret"}
        event_path.write_text(json.dumps(started) + "\n" + json.dumps(finished), encoding="utf-8")
        self.assertEqual(self.lab.view("demo")["events"], [started])
        with event_path.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        self.assertEqual(self.lab.view("demo")["events"], [started, finished])
        self.assertNotIn("token", self.lab.view("demo"))

    def run_conversion(self, plugin, profile="A", uninstall_after_start=False):
        if not self.lab.soffice:
            self.skipTest("LibreOffice yok; gerçek dönüşüm testi atlandı.")
        installed = self.lab.plugins.install(build_package("hizlipdf." + plugin))
        run_id = self.lab.create({"sample": True, "profile": profile, "plugin": plugin})
        if uninstall_after_start:
            self.lab.plugins.uninstall("hizlipdf." + plugin)
        deadline = time.monotonic() + 85
        while time.monotonic() < deadline:
            result = self.lab.view(run_id)
            if result["status"] not in ("queued", "running"):
                break
            time.sleep(0.05)
        self.assertEqual(result["status"], "completed", result.get("error"))
        self.assertEqual(result["pdf"]["pages"], 1)
        self.assertTrue(result["pdf"]["sample_validation"]["passed"], result["pdf"]["sample_validation"])
        self.assertEqual(len(result["pdf"]["sample_validation"]["checks"]), 6)
        if self.lab.preview_renderer:
            preview = Path(self.temp.name) / run_id / "output/sample-preview.png"
            self.assertEqual(preview.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(result["pdf"]["preview_url"], f"/api/runs/{run_id}/preview")
        self.assertIn("20.000", result["pdf"]["text_excerpt"])
        self.assertIn("Müşteri Teklifi", result["pdf"]["text_excerpt"])
        self.assertNotIn("LAB-BUTCE", result["pdf"]["text_excerpt"])
        self.assertEqual(result["plugin_manifest"]["id"], "hizlipdf." + plugin)
        self.assertEqual(result["package_sha256"], installed["sha256"])
        self.assertEqual(result["analysis"]["table_count"], 1)
        self.assertIn("Müşteri Teklifi", result["analysis"]["headings"])
        self.assertTrue((Path(self.temp.name) / run_id / "output/input.pdf").is_file())
        self.assertFalse((Path(self.temp.name) / run_id / "config.json").exists())
        return result

    def test_normal_vs_education_preserves_real_pdf_and_receiver_proof(self):
        # The native baseline is supported on the development Mac as well as Linux.
        self.lab.sandbox = {"available": False, "reason": "Native baseline test"}
        normal = self.run_conversion("normal")
        education = self.run_conversion("education")
        self.assertEqual(normal["pdf"]["text_excerpt"], education["pdf"]["text_excerpt"])
        self.assertEqual(normal["analysis"], education["analysis"])
        self.assertEqual(normal["input_sha256"], education["input_sha256"])
        self.assertEqual(normal["receiver"], [])
        self.assertEqual(education["metrics"]["accepted_sources"], 2)
        self.assertEqual(education["metrics"]["accepted_bytes"], sum(len(x.encode()) for x in FILES.values()))
        self.assertEqual(len([x for x in education["receiver"] if x["kind"] == "LAB_PING"]), 1)
        self.assertFalse(education["sandbox_applied"])
        self.assertFalse(education["independent_file_observer"])
        self.assertEqual(education["syscalls"], [])
        self.assertEqual(education["verdict"]["status"], "unverified")
        self.assertEqual(education["network_audit"]["status"], "reachable")
        self.assertEqual(normal["verdict"]["status"], "not_attempted")
        self.assertEqual(education["receiver_health"], {"before": True, "after": True})

    def test_uninstall_during_run_keeps_snapshot_but_rejects_next_run(self):
        self.lab.sandbox = {"available": False, "reason": "Native baseline test"}
        self.run_conversion("normal", uninstall_after_start=True)
        with self.assertRaisesRegex(ValueError, "kurulu değil"):
            self.lab.create({"plugin": "normal", "profile": "A"})

    def test_real_linux_profile_matrix(self):
        if not self.lab.sandbox["available"]:
            self.skipTest("Gerçek Linux bubblewrap ortamı yok; profil matrisi doğrulanmadı.")
        for profile, reads, accepted, ping in [("A", 2, 2, True), ("B", 0, 0, True),
                                                ("C", 2, 0, False), ("D", 0, 0, False)]:
            with self.subTest(profile=profile):
                result = self.run_conversion("education", profile)
                self.assertTrue(result["sandbox_applied"])
                self.assertEqual(result["metrics"]["read_sources_worker_reported"], reads)
                self.assertEqual(result["metrics"]["accepted_sources"], accepted)
                self.assertEqual(any(x["kind"] == "LAB_PING" for x in result["receiver"]), ping)
                observation = result["isolation"]
                self.assertEqual(observation["target_mount"]["present"], profile in ("A", "C"))
                if observation["target_mount"]["present"]:
                    self.assertTrue(observation["target_mount"]["read_only"])
                self.assertEqual(observation["network_relation"],
                                 "shared" if profile in ("A", "B") else "separate")


if __name__ == "__main__":
    unittest.main()
