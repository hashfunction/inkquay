"""Exporter unsigned retention and exact rederivation policy tests."""

import json
from pathlib import Path
import tempfile
import unittest
import store_export as export


class RetentionTests(unittest.TestCase):
    def test_exact_two_files_and_unchanged_unsigned_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "unsigned.msix"
            package.write_bytes(b"exact unsigned fixture")
            expected = export.msix.file_record(package)
            export.retain_unsigned(package, root / "ready", {"store_package": expected})
            self.assertEqual(
                sorted(p.name for p in (root / "ready").iterdir()),
                ["Scriblark_1.0.1.0_x64.msix", "release-ready.json"],
            )
            self.assertEqual(
                (root / "ready/Scriblark_1.0.1.0_x64.msix").read_bytes(),
                package.read_bytes(),
            )
            with self.assertRaises(ValueError):
                export.retain_unsigned(
                    package, root / "ready", {"store_package": expected}
                )

    def test_changed_package_cannot_receive_readiness_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "unsigned.msix"
            package.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                export.retain_unsigned(
                    package,
                    root / "ready",
                    {"store_package": {"bytes": 1, "sha256": "0" * 64}},
                )
            self.assertFalse((root / "ready/release-ready.json").exists())

    def test_context_requires_exact_current_run_and_normal_mode(self):
        valid = {
            "CI": "true",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "hashfunction/inkquay",
            "INKQUAY_CAPTURE_CRASH_STACK": "false",
        }
        self.assertEqual(export.context(valid)["workflow_run_id"], "123")
        for key, value in (
            ("GITHUB_SHA", "short"),
            ("GITHUB_RUN_ID", ""),
            ("GITHUB_RUN_ATTEMPT", "0"),
            ("GITHUB_REPOSITORY", "other/repo"),
            ("INKQUAY_CAPTURE_CRASH_STACK", "true"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                export.context({**valid, key: value})


if __name__ == "__main__":
    unittest.main()
