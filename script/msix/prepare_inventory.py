"""Bind the complete stage to the same-run native provenance before startup.
Copyright 2026 Trieflow LLC. MIT.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from msix_qualification import create_input_inventory, _canonical_json, _write_new


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
    if subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
        text=True,
    ).strip():
        raise ValueError(
            "Source checkout must be clean before collecting package inputs"
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
