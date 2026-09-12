"""Exercise both fixed identities through real staged/container/install boundaries."""

import copy
import json
import unittest
import zipfile
import msix_qualification as msix
import test_msix_qualification as fixtures


class StoreIdentityTests(unittest.TestCase):
    setUp = fixtures.PackageTests.setUp
    refresh = fixtures.PackageTests.refresh

    def stage(self, mode):
        return msix.stage_release(
            self.release,
            self.artwork,
            self.root / mode,
            self.commit,
            self.inventory,
            self.startup,
            self.source,
            mode,
        )

    def package(self, mode):
        record = self.stage(mode)
        path = self.root / msix.package_name(mode)
        with zipfile.ZipFile(path, "w") as archive:
            for name in record["payload"]:
                archive.write(self.root / mode / name, name)
            for name in ("[Content_Types].xml", "AppxBlockMap.xml"):
                archive.writestr(name, b"<metadata/>")
        record["containerVerification"] = msix.verify_msix(
            path, record["payload"], mode
        )
        record["unpackedVerification"] = msix.verify_unpacked(
            self.root / mode, record["payload"], mode
        )
        return path, record

    def test_fixed_store_manifest_and_default_compatibility(self):
        self.assertEqual(
            msix.validate_manifest(msix.create_manifest()), msix.QUALIFICATION_IDENTITY
        )
        self.assertEqual(
            msix.validate_manifest(msix.create_manifest("store"), "store"),
            {
                **msix.QUALIFICATION_IDENTITY,
                "packageName": "1659hashfunction.InkQuay",
                "publisher": "CN=B6A2631A-FD32-45CC-AE12-82466975F528",
            },
        )
        self.assertIn(
            b"<PublisherDisplayName>hashfunction</PublisherDisplayName>",
            msix.create_manifest("store"),
        )
        for mode in ("arbitrary", "", None):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                msix.create_manifest(mode)

    def test_independent_manifest_mode_and_mutation_rejection(self):
        data = msix.create_manifest("store")
        with self.assertRaises(ValueError):
            msix.validate_manifest(data)
        for old, new in (
            (b"1659hashfunction.InkQuay", b"foreign"),
            (b"CN=B6A2631A-FD32-45CC-AE12-82466975F528", b"CN=foreign"),
            (b"1.0.1.0", b"1.0.0.0"),
            (b'Id="InkQuay"', b'Id="Scriblark"'),
            (b"bin/Scriblark.exe", b"bin/foreign.exe"),
            (b"hashfunction<", b"Other<"),
        ):
            with self.subTest(old=old), self.assertRaises(ValueError):
                msix.validate_manifest(data.replace(old, new), "store")

    def test_actual_store_container_unpacked_installed_and_record(self):
        path, record = self.package("store")
        self.assertFalse(record["qualificationIdentityOnly"])
        self.assertTrue(record["storeIdentityUsed"])
        for key in (
            "publicRelease",
            "signed",
            "licenseClearanceClaimed",
            "installationQualificationPassed",
        ):
            self.assertIs(record[key], False)
        for verify, target in (
            (msix.verify_msix, path),
            (msix.verify_unpacked, self.root / "store"),
            (msix.verify_installed, self.root / "store"),
        ):
            verify(target, record["payload"], "store")
            with self.assertRaises(ValueError):
                verify(target, record["payload"])
        record_path = self.root / "record.json"

        def check(value, mode="store"):
            record_path.write_text(json.dumps(value))
            return msix.verify_record_inputs(
                path,
                record_path,
                self.release,
                self.artwork,
                self.commit,
                self.inventory,
                self.startup,
                self.source,
                mode,
            )

        self.assertTrue(check(record))
        for field, value in (
            ("qualificationIdentityOnly", True),
            ("storeIdentityUsed", False),
            ("identityMode", "qualification"),
            ("signed", True),
            ("signed", 0),
        ):
            bad = copy.deepcopy(record)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                check(bad)
        with self.assertRaises(ValueError):
            check(record, "qualification")

    def test_coherent_signing_payload_is_rejected_before_staging(self):
        for name in ("AppxSignature.p7x", "key.pem", "signing.pfx"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                msix.assert_unsigned_payload({name: {"bytes": 1, "sha256": "0" * 64}})
        path = self.release / "key.pem"
        path.write_bytes(b"private signing material")
        with self.assertRaisesRegex(ValueError, "Signing/certificate"):
            self.stage("store")

    def test_unsigned_container_rejects_signing_material(self):
        path, record = self.package("store")
        original = path.read_bytes()
        for name in ("AppxSignature.p7x", "signing.pfx", "key.pem", "certificate.cer"):
            path.write_bytes(original)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr(name, b"foreign signing material")
            with self.subTest(name=name), self.assertRaises(ValueError):
                msix.verify_msix(path, record["payload"], "store")


if __name__ == "__main__":
    unittest.main()
