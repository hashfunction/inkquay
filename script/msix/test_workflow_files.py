# Copyright 2026 Trieflow LLC. MIT.
"""Real-file/Poppler oracle tests; these do not claim installed GTK interactions."""
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET


class WorkflowFilesTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name("workflow_files.py")
        self.assertTrue(path.exists(), "Installed consumer workflow file oracle is missing")
        spec = importlib.util.spec_from_file_location("workflow_files", path)
        self.w = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.w)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "owned"
        self.w.prepare(self.root)
        self.tools = {
            name: (
                Path(sys.executable).parent / (name + ".exe")
                if os.name == "nt"
                else Path(shutil.which(name) or "").resolve()
            )
            for name in ("pdfinfo", "pdftotext", "pdftoppm")
        }
        self.assertTrue(
            all(p.is_file() for p in self.tools.values()), "Actual Poppler tools are required"
        )

    def note(self):
        doc = ET.fromstring(gzip.decompress((self.root / "source.xopp").read_bytes()))
        page = ET.SubElement(doc, "page", width="595.275591", height="841.889764")
        ET.SubElement(
            page,
            "background",
            type="solid",
            color="#ffffffff",
            style="lined",
            config="iq=2,m1=166,r1=24",
        )
        ET.SubElement(page, "layer")
        (self.root / "saved.xopp").write_bytes(gzip.compress(ET.tostring(doc)))

    def export(self, name="first.pdf", protected=("saved.xopp", "background.pdf")):
        self.note()
        # Standalone oracle fixtures: independently generated PDF is explicitly not UI output.
        data = self.w.make_pdf(
            [
                "BT /F1 18 Tf 50 740 Td (InkQuay qualification source) Tj 0 -30 Td (InkQuay owned note) Tj ET",
                "BT /F1 12 Tf 50 780 Td (Topic / Date Cues Notes Summary) Tj ET 0 0 0 RG 1 w 166 40 m 166 800 l S 40 700 m 555 700 l S 40 650 m 555 650 l S",
            ]
        )
        (self.root / name).write_bytes(data)
        report = {
            "version": 1,
            "status": "passed",
            "published": True,
            "output": str(self.root / name),
            "expectedPages": 2,
            "actualPages": 2,
            "outputBytes": len(data),
            "error": "",
            "warnings": [
                "Checks cover PDF structure, page count, positive page sizes and unchanged protected files; visual fidelity and accessibility were not checked."
            ],
            "recoveryFiles": [],
            "protectedFiles": [
                {
                    "path": str(self.root / p),
                    "sha256Before": self.w.fingerprint(self.root / p)["sha256"],
                }
                for p in protected
            ],
        }
        p = self.root / (name + ".12345678-1234-1234-1234-123456789abc.inkquay-report.json")
        p.write_text(json.dumps(report), encoding="utf-8")
        return p, report

    def test_report_scope_disclosure_matches_actual_native_producer(self):
        import re

        source = (
            Path(__file__).resolve().parents[2] / "src/core/control/jobs/PdfExportVerifier.cpp"
        ).read_text(encoding="utf-8")
        body = source.split("result.status = PdfExportVerification::Status::Passed;", 1)[1]
        statement = body.split("result.warnings.emplace_back(", 1)[1].split(");", 1)[0]
        native_message = "".join(
            json.loads(part) for part in re.findall(r'"[^"\\]*(?:\\.[^"\\]*)*"', statement)
        )
        _, report = self.export()
        self.assertEqual(report["warnings"], [native_message])

    def test_existing_root_is_never_replaced(self):
        before = (self.root / "source.xopp").read_bytes()
        with self.assertRaises(FileExistsError):
            self.w.prepare(self.root)
        self.assertEqual((self.root / "source.xopp").read_bytes(), before)

    def test_real_poppler_confirms_count_text_and_rendered_template(self):
        self.export()
        result = self.w.verify_export(
            self.root, "first.pdf", ("saved.xopp", "background.pdf"), self.tools
        )
        self.assertEqual(result["pages"], 2)
        self.assertGreater(result["template_dark_pixels"], 200)
        self.assertEqual(len(result["tools"]), 3)

    def test_modified_original_and_wrong_applied_template_are_rejected(self):
        self.note()
        self.w.verify_note(self.root)
        original = (self.root / "background.pdf").read_bytes()
        (self.root / "background.pdf").write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "original"):
            self.w.verify_note(self.root)
        (self.root / "background.pdf").write_bytes(original)
        data = gzip.decompress((self.root / "saved.xopp").read_bytes()).replace(b"iq=2", b"iq=3")
        (self.root / "saved.xopp").write_bytes(gzip.compress(data))
        with self.assertRaisesRegex(ValueError, "template"):
            self.w.verify_note(self.root)

    def test_failed_wrong_output_boolean_counts_and_missing_protection_cannot_pass(self):
        p, report = self.export()
        for change in (
            {"status": "failed"},
            {"published": False},
            {"actualPages": True},
            {"expectedPages": 3},
            {"output": str(self.root / "background.pdf")},
            {"protectedFiles": []},
            {"warnings": []},
            {"warnings": ["unexpected warning"]},
        ):
            with self.subTest(change=change):
                p.write_text(json.dumps(dict(report, **change)), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.w.verify_export(
                        self.root, "first.pdf", ("saved.xopp", "background.pdf"), self.tools
                    )

    def test_pdf_count_and_text_are_independent_of_the_report(self):
        p, report = self.export()
        for streams in (
            ["BT /F1 18 Tf 50 740 Td (wrong text) Tj ET"] * 2,
            ["BT /F1 18 Tf 50 740 Td (InkQuay qualification source InkQuay owned note) Tj ET"],
        ):
            data = self.w.make_pdf(streams)
            (self.root / "first.pdf").write_bytes(data)
            report["outputBytes"] = len(data)
            p.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.w.verify_export(
                    self.root, "first.pdf", ("saved.xopp", "background.pdf"), self.tools
                )

    def test_template_labels_without_its_ruling_are_rejected(self):
        p, report = self.export()
        data = self.w.make_pdf(
            [
                "BT /F1 18 Tf 50 740 Td (InkQuay qualification source InkQuay owned note) Tj ET",
                "BT /F1 12 Tf 50 780 Td (Topic / Date Cues Notes Summary) Tj ET",
            ]
        )
        (self.root / "first.pdf").write_bytes(data)
        report["outputBytes"] = len(data)
        p.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ruling"):
            self.w.verify_export(
                self.root, "first.pdf", ("saved.xopp", "background.pdf"), self.tools
            )

    def test_missing_blank_render_duplicate_reports_and_links_are_rejected(self):
        p, report = self.export()
        data = self.w.make_pdf(
            ["BT /F1 18 Tf 50 740 Td (InkQuay qualification source InkQuay owned note) Tj ET", ""]
        )
        (self.root / "first.pdf").write_bytes(data)
        report["outputBytes"] = len(data)
        p.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "template"):
            self.w.verify_export(
                self.root, "first.pdf", ("saved.xopp", "background.pdf"), self.tools
            )
        (
            self.root / "first.pdf.00000000-1234-1234-1234-123456789abc.inkquay-report.json"
        ).write_bytes(p.read_bytes())
        with self.assertRaises(ValueError):
            self.w.verify_export(
                self.root, "first.pdf", ("saved.xopp", "background.pdf"), self.tools
            )
        if hasattr(Path, "symlink_to"):
            target = self.root / "linked.xopp"
            try:
                target.symlink_to(self.root / "source.xopp")
            except OSError:
                return  # Windows symlink privilege is not required for this separate case.
            with self.assertRaises(ValueError):
                self.w.fingerprint(target)


if __name__ == "__main__":
    unittest.main()
