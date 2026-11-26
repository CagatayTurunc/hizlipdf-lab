import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docx import Document
from packages import PluginStore, build_package, read_package, definition
from analysis_docx import analyze_docx


def altered_package(manifest, pipeline, extra=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("pipeline.json", json.dumps(pipeline))
        if extra:
            archive.writestr(extra, "unexpected")
    return stream.getvalue()


class PackageTests(unittest.TestCase):
    def test_installed_package_persists_and_uninstall_removes_it(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PluginStore(folder)
            self.assertFalse(any(p["installed"] for p in store.listing()))
            data = build_package("hizlipdf.normal")
            info = store.install(data)
            after_restart = PluginStore(folder)
            self.assertEqual(after_restart.resolve("hizlipdf.normal")[1], data)
            self.assertEqual(after_restart.listing()[0]["sha256"], info["sha256"])
            after_restart.uninstall("hizlipdf.normal")
            with self.assertRaises(ValueError):
                after_restart.resolve("hizlipdf.normal")

    def test_rejects_unapproved_steps_versions_and_traversal(self):
        manifest, pipeline = definition("hizlipdf.education")
        cases = [altered_package({**manifest, "version": "9.0"}, pipeline),
                 altered_package({**manifest, "api_version": True}, pipeline),
                 altered_package(manifest, {"steps": ["execute_arbitrary_code"]}),
                 altered_package(manifest, pipeline, "../../outside.txt"),
                 altered_package({**manifest, "id": "../unknown"}, pipeline)]
        with tempfile.TemporaryDirectory() as folder:
            store = PluginStore(folder)
            for data in cases:
                with self.subTest(size=len(data)), self.assertRaises(ValueError):
                    store.install(data)
            self.assertEqual(list(Path(folder).iterdir()), [])
            original = build_package("hizlipdf.education")
            store.install(original)
            with self.assertRaises(ValueError):
                store.install(cases[0])
            self.assertEqual(store.resolve("hizlipdf.education")[1], original)

    def test_corruption_is_not_silently_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PluginStore(folder)
            store.install(build_package("hizlipdf.normal"))
            store.path("hizlipdf.normal").write_bytes(build_package("hizlipdf.education"))
            with self.assertRaisesRegex(ValueError, "kimliği"):
                store.resolve("hizlipdf.normal")
            self.assertFalse(store.listing()[0]["installed"])

    def test_exact_plans_differ_only_in_extra_lab_step(self):
        normal = read_package(build_package("hizlipdf.normal"))
        education = read_package(build_package("hizlipdf.education"))
        self.assertEqual(normal["pipeline"]["steps"], ["analyze_docx", "convert_pdf"])
        self.assertEqual(education["pipeline"]["steps"], normal["pipeline"]["steps"] + ["synthetic_lab_probe"])
        self.assertEqual(build_package("hizlipdf.normal"), build_package("hizlipdf.normal"))


class AnalysisTests(unittest.TestCase):
    def test_body_table_runs_and_heading_counts(self):
        doc = Document()
        doc.add_heading("Örnek Başlık", 1)
        paragraph = doc.add_paragraph()
        paragraph.add_run("Mer"); paragraph.add_run("haba dünya 2026")
        doc.add_paragraph("")
        cells = doc.add_table(rows=1, cols=2).rows[0].cells
        cells[0].text, cells[1].text = "Bir hücre", "İki"
        doc.sections[0].header.paragraphs[0].text = "Bu üstbilgi sayılmaz"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.docx"
            doc.save(path)
            result = analyze_docx(path)
        self.assertEqual(result["word_count"], 8)
        self.assertEqual(result["paragraph_count"], 4)
        self.assertEqual(result["headings"], ["Örnek Başlık"])
        self.assertEqual(result["table_count"], 1)


if __name__ == "__main__":
    unittest.main()
