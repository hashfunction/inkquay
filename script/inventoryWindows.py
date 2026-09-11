#!/usr/bin/env python3
"""Inventory the actual native stage. Copyright 2026 Trieflow LLC, GPL-2.0-or-later."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def main():
    if sys.platform != 'win32' or not os.environ.get('MSYSTEM'):
        raise SystemExit('Run this inventory with native Python inside the Windows MSYS2 build environment.')
    stage, prefix, report = map(Path, sys.argv[1:])
    packages = dict(line.split(' ', 1) for line in subprocess.check_output(['pacman', '-Q'], text=True).splitlines())
    files = []
    for path in sorted(stage.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(stage)
        hashed = digest(path)
        source = prefix / relative
        record = {'path': relative.as_posix(), 'bytes': path.stat().st_size, 'sha256': hashed}
        if source.is_file() and digest(source) == hashed:
            record['sourcePath'] = str(source)
            owner = subprocess.run(['pacman', '-Qoq', os.environ['MSYSTEM_PREFIX'] + '/' + relative.as_posix()], capture_output=True, text=True)
            if owner.returncode == 0:
                package = owner.stdout.strip()
                record['package'] = package
                record['packageVersion'] = packages.get(package)
        if 'package' not in record:
            record['provenanceNote'] = 'Application/generated resource or copied data without a matched package owner; review against build and license inputs.'
        files.append(record)
    result = {
        'schemaVersion': 1,
        'recordedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sourceCommit': subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[1]), 'rev-parse', 'HEAD'], text=True).strip(),
        'platform': sys.platform, 'msystem': os.environ['MSYSTEM'], 'packages': packages,
        'files': files, 'licenseAuditComplete': False,
        'remainingGates': ['Audit every emitted library/resource and its corresponding source obligations', 'Execute the staged application and PDF/pen tests', 'Validate final MSIX identity, installation, signing and certification'],
        'omitted': ['LuaGObject and plugins', 'Audio support', 'GTKSourceView and GTK demo applications'],
    }
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
