"""Retain only the exact unsigned Store MSIX after both normal installed workflows.
Copyright 2026 Trieflow LLC. MIT. Store submission/certification remain separate.
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import msix_qualification as msix
import source_publication as publication
from source_publication import require, load
from store_workflow_evidence import validate_installation


def context(environment):
    require(
        environment.get("CI") == "true"
        and environment.get("GITHUB_REPOSITORY") == "hashfunction/inkquay"
        and environment.get("INKQUAY_CAPTURE_CRASH_STACK") == "false",
        "Unsigned retention requires normal current-repository Windows CI",
    )
    result = {
        key: environment.get(env)
        for key, env in [
            ("source_commit", "GITHUB_SHA"),
            ("workflow_run_id", "GITHUB_RUN_ID"),
            ("workflow_run_attempt", "GITHUB_RUN_ATTEMPT"),
        ]
    }
    require(
        re.fullmatch("[0-9a-f]{40}", result["source_commit"] or "") is not None
        and all(
            re.fullmatch("[1-9][0-9]*", result[key] or "")
            for key in ("workflow_run_id", "workflow_run_attempt")
        ),
        "Exact current source/run/attempt required",
    )
    return result


def clean_source(source, commit):
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(source), *args], text=True, timeout=30
        ).strip()

    require(
        git("rev-parse", "HEAD") == commit
        and not git("status", "--porcelain", "--untracked-files=all"),
        "Export requires exact clean source checkout",
    )


def retain_unsigned(package, output, receipt):
    package, output = Path(package), Path(output)
    require(not os.path.lexists(output), "Store output already exists; preserving it")
    require(
        msix.file_record(package) == receipt["store_package"],
        "Unsigned package changed before retention",
    )
    output.mkdir()
    target = output / msix.package_name("store")
    with msix._regular_stream(package) as original, target.open("xb") as destination:
        shutil.copyfileobj(original, destination, 1024 * 1024)
    require(
        msix.file_record(target)
        == receipt["store_package"]
        == msix.file_record(package),
        "Unsigned package changed during retention",
    )
    msix._write_new(output / "release-ready.json", msix._canonical_json(receipt))


def export(
    source, evidence, qualification, store, output, current, fetcher=publication.fetch
):
    source, evidence = Path(source), Path(evidence)
    require(not os.path.lexists(output), "Store output already exists")
    clean_source(source, current["source_commit"])
    before = msix.inventory_tree(evidence)
    records = {}
    results = {}
    packages = {}
    for mode, directory, label in (
        ("qualification", Path(qualification), "msix-install"),
        ("store", Path(store), "msix-store-install"),
    ):
        record_path = directory / "package-record.json"
        package = directory / msix.package_name(mode)
        record = load(record_path)
        records[mode] = record
        packages[mode] = package
        msix.verify_record_inputs(
            package,
            record_path,
            source / "build/dist",
            source / "ui/pixmaps/com.trieflow.inkquay.png",
            current["source_commit"],
            evidence / "package-inventory.json",
            evidence / "windows-startup.json",
            source,
            mode,
        )
        metadata = (
            "msix-package-record.json"
            if mode == "qualification"
            else "msix-store-package-record.json"
        )
        require(
            msix.file_record(evidence / metadata) == msix.file_record(record_path),
            "Retained package metadata differs from build output",
        )
        require(
            record["makeAppx"]
            == msix._tool_record(Path(record["makeAppx"]["path"]), "10.0.26100.0"),
            "SDK packer changed since exact packaging",
        )
        results[mode] = validate_installation(
            evidence / label, record, source, current, mode, Path(sys.executable).parent
        )
        sign = load(evidence / label / "installation-qualification.json")["signtool"]
        require(
            msix.file_record(Path(sign["path"])) == publication.fingerprint(sign),
            "SDK signing tool changed after qualification",
        )
    require(
        records["qualification"]["releaseInput"] == records["store"]["releaseInput"],
        "Identity modes did not package the same current native release",
    )
    native = load(source / "build/inkquay-windows-inventory.json")
    require(
        msix.file_record(source / "build/inkquay-windows-inventory.json")
        == load(evidence / "package-inventory.json")["nativeInventory"]
        and msix.file_record(evidence / "inkquay-windows-inventory.json")
        == msix.file_record(source / "build/inkquay-windows-inventory.json"),
        "Same-run native inventory differs",
    )
    cache = publication.parse_cache(
        (evidence / "msys2-cache-sha256.txt").read_text(encoding="utf-8-sig")
    )
    closure = publication.validate_native_sources(
        source, native, cache, records["store"]
    )
    public = publication.verify_public_sources(
        source, current["source_commit"], fetcher
    )
    require(
        msix.inventory_tree(evidence) == before,
        "Consumed qualification evidence changed during export verification",
    )
    clean_source(source, current["source_commit"])
    # Rebuild the expected payload again after network/evidence checks. Neither a
    # signed copy nor coherent replacement package+record can enter final output.
    for mode, directory in (
        ("qualification", Path(qualification)),
        ("store", Path(store)),
    ):
        msix.verify_record_inputs(
            packages[mode],
            directory / "package-record.json",
            source / "build/dist",
            source / "ui/pixmaps/com.trieflow.inkquay.png",
            current["source_commit"],
            evidence / "package-inventory.json",
            evidence / "windows-startup.json",
            source,
            mode,
        )
        require(
            load(directory / "package-record.json") == records[mode],
            "Package record changed during verification",
        )
    receipt = {
        "schema_version": 1,
        "product": "Scriblark",
        "version": "1.0.1.0",
        **current,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "identity": msix.STORE_IDENTITY,
        "unsigned": True,
        "store_identity_used": True,
        "both_installed_workflows_passed": True,
        "store_package": records["store"]["containerVerification"]["package"],
        "qualification_package": records["qualification"]["containerVerification"][
            "package"
        ],
        "installed_workflows": results,
        "qualification_evidence": before,
        "source_closure": closure,
        "source_publication": public,
        "license_clearance_claimed": False,
        "public_release": False,
        "submitted_to_store": False,
        "certification_passed": False,
        "diagnostic_observer": False,
        "certificate_private_key_exported": False,
    }
    retain_unsigned(packages["store"], output, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("qualification", "store", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    require(sys.platform == "win32", "Export requires actual Windows CI")
    source = Path(__file__).resolve().parents[2]
    export(
        source,
        source / "build-evidence",
        args.qualification,
        args.store,
        args.output,
        context(os.environ),
    )
    print(
        "PASS: retained exact unsigned Store package after both normal installed workflows and public source checks"
    )


if __name__ == "__main__":
    main()
