import base64
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
from sandbox import command
from server import Lab, sample_docx, validate_docx
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

    def test_unavailable_isolation_never_falls_back(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            command({"profile": "D"}, Path("config"), Path("run"), Path("root"), False)


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

    def test_api_layer_refuses_unsupported_profile(self):
        self.lab.sandbox = {"available": False, "reason": "test"}
        with self.assertRaisesRegex(ValueError, "izolasyon"):
            self.lab.create({"profile": "B", "plugin": "education"})
        self.assertEqual(self.lab.runs, {})

    def run_conversion(self, plugin, profile="A", uninstall_after_start=False):
        if not self.lab.soffice:
            self.skipTest("LibreOffice yok; gerçek dönüşüm testi atlandı.")
        installed = self.lab.plugins.install(build_package("hizlipdf." + plugin))
        run_id = self.lab.create({"filename": "Musteri_Teklifi.docx", "profile": profile, "plugin": plugin,
                                  "content_base64": base64.b64encode(sample_docx()).decode()})
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
        self.assertEqual(normal["receiver"], [])
        self.assertEqual(education["metrics"]["accepted_sources"], 2)
        self.assertEqual(education["metrics"]["accepted_bytes"], sum(len(x.encode()) for x in FILES.values()))
        self.assertEqual(len([x for x in education["receiver"] if x["kind"] == "LAB_PING"]), 1)
        self.assertFalse(education["sandbox_applied"])
        self.assertFalse(education["independent_file_observer"])

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


if __name__ == "__main__":
    unittest.main()
