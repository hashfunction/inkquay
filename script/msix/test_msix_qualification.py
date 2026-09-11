"""InkQuay package boundaries with real files and ZIPs; no Windows claim."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

try:
    import msix_qualification as msix
except ImportError:
    msix = None


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(msix, "InkQuay MSIX qualification is not implemented")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.source = self.root / "source"
        self.release = self.root / "release"
        self.commit = "a" * 40
        self.inventory = self.root / "inputs.json"
        self.startup = self.root / "startup.json"
        actual = Path(__file__).resolve().parents[2]
        for relative in msix.SOURCE_FILES:
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((actual / relative).read_bytes())
        for relative in msix.REQUIRED_RELEASE_FILES:
            target = self.release / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            original = msix.SOURCE_COPIES.get(relative)
            target.write_bytes(
                (self.source / original).read_bytes()
                if original
                else (relative + " native fixture").encode()
            )
        self.artwork = self.source / "ui/pixmaps/com.trieflow.inkquay.png"
        self.native = self.source / "build/inkquay-windows-inventory.json"
        self.native.parent.mkdir(parents=True)
        files = msix.inventory_tree(self.release)
        rows = [
            {
                "path": name,
                **record,
                "package": "mingw-w64-x86_64-fixture",
                "packageVersion": "1.0",
            }
            for name, record in files.items()
        ]
        for row in rows:
            if row["path"] in ("bin/inkquay.exe", "bin/inkquay-wrapper.exe"):
                del row["package"]
                del row["packageVersion"]
        self.native.write_text(
            json.dumps(
                {
                    "schemaVersion": 3,
                    "sourceCommit": self.commit,
                    "platform": "win32",
                    "msystem": "MINGW64",
                    "packages": {"mingw-w64-x86_64-fixture": "1.0"},
                    "files": rows,
                    "builtApplication": {"sha256": files["bin/inkquay.exe"]["sha256"]},
                    "builtWrapper": {
                        "sha256": files["bin/inkquay-wrapper.exe"]["sha256"]
                    },
                    "licenseAuditComplete": False,
                }
            )
        )
        self.refresh()

    def refresh(self):
        d = msix.create_input_inventory(self.release, self.source, self.commit)
        self.inventory.write_text(json.dumps(d))
        self.startup.write_text(
            json.dumps(
                {
                    "source_commit": self.commit,
                    "windows_native_startup": True,
                    "window_title": "Unsaved Document - InkQuay",
                    "executable_sha256": d["files"]["bin/inkquay.exe"]["sha256"],
                    "package_inventory_sha256": digest(self.inventory.read_bytes())[
                        "sha256"
                    ],
                }
            )
        )

    def stage(self):
        return msix.stage_release(
            self.release,
            self.artwork,
            self.root / "stage",
            self.commit,
            self.inventory,
            self.startup,
            self.source,
        )

    def test_complete_stage_preserves_inputs_and_false_release_claims(self):
        d = self.stage()
        self.assertEqual(d["releaseInput"], msix.inventory_tree(self.release))
        self.assertEqual(d["payload"], msix.inventory_tree(self.root / "stage"))
        self.assertEqual(d["identity"]["executable"], "bin/inkquay.exe")
        self.assertFalse(d["publicRelease"])
        self.assertFalse(d["licenseClearanceClaimed"])
        self.assertEqual(d["runtime"]["gtk"], "bin/libgtk-3-0.dll")

    def test_native_inventory_rejects_missing_extra_duplicate_and_changed_files(self):
        original = self.native.read_text()
        for kind in (
            "missing",
            "extra",
            "duplicate",
            "changed",
            "wrong-source",
            "wrong-version",
            "unowned",
            "wrong-build",
        ):
            with self.subTest(kind=kind):
                d = json.loads(original)
                if kind == "missing":
                    d["files"].pop()
                elif kind == "extra":
                    d["files"].append(
                        {
                            "path": "bin/extra.dll",
                            **digest(b"fake"),
                            "package": "mingw-w64-x86_64-fixture",
                            "packageVersion": "1.0",
                        }
                    )
                elif kind == "duplicate":
                    d["files"].append(dict(d["files"][0]))
                elif kind == "changed":
                    d["files"][0]["sha256"] = "0" * 64
                elif kind == "wrong-source":
                    d["sourceCommit"] = "b" * 40
                elif kind == "wrong-version":
                    d["packages"]["mingw-w64-x86_64-fixture"] = "2.0"
                elif kind == "unowned":
                    row = next(
                        r for r in d["files"] if r["path"] == "bin/libgtk-3-0.dll"
                    )
                    del row["package"]
                else:
                    d["builtWrapper"]["sha256"] = "0" * 64
                self.native.write_text(json.dumps(d))
                with self.assertRaises(ValueError):
                    msix.create_input_inventory(self.release, self.source, self.commit)
        self.native.write_text(original)

    def test_original_notice_and_artwork_changes_are_rejected(self):
        for staged, source in msix.SOURCE_COPIES.items():
            with self.subTest(source=source):
                p = self.release / staged
                old = p.read_bytes()
                p.write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    msix.create_input_inventory(self.release, self.source, self.commit)
                p.write_bytes(old)

    def test_detailed_upstream_attribution_is_preserved_and_required(self):
        relative = "share/inkquay/licenses/copyright.txt"
        original = Path(__file__).resolve().parents[2] / "copyright.txt"
        expected = original.read_bytes()
        self.assertIn(b"Nararyans R.I.", expected)
        self.assertIn(b"Lucide Contributors", expected)
        self.assertIn(b"CC-BY-SA-4.0", expected)
        self.assertEqual((self.release / relative).read_bytes(), expected)
        package, record = self.package()
        self.assertEqual(record["sourceInputs"]["copyright.txt"], digest(expected))
        with zipfile.ZipFile(package) as archive:
            self.assertEqual(archive.read(relative), expected)

        # Neither a missing notice nor a consistently rehashed generic GPL
        # summary may replace the detailed copyright and asset attribution.
        for replacement in (None, (self.source / "debian/copyright").read_bytes()):
            with self.subTest(replacement="missing" if replacement is None else "generic"):
                target = self.release / relative
                if replacement is None:
                    target.unlink()
                else:
                    target.write_bytes(replacement)
                native = json.loads(self.native.read_text())
                native["files"] = [r for r in native["files"] if r["path"] != relative]
                if replacement is not None:
                    native["files"].append({"path": relative, **digest(replacement)})
                self.native.write_text(json.dumps(native))
                with self.assertRaisesRegex(ValueError, "Missing|notice/artwork"):
                    msix.create_input_inventory(self.release, self.source, self.commit)

    def test_actual_package_notice_copy_preserves_detailed_source_bytes(self):
        actual = Path(__file__).resolve().parents[2]
        script = (actual / "windows-setup/package.sh").read_text()
        copy_commands = [
            line for line in script.splitlines()
            if line.startswith('cp "$script_dir/../LICENSE"')
        ]
        self.assertEqual(len(copy_commands), 1)
        setup = self.root / "package stage with spaces"
        destination = setup / "share/inkquay/licenses"
        destination.mkdir(parents=True)
        # Run the actual source-notice copy command with only its input/output
        # directories adapted; do not run native package/build work on macOS.
        if sys.platform == "win32":
            # The qualification records the MINGW64 Python executable. Select
            # that same MSYS2 installation's bash, never a PATH WSL launcher.
            bash = Path(sys.executable).resolve().parents[2] / "usr/bin/bash.exe"
            self.assertTrue(bash.is_file(), "Expected the qualified MSYS2 bash")
            directories = 'script_dir=$(cygpath -u "$1"); setup_dir=$(cygpath -u "$2"); '
        else:
            bash = "bash"
            directories = 'script_dir=$1; setup_dir=$2; '
        subprocess.run(
            [str(bash), "-c", directories + copy_commands[0],
             "notice-copy", str(actual / "windows-setup"), str(setup)],
            check=True,
        )
        for name, source in (("copyright", "debian/copyright"), ("copyright.txt", "copyright.txt")):
            self.assertEqual((destination / name).read_bytes(), (actual / source).read_bytes())

    def test_startup_source_title_inventory_and_executable_are_bound(self):
        old = self.startup.read_text()
        for key, value in [
            ("source_commit", "b" * 40),
            ("window_title", "Xournal++"),
            ("package_inventory_sha256", "0" * 64),
            ("executable_sha256", "0" * 64),
            ("windows_native_startup", False),
        ]:
            d = json.loads(old)
            d[key] = value
            self.startup.write_text(json.dumps(d))
            with self.assertRaises(ValueError):
                self.stage()
        self.startup.write_text(old)

    def test_existing_stage_preserves_previous_bytes(self):
        p = self.root / "stage"
        p.mkdir()
        (p / "old").write_bytes(b"old")
        with self.assertRaises(ValueError):
            self.stage()
        self.assertEqual((p / "old").read_bytes(), b"old")

    def test_stage_mutation_after_receipt_is_rejected(self):
        (self.release / "extra.txt").write_bytes(b"extra")
        with self.assertRaises(ValueError):
            self.stage()

    def test_manifest_identity_and_capability_are_semantic(self):
        data = msix.create_manifest()
        msix.validate_manifest(data)
        for old, new in [
            (b"CN=InkQuay-CI-Qualification", b"CN=Other"),
            (b"bin/inkquay.exe", b"bin/other.exe"),
            (b"runFullTrust", b"internetClient"),
        ]:
            self.assertIn(old, data)
            with self.assertRaises(ValueError):
                msix.validate_manifest(data.replace(old, new))

    def test_zip_and_unpacked_byte_verification(self):
        record = self.stage()
        stage = self.root / "stage"
        p = self.root / "test.msix"
        with zipfile.ZipFile(p, "w") as z:
            for name in record["payload"]:
                z.write(stage / name, name)
            z.writestr("AppxBlockMap.xml", b"metadata")
            z.writestr("[Content_Types].xml", b"metadata")
        self.assertEqual(
            msix.verify_msix(p, record["payload"])["verifiedPayloadFiles"],
            len(record["payload"]),
        )
        msix.verify_unpacked(stage, record["payload"])
        with zipfile.ZipFile(p, "a") as z:
            z.writestr("bin/unexpected.dll", b"foreign")
        with self.assertRaises(ValueError):
            msix.verify_msix(p, record["payload"])

    def test_windows_path_alias_and_traversal_rejection(self):
        for p in (
            "../escape",
            "bin/CON.dll",
            "bin/with.",
            "bin/with ",
            "C:/file",
            "bin/a:b",
        ):
            with self.assertRaises(ValueError):
                msix._checked_path(p)
        seen = {}
        msix._register_path("bin/A.dll", seen)
        with self.assertRaises(ValueError):
            msix._register_path("bin/a.dll", seen)

    def package(self):
        record = self.stage()
        path = self.root / "fixture.msix"
        with zipfile.ZipFile(path, "w") as archive:
            for relative in record["payload"]:
                archive.write(self.root / "stage" / relative, relative)
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("AppxBlockMap.xml", "<BlockMap/>")
        record["unpackedVerification"] = msix.verify_unpacked(
            self.root / "stage", record["payload"]
        )
        return path, record

    def test_exact_container_and_unpacked_payload_match(self):
        package, record = self.package()
        self.assertEqual(
            msix.verify_msix(package, record["payload"])["verifiedPayloadFiles"],
            len(record["payload"]),
        )
        self.assertEqual(
            msix.verify_unpacked(self.root / "stage", record["payload"])[
                "verifiedPayloadFiles"
            ],
            len(record["payload"]),
        )

    def test_installed_inventory_allows_only_signature_metadata_beyond_payload(self):
        record = self.stage()
        stage = self.root / "stage"
        (stage / "AppxSignature.p7x").write_bytes(b"ephemeral signing metadata fixture")
        self.assertEqual(
            msix.verify_installed(stage, record["payload"])["verifiedPayloadFiles"],
            len(record["payload"]),
        )
        (stage / "unexpected-resource.txt").write_bytes(
            b"unrecorded installed resource"
        )
        with self.assertRaises(ValueError):
            msix.verify_installed(stage, record["payload"])

    def test_install_preflight_rejects_coherently_rehashed_package_record(self):
        package, record = self.package()
        record_path = self.root / "package-record.json"
        record["containerVerification"] = msix.verify_msix(package, record["payload"])
        record_path.write_text(json.dumps(record))
        self.assertTrue(
            msix.verify_record_inputs(
                package,
                record_path,
                self.release,
                self.artwork,
                self.commit,
                self.inventory,
                self.startup,
                self.source,
            )
        )
        # An internally consistent hash/record cannot substitute another input revision.
        record["sourceCommit"] = "b" * 40
        record_path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            msix.verify_record_inputs(
                package,
                record_path,
                self.release,
                self.artwork,
                self.commit,
                self.inventory,
                self.startup,
                self.source,
            )
        record["sourceCommit"] = self.commit
        record["runtime"] = {}
        record_path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            msix.verify_record_inputs(
                package,
                record_path,
                self.release,
                self.artwork,
                self.commit,
                self.inventory,
                self.startup,
                self.source,
            )

    def test_opc_decodes_once_and_accepts_exact_bytes(self):
        package, record = self.package()
        for encoded, decoded in [
            ("libc%2B%2B.dll", "libc++.dll"),
            ("literal%2520.txt", "literal%20.txt"),
            ("R%C3%A9sum%C3%A9.txt", "Résumé.txt"),
        ]:
            data = b"fixture bytes"
            with zipfile.ZipFile(package, "a") as archive:
                archive.writestr(encoded, data)
            record["payload"][decoded] = digest(data)
        msix.verify_msix(package, record["payload"])

    def test_opc_alias_traversal_bad_utf8_and_special_paths_rejected(self):
        package, record = self.package()
        for name in (
            "bin/%69nkquay.exe",
            "BIN/INKQUAY.EXE",
            "_internal%2fescape.dll",
            "_internal%5cescape.dll",
            "%2e%2e/escape",
            "/absolute",
            "C:evil",
            "x%FF",
            "x%GG",
            "x%00",
            "CON.txt",
            "name.",
            "empty//name",
        ):
            changed = self.root / "changed.msix"
            shutil.copyfile(package, changed)
            with zipfile.ZipFile(changed, "a") as archive:
                archive.writestr(name, b"extra")
            with self.subTest(name=name), self.assertRaises(ValueError):
                msix.verify_msix(changed, record["payload"])

    def test_zip_link_and_unexpected_empty_directory_rejected(self):
        package, record = self.package()
        for name, mode in [("redirect", 0o120777), ("unreviewed/", 0o40755)]:
            changed = self.root / "changed.msix"
            shutil.copyfile(package, changed)
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            with zipfile.ZipFile(changed, "a") as archive:
                archive.writestr(info, b"")
            with self.assertRaises(ValueError):
                msix.verify_msix(changed, record["payload"])

    def test_manifest_semantics_independent_of_coherent_hashes(self):
        package, record = self.package()
        for before, after in [
            (b"runFullTrust", b"internetClient"),
            (b"bin/inkquay.exe", b"other.exe"),
            (b"CN=InkQuay-CI-Qualification", b"CN=foreign"),
        ]:
            data = (
                (self.root / "stage/AppxManifest.xml")
                .read_bytes()
                .replace(before, after)
            )
            with self.assertRaises(ValueError):
                msix.validate_manifest(data)
        root = self.root / "stage"
        (root / "AppxManifest.xml").write_bytes(data)
        record["payload"]["AppxManifest.xml"] = digest(data)
        with self.assertRaises(ValueError):
            msix.verify_unpacked(root, record["payload"])

    def test_exact_sdk_semantic_pack_unpack_and_tool_integrity(self):
        sdk = self.root / "Windows Kits/10/bin/10.0.26100.0/x64"
        sdk.mkdir(parents=True)
        tool = sdk / "makeappx.exe"
        tool.write_bytes(b"fixture tool")
        commands = []

        def runner(command):
            commands.append(command)
            p = Path(command[command.index("/p") + 1])
            d = Path(command[command.index("/d") + 1])
            if command[1] == "pack":
                with zipfile.ZipFile(p, "w") as z:
                    for f in d.rglob("*"):
                        if f.is_file():
                            z.write(f, f.relative_to(d).as_posix())
                    z.writestr("[Content_Types].xml", "<Types/>")
                    z.writestr("AppxBlockMap.xml", "<BlockMap/>")
            else:
                with zipfile.ZipFile(p) as z:
                    z.extractall(d)

        output = self.root / "package-output"
        msix.build_qualification(
            self.release,
            self.artwork,
            self.commit,
            tool,
            "10.0.26100.0",
            output,
            self.inventory,
            self.startup,
            self.source,
            runner,
        )
        self.assertEqual([c[1] for c in commands], ["pack", "unpack"])
        self.assertNotIn("/nv", commands[0])
        self.assertNotIn("/o", commands[0])
        self.assertIn("/v", commands[0])
        record = json.loads((output / "package-record.json").read_text())
        self.assertFalse(record["signed"])
        self.assertFalse(record["installationQualificationPassed"])
        self.assertEqual(
            record["makeAppx"]["sha256"], digest(tool.read_bytes())["sha256"]
        )
        with self.assertRaises(ValueError):
            msix._tool_record(tool, "10.0.22621.0")

    def test_sdk_tool_change_aborts_without_publishing_output(self):
        sdk = self.root / "Windows Kits/10/bin/10.0.26100.0/x64"
        sdk.mkdir(parents=True)
        tool = sdk / "makeappx.exe"
        tool.write_bytes(b"original SDK tool")

        def changing_tool(command):
            tool.write_bytes(b"changed SDK tool")

        output = self.root / "package-output"
        with self.assertRaisesRegex(ValueError, "MakeAppx changed"):
            msix.build_qualification(
                self.release,
                self.artwork,
                self.commit,
                tool,
                "10.0.26100.0",
                output,
                self.inventory,
                self.startup,
                self.source,
                changing_tool,
            )
        self.assertFalse(output.exists())

    def test_install_preflight_requires_exact_typed_unpack_evidence(self):
        package, record = self.package()
        record["containerVerification"] = msix.verify_msix(package, record["payload"])
        record_path = self.root / "package-record.json"
        count = len(record["payload"])
        for value in [
            None,
            {},
            {"verifiedPayloadFiles": 0},
            {"verifiedPayloadFiles": str(count)},
            {"verifiedPayloadFiles": float(count)},
            {"verifiedPayloadFiles": True},
            {"verifiedPayloadFiles": count, "unexpected": True},
        ]:
            with self.subTest(value=value):
                altered = copy.deepcopy(record)
                if value is None:
                    del altered["unpackedVerification"]
                else:
                    altered["unpackedVerification"] = value
                record_path.write_text(json.dumps(altered))
                with self.assertRaisesRegex(ValueError, "unpack"):
                    msix.verify_record_inputs(
                        package,
                        record_path,
                        self.release,
                        self.artwork,
                        self.commit,
                        self.inventory,
                        self.startup,
                        self.source,
                    )

    def test_different_valid_artwork_cannot_replace_source_artwork(self):
        alternative = self.root / "other.png"
        alternative.write_bytes(msix.resize_png(self.artwork.read_bytes(), 50))
        self.assertNotEqual(
            digest(alternative.read_bytes()), digest(self.artwork.read_bytes())
        )
        with self.assertRaisesRegex(ValueError, "artwork"):
            msix.stage_release(
                self.release,
                alternative,
                self.root / "stage",
                self.commit,
                self.inventory,
                self.startup,
                self.source,
            )


if __name__ == "__main__":
    unittest.main()
