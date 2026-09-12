"""Recheck same-run source/stage/receipt/package binding before any install mutation.
Copyright 2026 Trieflow LLC. MIT.
"""

import argparse
from pathlib import Path
import subprocess

from msix_qualification import verify_record_inputs, verify_installed, _load_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--record", type=Path, required=True)
parser.add_argument("--package", type=Path, required=True)
parser.add_argument("--source-commit", required=True)
parser.add_argument("--installed-root", type=Path)
parser.add_argument(
    "--identity-mode", choices=("qualification", "store"), default="qualification"
)
args = parser.parse_args()
source = Path(__file__).resolve().parents[2]
actual = subprocess.run(
    ["git", "-C", str(source), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
if actual != args.source_commit:
    raise SystemExit("Source commit differs from this installation qualification run")
dirty = subprocess.run(
    ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
if dirty:
    raise SystemExit("Dirty source checkout cannot identify qualification inputs")
verify_record_inputs(
    args.package,
    args.record,
    source / "build/dist",
    source / "ui/pixmaps/com.trieflow.inkquay.png",
    actual,
    source / "build-evidence/package-inventory.json",
    source / "build-evidence/windows-startup.json",
    source,
    args.identity_mode,
)
if args.installed_root:
    verify_installed(
        args.installed_root,
        _load_json(args.record, "qualification record")["payload"],
        args.identity_mode,
    )
print(
    "PASS: exact source/stage/notices/startup/package binding reverified before installation"
)
