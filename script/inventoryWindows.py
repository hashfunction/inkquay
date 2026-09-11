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


def package_file_owners(listing):
    owners = {}
    for line in listing.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) != 2 or not fields[1].startswith('/'):
            raise ValueError('Malformed pacman file listing')
        package, path = fields
        owners.setdefault(path, set()).add(package)
    return owners


def inventory_files(stage, prefix, msys_prefix, packages, owners):
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
            candidates = owners.get(msys_prefix.rstrip('/') + '/' + relative.as_posix(), set())
            if len(candidates) == 1:
                package = next(iter(candidates))
                if package not in packages:
                    raise ValueError('File owner was absent from the installed package snapshot: ' + package)
                record['package'] = package
                record['packageVersion'] = packages[package]
            elif candidates:
                record['ambiguousPackageOwners'] = sorted(candidates)
        if 'package' not in record:
            record['provenanceNote'] = 'Application/generated resource or copied data without a matched package owner; review against build and license inputs.'
        files.append(record)
    return files


def main():
    if sys.platform != 'win32' or not os.environ.get('MSYSTEM'):
        raise SystemExit('Run this inventory with native Python inside the Windows MSYS2 build environment.')
    stage, prefix, report = map(Path, sys.argv[1:])
    source_commit = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[1]), 'rev-parse', 'HEAD'], text=True).strip()
    packages = dict(line.split(' ', 1) for line in subprocess.check_output(['pacman', '-Q'], text=True, encoding='utf-8').splitlines())
    # One installed-file snapshot replaces a process launch for every copied icon
    # and DLL. Byte comparisons still decide whether package provenance applies.
    owners = package_file_owners(subprocess.check_output(['pacman', '-Ql'], text=True, encoding='utf-8'))
    files = inventory_files(stage, prefix, os.environ['MSYSTEM_PREFIX'], packages, owners)
    result = {
        'schemaVersion': 1,
        'recordedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sourceCommit': source_commit,
        'platform': sys.platform, 'msystem': os.environ['MSYSTEM'], 'packages': packages,
        'files': files, 'licenseAuditComplete': False,
        'remainingGates': ['Audit every emitted library/resource and its corresponding source obligations', 'Execute the staged application and PDF/pen tests', 'Validate final MSIX identity, installation, signing and certification'],
        'omitted': ['LuaGObject and plugins', 'Audio support', 'GTKSourceView and GTK demo applications'],
    }
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
