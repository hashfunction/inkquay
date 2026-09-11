"""Bind the complete stage to the same-run native provenance before startup.
Copyright 2026 Trieflow LLC. MIT.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from msix_qualification import create_input_inventory, _canonical_json, _write_new


MAX_RECORDED_STATUS_ENTRIES = 256


def _parse_porcelain_v1_z(raw):
    """Parse Git's stable, unquoted NUL-delimited status format."""
    if not raw:
        return []
    if not raw.endswith(b"\0"):
        raise ValueError("Malformed Git source-status output")
    fields = raw[:-1].split(b"\0")
    entries = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4 or field[2:3] != b" ":
            raise ValueError("Malformed Git source-status entry")
        try:
            status = field[:2].decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("Malformed Git source-status code") from error
        entry = {"status": status, "path": os.fsdecode(field[3:])}
        if "R" in status or "C" in status:
            if index >= len(fields):
                raise ValueError("Malformed Git rename/copy source-status entry")
            entry["originalPath"] = os.fsdecode(fields[index])
            index += 1
        entries.append(entry)
    return entries


def collect_source_status(source, source_commit):
    raw = subprocess.check_output(
        [
            "git",
            "-C",
            str(source),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ]
    )
    entries = _parse_porcelain_v1_z(raw)
    return {
        "schemaVersion": 1,
        "sourceCommit": source_commit,
        "clean": not entries,
        "statusBytes": len(raw),
        "statusSha256": hashlib.sha256(raw).hexdigest(),
        "statusEntryCount": len(entries),
        "entries": entries[:MAX_RECORDED_STATUS_ENTRIES],
        "entriesTruncated": len(entries) > MAX_RECORDED_STATUS_ENTRIES,
    }


def require_clean_source(source, source_commit, evidence_path):
    record = collect_source_status(source, source_commit)
    _write_new(evidence_path, _canonical_json(record))
    if not record["clean"]:
        rendered = json.dumps(record["entries"], ensure_ascii=True, separators=(",", ":"))
        suffix = " (additional entries omitted)" if record["entriesTruncated"] else ""
        raise ValueError(
            "Source checkout must be clean before collecting package inputs; "
            f"Git status entries: {rendered}{suffix}"
        )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("CI") != "true":
        parser.error("Requires a disposable Windows CI runner")
    source = Path(__file__).resolve().parents[2]
    actual = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != args.source_commit:
        raise ValueError("Native stage must identify the exact current source commit")
    require_clean_source(
        source, actual, source / "build-evidence/source-status.json"
    )
    record = create_input_inventory(source / "build/dist", source, actual)
    _write_new(
        source / "build-evidence/package-inventory.json", _canonical_json(record)
    )
    print(
        f'Bound {len(record["files"])} complete stage files to native/source provenance'
    )


if __name__ == "__main__":
    main()
