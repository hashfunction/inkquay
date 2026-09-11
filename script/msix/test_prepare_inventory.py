#!/usr/bin/env python3
"""Clean-source evidence tests using real Git repositories."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import prepare_inventory


class SourceStatusTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name) / "source"
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "config", "user.name", "Ink Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.source), "config", "user.email", "ink@test.invalid"],
            check=True,
        )
        (self.source / "tracked.txt").write_text("original\n", encoding="utf-8")
        (self.source / "old-name.txt").write_text("rename me\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "commit", "-qm", "fixture"], check=True
        )
        self.commit = subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True
        ).strip()

    def test_dirty_checkout_records_exact_status_paths_and_stays_rejected(self):
        (self.source / ".git/info/exclude").write_text(
            "/evidence/\n", encoding="utf-8"
        )
        (self.source / "tracked.txt").write_text("generated\n", encoding="utf-8")
        (self.source / "generated output.txt").write_text("generated\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.source), "mv", "old-name.txt", "new-name.txt"],
            check=True,
        )
        evidence = self.source / "evidence" / "source-status.json"

        with self.assertRaisesRegex(ValueError, "tracked.txt"):
            prepare_inventory.require_clean_source(
                self.source, self.commit, evidence
            )

        record = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual(record["schemaVersion"], 1)
        self.assertEqual(record["sourceCommit"], self.commit)
        self.assertFalse(record["clean"])
        self.assertFalse(record["entriesTruncated"])
        self.assertEqual(record["statusEntryCount"], 3)
        self.assertEqual(
            record["entries"],
            [
                {
                    "originalPath": "old-name.txt",
                    "path": "new-name.txt",
                    "status": "R ",
                },
                {"path": "tracked.txt", "status": " M"},
                {"path": "generated output.txt", "status": "??"},
            ],
        )
        raw = subprocess.check_output(
            [
                "git",
                "-C",
                str(self.source),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ]
        )
        self.assertEqual(record["statusBytes"], len(raw))
        self.assertEqual(record["statusSha256"], hashlib.sha256(raw).hexdigest())

    def test_clean_checkout_writes_clean_evidence(self):
        evidence = self.source / "ignored-build" / "source-status.json"
        (self.source / ".git/info/exclude").write_text(
            "/ignored-build/\n", encoding="utf-8"
        )
        record = prepare_inventory.require_clean_source(
            self.source, self.commit, evidence
        )
        self.assertTrue(record["clean"])
        self.assertEqual(record["entries"], [])
        self.assertEqual(json.loads(evidence.read_text(encoding="utf-8")), record)

    def test_existing_evidence_is_preserved(self):
        evidence = self.source / "ignored-build" / "source-status.json"
        evidence.parent.mkdir()
        evidence.write_bytes(b"existing")
        (self.source / ".git/info/exclude").write_text(
            "/ignored-build/\n", encoding="utf-8"
        )
        with self.assertRaises(FileExistsError):
            prepare_inventory.require_clean_source(
                self.source, self.commit, evidence
            )
        self.assertEqual(evidence.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
