"""Exact shipped native bytes and original notices versus reachable preferred-form source.
Copyright 2026 Trieflow LLC. MIT. Historical collection facts remain historical.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.request import Request, urlopen
import msix_qualification as msix

REPOSITORY = "hashfunction/inkquay"
PUBLICATION = "Release/source-publication"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(row):
    return {key: row[key] for key in ("bytes", "sha256")}


def load(path):
    return msix._load_json(path, "source/publication evidence")


def unique(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), "Duplicate source/provenance rows")
    return result


def owner_file_proof(source, index, owner):
    if owner["package"] == "mingw-w64-x86_64-libwinpthread":
        item = next(
            x
            for x in index["nativeSourceArchives"]
            if x["filename"] == owner["sourceArchive"]
        )
        evidence = item["supplementEvidence"]
        require(
            evidence["binaryMetadata"]["package"] == owner["package"]
            and evidence["binaryMetadata"]["version"] == owner["version"]
            and evidence["binaryMetadata"]["pkgbuildSha256sum"]
            == owner["binaryRecipeHash"]
            == item["recipeSha256"],
            "Separate winpthread binary/source recipe mismatch",
        )
        return [
            evidence["runtime"],
            *[
                dict(path=path, **fingerprint(evidence["copiedNotice"]))
                for path in evidence["copiedNotice"]["paths"]
            ],
        ]
    root = Path(source) / PUBLICATION
    relative = "binary-metadata/" + owner["package"] + "/evidence.json"
    proof = load(root / relative)
    delivery = unique(load(root / "delivery-files.json")["files"], "path")
    require(
        msix.file_record(root / relative) == fingerprint(delivery[relative]),
        "Original binary proof differs from published collection",
    )
    for key in ("package", "version", "pkgbase", "binaryArchive"):
        require(proof[key] == owner[key], "Original binary owner mismatch: " + key)
    require(
        proof["sha256"] == owner["binaryArchiveSha256"]
        and proof["pkgbuildSha256"] == owner["binaryRecipeHash"]
        and proof["binaryHashMatchesNativeRun"] is True,
        "Original binary archive/recipe proof mismatch",
    )
    return proof["shippedFiles"]


def validate_native_sources(source, native, cache, record):
    source = Path(source)
    root = source / PUBLICATION
    index = load(source / msix.NOTICE_SOURCE / "SOURCE-INPUTS.json")
    original = load(root / "source-manifest.json")
    delivery = load(root / "delivery-files.json")
    files = unique(delivery["files"], "path")
    require(
        delivery["fileCount"] == len(files)
        and msix.file_record(root / "source-manifest.json")
        == fingerprint(files["source-manifest.json"])
        and msix.file_record(root / "source-manifest.json")["sha256"]
        == index["collection"]["manifestSha256"],
        "Original source collection/manifest membership changed",
    )
    old_owners = unique(original["nativeOwners"], "package")
    sources = unique(index["nativeSourceArchives"], "filename")
    owners = unique(index["nativeOwners"], "package")
    require(
        len(owners) == 66 and len(sources) == 66,
        "Incomplete reviewed native source set",
    )
    tint = load(root / "tint-native-source-delivery.json")
    tint_manifest = load(root / "tint-source-manifest.json")
    tint_asset = next(
        x for x in tint["artifacts"] if x["name"] == "source-manifest.json"
    )
    require(
        msix.file_record(root / "tint-source-manifest.json") == fingerprint(tint_asset)
        and tint_asset["unauthenticatedDownloadVerified"] is True,
        "Related original collection manifest differs",
    )
    tint_files = unique(tint_manifest["archives"], "archive")
    separate = 0
    for owner in owners.values():
        item = sources[owner["sourceArchive"]]
        require(
            item["pkgbase"] == owner["pkgbase"]
            and item["version"] == owner["version"]
            and item["recipeSha256"] == owner["binaryRecipeHash"],
            "Source does not match exact binary recipe/version",
        )
        require(
            cache.get(owner["binaryArchive"]) == owner["binaryArchiveSha256"],
            "Current cached native archive differs: " + owner["package"],
        )
        kind = item["delivery"]["kind"]
        if kind == "published_source_asset":
            require(
                owner["package"] == "mingw-w64-x86_64-libwinpthread",
                "Unreviewed separate source asset",
            )
            supplement = item["supplementEvidence"]
            for field, name in (
                ("publicationProof", "tint-native-source-supplement-publication.json"),
                ("retainedSourceProof", "tint-source-supplements.json"),
            ):
                require(
                    msix.file_record(root / name) == fingerprint(supplement[field]),
                    "Separate preferred-form/publication proof changed",
                )
            separate += 1
        else:
            require(
                all(
                    old_owners[owner["package"]][key] == value
                    for key, value in owner.items()
                ),
                "Current owner differs from original source proof",
            )
            if kind == "included":
                require(
                    fingerprint(files[item["delivery"]["path"]]) == fingerprint(item),
                    "Included source archive differs from original collection",
                )
            elif kind == "existing_source_collection":
                require(
                    fingerprint(tint_files[item["delivery"]["member"]])
                    == fingerprint(item),
                    "Related source archive membership differs",
                )
                asset = next(
                    x for x in tint["artifacts"] if x["url"] == item["delivery"]["url"]
                )
                require(
                    asset["bytes"] == item["delivery"]["collectionBytes"]
                    and asset["sha256"] == item["delivery"]["collectionSha256"]
                    and asset["unauthenticatedDownloadVerified"] is True,
                    "Related collection publication differs",
                )
            else:
                raise ValueError("Unreviewed source delivery kind")
    require(separate == 1, "Current separate source supplement missing")
    proof_files = {
        owner["package"]: unique(owner_file_proof(source, index, owner), "path")
        for owner in owners.values()
    }
    require(
        native["sourceCommit"] == record["sourceCommit"],
        "Native inventory source differs",
    )
    observed = set()
    seen = set()
    for row in native["files"]:
        path = row["path"]
        require(path not in seen, "Duplicate current native file")
        seen.add(path)
        require(
            record["releaseInput"].get(path) == fingerprint(row),
            "Current native payload hash differs",
        )
        package = row.get("package")
        if package:
            require(
                package in owners
                and row["packageVersion"]
                == native["packages"].get(package)
                == owners[package]["version"],
                "Current native owner/version differs",
            )
            require(
                path in proof_files[package]
                and fingerprint(proof_files[package][path]) == fingerprint(row),
                "Current owned file differs from exact published binary/source proof: "
                + path,
            )
            observed.add(package)
        elif PurePosixPath(path).suffix.lower() in (".dll", ".exe"):
            require(
                path in ("bin/Scriblark.exe", "bin/Scriblark-wrapper.exe"),
                "Native binary has no source owner: " + path,
            )
    require(observed == set(owners), "Current shipped source-owner closure differs")
    cargo = index["cargo"]
    require(len(cargo["sources"]) == 359, "Incomplete resolved Cargo source delivery")
    for item in cargo["sources"]:
        require(
            fingerprint(files[item["path"]]) == fingerprint(item),
            "Cargo source archive differs: " + item["name"],
        )
    require(
        fingerprint(files[cargo["sourceCollectionLockPath"]]) == cargo["resolvedLock"],
        "Published resolved Cargo lock differs",
    )
    notices = load(source / msix.NOTICE_SOURCE / "NOTICE-INDEX.json")
    msix.notice_sources(source)
    for item in notices["files"]:
        require(
            fingerprint(files[item["retainedSourcePath"]]) == fingerprint(item),
            "Original notice is absent from source collection",
        )
    require(notices["fileCount"] == 735, "Incomplete original notices")
    return {
        "native_owners": len(observed),
        "native_files": sum(bool(r.get("package")) for r in native["files"]),
        "cargo_archives": 359,
        "original_notice_files": 735,
        "separate_source_assets": separate,
        "binary_reproduction_claimed": False,
        "license_conversion_applied": False,
    }


def parse_cache(data):
    result = {}
    for line in data.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", line)
        require(match is not None, "Malformed same-run cached archive hash")
        name = PurePosixPath(match[2].replace("\\", "/")).name
        require(name not in result, "Duplicate cached archive name")
        result[name] = match[1]
    return result


def validate_public_asset(asset, release):
    match = re.fullmatch(
        r"https://github.com/(hashfunction/(?:inkquay|pixelquay))/releases/download/([^/]+)/([^/]+)",
        asset["url"],
    )
    require(match is not None, "Unexpected source publication endpoint")
    rows = [x for x in release["assets"] if x["name"] == match[3]]
    require(
        release["draft"] is False
        and release["tag_name"] == match[2]
        and len(rows) == 1
        and rows[0]["size"] == asset["bytes"]
        and rows[0]["digest"] == "sha256:" + asset["sha256"]
        and rows[0]["browser_download_url"] == asset["url"],
        "Source asset is unavailable or differs from retained verified bytes",
    )


def fetch(url, limit=4 * 1024 * 1024):
    require(
        url.startswith(("https://api.github.com/", "https://github.com/")),
        "Unexpected publication host",
    )
    with urlopen(
        Request(
            url,
            headers={
                "User-Agent": "Scriblark-source-verification",
                "Accept": "application/vnd.github+json",
            },
        ),
        timeout=45,
    ) as response:
        require(response.status == 200, "Source endpoint unavailable")
        body = response.read(limit + 1)
    require(len(body) <= limit, "Source metadata exceeds bound")
    return body


def verify_public_sources(source, commit, fetcher=fetch):
    source = Path(source)
    root = source / PUBLICATION
    original = load(root / "public-delivery-verification.json")
    require(
        original["authenticated"] is False
        and original["all_members_match_local_manifest"] is True
        and original["members_verified"] == 1711,
        "Original anonymous full collection verification missing",
    )
    assets = [original]
    tint = load(root / "tint-native-source-delivery.json")
    assets.extend(
        x
        for x in tint["artifacts"]
        if x["name"] in ("source-manifest.json", "pixelquay-native-sources-c9f4add.tar")
    )
    index = load(source / msix.NOTICE_SOURCE / "SOURCE-INPUTS.json")
    for item in index["nativeSourceArchives"]:
        if item["delivery"]["kind"] == "published_source_asset":
            assets.append(dict(url=item["delivery"]["url"], **fingerprint(item)))
    releases = {}
    for asset in assets:
        match = re.fullmatch(
            r"https://github.com/(hashfunction/(?:inkquay|pixelquay))/releases/download/([^/]+)/([^/]+)",
            asset["url"],
        )
        require(match is not None, "Unexpected source asset URL")
        endpoint = f"https://api.github.com/repos/{match[1]}/releases/tags/{match[2]}"
        if endpoint not in releases:
            releases[endpoint] = json.loads(fetcher(endpoint))
        validate_public_asset(asset, releases[endpoint])
    public = json.loads(
        fetcher(f"https://api.github.com/repos/{REPOSITORY}/git/commits/{commit}")
    )
    tree = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", commit + "^{tree}"],
        text=True,
        timeout=30,
    ).strip()
    require(
        public["sha"] == commit and public["tree"]["sha"] == tree,
        "Public current application commit/tree differs",
    )
    return {
        "anonymous": True,
        "application_commit": commit,
        "application_tree": tree,
        "application_source_url": f"https://github.com/{REPOSITORY}/tree/{commit}",
        "application_archive_url": f"https://github.com/{REPOSITORY}/archive/{commit}.tar.gz",
        "assets": [dict(url=x["url"], **fingerprint(x)) for x in assets],
        "large_archive_download_repeated": False,
    }
