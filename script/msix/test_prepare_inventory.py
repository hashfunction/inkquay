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
        # Model a real checkout: attributes are present in the commit before
        # Git decides how to materialize any tracked file.
        attributes = Path(__file__).resolve().parents[2] / ".gitattributes"
        (self.source / ".gitattributes").write_bytes(attributes.read_bytes())
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "commit", "-qm", "fixture"], check=True
        )
        self.commit = subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True
        ).strip()

    def test_windows_and_msys_checkout_rules_produce_the_same_clean_bytes(self):
        (self.source / "sample.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00binary\r\n")
        log = self.source / "Release/verification/raw.log"
        log.parent.mkdir(parents=True)
        log.write_bytes(b"native raw output\r\nwith trailing spaces  \r\n")
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.source), "commit", "-qm", "checkout policy"], check=True)
        clone = self.source.parent / "windows checkout"
        subprocess.run(["git", "clone", "-q", "--no-local", "-c", "core.autocrlf=true",
                        str(self.source), str(clone)], check=True)
        # actions/checkout uses Git for Windows; the native build uses MSYS Git.
        # A tracked policy must produce identical bytes under both defaults.
        self.assertEqual((clone / "tracked.txt").read_bytes(), b"original\n")
        self.assertEqual((clone / "sample.png").read_bytes(), (self.source / "sample.png").read_bytes())
        self.assertEqual((clone / "Release/verification/raw.log").read_bytes(), log.read_bytes())
        attributes = subprocess.check_output(
            ["git", "-C", str(clone), "check-attr", "text", "eol", "--", "tracked.txt"],
            text=True,
        )
        self.assertIn("tracked.txt: text: auto", attributes)
        self.assertIn("tracked.txt: eol: lf", attributes)
        commit = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip()
        for autocrlf in ("true", "false"):
            subprocess.run(["git", "-C", str(clone), "config", "core.autocrlf", autocrlf], check=True)
            self.assertTrue(prepare_inventory.collect_source_status(clone, commit)["clean"], autocrlf)

        (clone / "Release/verification/raw.log").write_bytes(
            b"changed raw output\r\nwith trailing spaces   \r\n"
        )
        self.assertFalse(prepare_inventory.collect_source_status(clone, commit)["clean"])
        subprocess.run(
            ["git", "-C", str(clone), "checkout", "--", "Release/verification/raw.log"],
            check=True,
        )
        (clone / "sample.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00changed binary\r\n")
        self.assertFalse(prepare_inventory.collect_source_status(clone, commit)["clean"])
        subprocess.run(
            ["git", "-C", str(clone), "checkout", "--", "sample.png"], check=True
        )
        (clone / "tracked.txt").write_bytes(b"actual source modification\n")
        self.assertFalse(prepare_inventory.collect_source_status(clone, commit)["clean"])

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

    def test_original_notice_bytes_survive_autocrlf_checkout(self):
        relative = "Release/notice-supplement/originals/native/COPYING"
        original = b"Original upstream copyright\r\nLicensed as received.\r\n"
        notice = self.source / relative
        notice.parent.mkdir(parents=True)
        notice.write_bytes(original)
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.source), "commit", "-qm", "original notice"], check=True)
        clone = self.source.parent / "notice checkout"
        subprocess.run(["git", "clone", "-q", "--no-local", "-c", "core.autocrlf=true",
                        str(self.source), str(clone)], check=True)
        self.assertEqual((clone / relative).read_bytes(), original)

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
