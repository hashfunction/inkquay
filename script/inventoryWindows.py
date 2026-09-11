#!/usr/bin/env python3
"""Inventory the actual native stage. Copyright 2026 Trieflow LLC, GPL-2.0-or-later."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REQUIRED_PACKAGE_FILES = ('bin/libfontconfig-1.dll', 'bin/gdbus.exe', 'etc/fonts/fonts.conf')


def pacman_prefix(prefix):
    # MSYS2 converts MSYSTEM_PREFIX when it launches native Python. Convert the
    # actual native path back once; pacman's file inventory uses POSIX paths.
    result = subprocess.check_output(['cygpath', '-u', str(prefix)], text=True, encoding='utf-8').strip()
    if not result.startswith('/') or result.startswith('//') or '\n' in result or '\r' in result or ':' in result or '\\' in result:
        raise ValueError('cygpath did not return one absolute POSIX package prefix')
    return result.rstrip('/')


def validate_provenance(files, msys_prefix, owners, built_application_sha256=None):
    if not any(path.startswith(msys_prefix + '/') for path in owners):
        raise ValueError('No installed files match the package ownership prefix: ' + msys_prefix)
    rows = {row['path']: row for row in files}
    if built_application_sha256 is not None and rows.get('bin/inkquay.exe', {}).get('sha256') != built_application_sha256:
        raise ValueError('Staged InkQuay executable is missing or differs from the exact application build')
    for required in REQUIRED_PACKAGE_FILES:
        if required not in rows or not rows[required].get('package'):
            raise ValueError('Required staged runtime/configuration has no verified package owner: ' + required)
    for row in files:
        if Path(row['path']).suffix.lower() in ('.dll', '.exe') and not row.get('package'):
            if row['path'] == 'bin/inkquay.exe' and built_application_sha256 and row.get('sha256') == built_application_sha256:
                continue
            raise ValueError('Staged runtime has no verified package owner or exact application build identity: ' + row['path'])
    return {
        'stagedFiles': len(files),
        'byteMatchedSourceFiles': sum('sourcePath' in row for row in files),
        'packageOwnedFiles': sum('package' in row for row in files),
        'unresolvedFiles': sum('package' not in row for row in files),
    }


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
    stage, prefix, report, built_application = map(Path, sys.argv[1:])
    if built_application.name != 'inkquay.exe' or not built_application.is_file():
        raise ValueError('The exact built InkQuay executable is required for application provenance')
    built_application_sha256 = digest(built_application)
    source_commit = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[1]), 'rev-parse', 'HEAD'], text=True).strip()
    packages = dict(line.split(' ', 1) for line in subprocess.check_output(['pacman', '-Q'], text=True, encoding='utf-8').splitlines())
    # One installed-file snapshot replaces a process launch for every copied icon
    # and DLL. Byte comparisons still decide whether package provenance applies.
    owners = package_file_owners(subprocess.check_output(['pacman', '-Ql'], text=True, encoding='utf-8'))
    msys_prefix = pacman_prefix(prefix)
    files = inventory_files(stage, prefix, msys_prefix, packages, owners)
    counts = validate_provenance(files, msys_prefix, owners, built_application_sha256)
    result = {
        'schemaVersion': 2,
        'recordedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sourceCommit': source_commit,
        'platform': sys.platform, 'msystem': os.environ['MSYSTEM'], 'packages': packages,
        'nativePackagePrefix': str(prefix), 'pacmanPackagePrefix': msys_prefix,
        'provenanceCounts': counts,
        'builtApplication': {'path': str(built_application), 'sha256': built_application_sha256},
        'files': files, 'licenseAuditComplete': False,
        'remainingGates': ['Audit every emitted library/resource and its corresponding source obligations', 'Execute the staged application and PDF/pen tests', 'Validate final MSIX identity, installation, signing and certification'],
        'omitted': ['LuaGObject and plugins', 'Audio support', 'GTKSourceView and GTK demo applications'],
    }
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
