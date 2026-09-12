"""Current native rows versus original published metadata, without binary downloads."""

import copy
import json
from pathlib import Path
import unittest
import shutil
import tempfile
import subprocess
import re
import source_publication as policy


class SourcePublicationTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).resolve().parents[2]
        self.index = policy.load(
            self.source / "Release/notice-supplement/SOURCE-INPUTS.json"
        )
        self.native = {"sourceCommit": "a" * 40, "files": [], "packages": {}}
        self.cache = {}
        self.payload = {}
        for owner in self.index["nativeOwners"]:
            self.cache[owner["binaryArchive"]] = owner["binaryArchiveSha256"]
            self.native["packages"][owner["package"]] = owner["version"]
            for row in policy.owner_file_proof(self.source, self.index, owner):
                self.native["files"].append(
                    {
                        **row,
                        "package": owner["package"],
                        "packageVersion": owner["version"],
                    }
                )
                self.payload[row["path"]] = policy.fingerprint(row)
        self.record = {"sourceCommit": "a" * 40, "releaseInput": self.payload}

    def check(self):
        return policy.validate_native_sources(
            self.source, self.native, self.cache, self.record
        )

    def test_complete_actual_original_and_separate_supplement_proof(self):
        result = self.check()
        self.assertEqual(result["native_owners"], 66)
        self.assertEqual(result["cargo_archives"], 359)
        self.assertEqual(result["original_notice_files"], 735)
        self.assertEqual(result["separate_source_assets"], 1)

    def test_current_owner_version_archive_and_runtime_mutations_fail(self):
        original = copy.deepcopy((self.native, self.cache, self.record))
        for mutation in ("owner", "version", "archive", "bytes", "unowned"):
            self.native, self.cache, self.record = copy.deepcopy(original)
            row = self.native["files"][0]
            if mutation == "owner":
                row["package"] = "foreign"
            if mutation == "version":
                row["packageVersion"] = "0"
            if mutation == "archive":
                self.cache[next(iter(self.cache))] = "0" * 64
            if mutation == "bytes":
                row["sha256"] = "0" * 64
                self.record["releaseInput"][row["path"]]["sha256"] = "0" * 64
            if mutation == "unowned":
                self.native["files"].append(
                    {"path": "bin/foreign.dll", "bytes": 1, "sha256": "0" * 64}
                )
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check()

    def test_changed_cargo_member_notice_and_missing_publication_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            for relative in ("Release/source-publication", "Release/notice-supplement"):
                shutil.copytree(self.source / relative, source / relative)
            index_path = source / "Release/notice-supplement/SOURCE-INPUTS.json"
            original = index_path.read_bytes()
            for mutation in ("cargo", "member", "recipe"):
                index = json.loads(original)
                if mutation == "cargo":
                    index["cargo"]["sources"][0]["sha256"] = "0" * 64
                if mutation == "member":
                    index["nativeSourceArchives"][0]["delivery"][
                        "member"
                    ] = "sources/foreign.tar"
                if mutation == "recipe":
                    index["nativeSourceArchives"][0]["recipeSha256"] = "0" * 64
                index_path.write_text(json.dumps(index))
                with self.subTest(mutation=mutation), self.assertRaises(
                    (ValueError, KeyError)
                ):
                    policy.validate_native_sources(
                        source, self.native, self.cache, self.record
                    )
            index_path.write_bytes(original)
            notice = json.loads(
                (source / "Release/notice-supplement/NOTICE-INDEX.json").read_text()
            )["files"][0]["path"]
            (source / "Release/notice-supplement" / notice).write_bytes(
                b"altered original"
            )
            with self.assertRaises(ValueError):
                policy.validate_native_sources(
                    source, self.native, self.cache, self.record
                )
            (
                source / "Release/source-publication/public-delivery-verification.json"
            ).unlink()
            with self.assertRaises(ValueError):
                policy.verify_public_sources(source, "a" * 40, lambda url: b"{}")

    def test_public_current_commit_and_tree_are_bound(self):
        commit = subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"], text=True
        ).strip()
        tree = subprocess.check_output(
            ["git", "-C", str(self.source), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
        root = self.source / policy.PUBLICATION
        assets = [policy.load(root / "public-delivery-verification.json")]
        assets.extend(
            x
            for x in policy.load(root / "tint-native-source-delivery.json")["artifacts"]
            if x["name"]
            in ("source-manifest.json", "pixelquay-native-sources-c9f4add.tar")
        )
        assets.extend(
            dict(url=x["delivery"]["url"], **policy.fingerprint(x))
            for x in self.index["nativeSourceArchives"]
            if x["delivery"]["kind"] == "published_source_asset"
        )
        responses = {}
        for asset in assets:
            match = re.fullmatch(
                r"https://github.com/(hashfunction/(?:inkquay|pixelquay))/releases/download/([^/]+)/([^/]+)",
                asset["url"],
            )
            endpoint = (
                f"https://api.github.com/repos/{match[1]}/releases/tags/{match[2]}"
            )
            response = responses.setdefault(
                endpoint, {"draft": False, "tag_name": match[2], "assets": []}
            )
            response["assets"].append(
                {
                    "name": match[3],
                    "size": asset["bytes"],
                    "digest": "sha256:" + asset["sha256"],
                    "browser_download_url": asset["url"],
                }
            )
        endpoint = (
            f"https://api.github.com/repos/hashfunction/inkquay/git/commits/{commit}"
        )
        responses[endpoint] = {"sha": commit, "tree": {"sha": tree}}
        fetch = lambda url: json.dumps(responses[url]).encode()
        self.assertEqual(
            policy.verify_public_sources(self.source, commit, fetch)[
                "application_tree"
            ],
            tree,
        )
        for field in ("commit", "tree"):
            responses[endpoint] = {"sha": commit, "tree": {"sha": tree}}
            if field == "commit":
                responses[endpoint]["sha"] = "0" * 40
            else:
                responses[endpoint]["tree"]["sha"] = "0" * 40
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "Public current application"
            ):
                policy.verify_public_sources(self.source, commit, fetch)

    def test_public_asset_exact_hash_size_and_visibility(self):
        asset = {
            "url": "https://github.com/hashfunction/inkquay/releases/download/tag/source.tar",
            "bytes": 9,
            "sha256": "a" * 64,
        }
        release = {
            "draft": False,
            "tag_name": "tag",
            "assets": [
                {
                    "name": "source.tar",
                    "size": 9,
                    "digest": "sha256:" + "a" * 64,
                    "browser_download_url": asset["url"],
                }
            ],
        }
        policy.validate_public_asset(asset, release)
        for field, value in (
            ("size", 10),
            ("digest", "sha256:" + "b" * 64),
            ("browser_download_url", "https://foreign/source.tar"),
        ):
            bad = copy.deepcopy(release)
            bad["assets"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                policy.validate_public_asset(asset, bad)
        release["draft"] = True
        with self.assertRaises(ValueError):
            policy.validate_public_asset(asset, release)


if __name__ == "__main__":
    unittest.main()
