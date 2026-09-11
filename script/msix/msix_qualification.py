#!/usr/bin/env python3
"""Build and independently verify a disposable InkQuay qualification MSIX.

Copyright 2026 Trieflow LLC. MIT licensed. Derived from TwinQuay qualification
source 1ee1e1849ad2aad030717b7ba56254197436ea4e, PixelQuay and ReticleQuay;
retained notices: PIPELINE-MIT.txt and RETICLEQUAY-MIT.txt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile
import zlib


APPX_NS = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP_NS = "http://schemas.microsoft.com/appx/manifest/uap/windows10"
RESCAP_NS = "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
ET.register_namespace("", APPX_NS)
ET.register_namespace("uap", UAP_NS)
ET.register_namespace("rescap", RESCAP_NS)

QUALIFICATION_IDENTITY = {
    "packageName": "Trieflow.InkQuay.Qualification",
    "publisher": "CN=InkQuay-CI-Qualification",
    "version": "1.0.0.0",
    "architecture": "x64",
    "applicationId": "InkQuay",
    "executable": "bin/inkquay.exe",
    "deviceFamily": "Windows.Desktop",
    "minVersion": "10.0.19041.0",
    "maxVersionTested": "10.0.26100.0",
    "capability": "runFullTrust",
}
SOURCE_COPIES = {
    "share/inkquay/licenses/LICENSE": "LICENSE",
    "share/inkquay/licenses/AUTHORS": "AUTHORS",
    "share/inkquay/licenses/copyright": "debian/copyright",
    "share/inkquay/licenses/copyright.txt": "copyright.txt",
    "share/inkquay/licenses/THIRD-PARTY-NOTICES.txt": "Release/THIRD-PARTY-NOTICES.txt",
    "share/inkquay/ui/pixmaps/com.trieflow.inkquay.png": "ui/pixmaps/com.trieflow.inkquay.png",
    "share/inkquay/ui/pixmaps/com.trieflow.inkquay.svg": "ui/pixmaps/com.trieflow.inkquay.svg",
}
NOTICE_SOURCE = "Release/notice-supplement"
NOTICE_DESTINATION = "share/inkquay/licenses/supplement"
for _notice_name in ("NOTICE-INDEX.json", "SOURCE-INPUTS.json", "README.txt"):
    SOURCE_COPIES[f"{NOTICE_DESTINATION}/{_notice_name}"] = f"{NOTICE_SOURCE}/{_notice_name}"
SOURCE_FILES = tuple(SOURCE_COPIES.values()) + (
    "Release/windows-dependencies.json",
    "src/core/control/Control.cpp",
    "script/inventoryWindows.py",
    "windows-setup/package.sh",
    "script/msix/copy_notice_supplement.py",
    "script/msix/msix_qualification.py",
    "CMakeLists.txt",
)
RUNTIME = {
    "executable": "bin/inkquay.exe",
    "gtk": "bin/libgtk-3-0.dll",
    "gio": "bin/libgio-2.0-0.dll",
    "gobject": "bin/libgobject-2.0-0.dll",
    "cairo": "bin/libcairo-2.dll",
    "fontconfig": "bin/libfontconfig-1.dll",
    "poppler": "bin/libpoppler-glib-8.dll",
}
REQUIRED_RELEASE_FILES = (
    tuple(SOURCE_COPIES)
    + tuple(RUNTIME.values())
    + (
        "bin/inkquay-wrapper.exe",
        "bin/gdbus.exe",
        "bin/libqpdf30.dll",
        "bin/libpoppler-163.dll",
        "etc/fonts/fonts.conf",
    )
)
PACKAGE_METADATA = {
    "[Content_Types].xml",
    "AppxBlockMap.xml",
    "AppxMetadata/CodeIntegrity.cat",
}


def _canonical_json(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(stream):
    hasher = hashlib.sha256()
    size = 0
    while block := stream.read(1024 * 1024):
        hasher.update(block)
        size += len(block)
    return {"bytes": size, "sha256": hasher.hexdigest()}


def _reject_link(path):
    path = Path(path)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Symlink/reparse point refused: {path}")
    return info


def _regular_stream(path):
    path = Path(path)
    before = _reject_link(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Expected regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    stream = os.fdopen(fd, "rb")
    after = os.fstat(fd)
    if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        stream.close()
        raise ValueError(f"File identity changed while opening: {path}")
    return stream


def _checked_path(value):
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or value.startswith("/")
    ):
        raise ValueError(f"Unsafe Windows path: {value!r}")
    parts = value.split("/")
    if any(
        not part
        or part in (".", "..")
        or part.endswith((".", " "))
        or re.search(r'[<>"|?*\x00-\x1f\x7f]', part)
        or re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I)
        for part in parts
    ):
        raise ValueError(f"Unsafe Windows path: {value!r}")
    return value


def _register_path(value, seen):
    _checked_path(value)
    parts = value.split("/")
    for count in range(1, len(parts) + 1):
        prefix = "/".join(parts[:count])
        key = unicodedata.normalize("NFC", prefix).casefold()
        if ("file", key) in seen:
            raise ValueError(f"File/directory or case/Unicode alias: {value}")
        prior = seen.get(("component", key))
        if prior is not None and prior != prefix:
            raise ValueError(f"Case/Unicode path alias: {value}")
        if count == len(parts) and ("directory", key) in seen:
            raise ValueError(f"File/directory path alias: {value}")
        seen[("component", key)] = prefix
        seen[("file" if count == len(parts) else "directory", key)] = prefix


def inventory_tree(root):
    root = Path(root)
    for parent in root.absolute().parents:
        _reject_link(parent)
    root_info = _reject_link(root)
    if not stat.S_ISDIR(root_info.st_mode):
        raise ValueError(f"Expected directory: {root}")
    result = {}
    seen = {}

    def walk(directory):
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            info = _reject_link(path)
            relative = path.relative_to(root).as_posix()
            _checked_path(relative)
            if stat.S_ISDIR(info.st_mode):
                walk(path)
            elif stat.S_ISREG(info.st_mode):
                _register_path(relative, seen)
                with _regular_stream(path) as stream:
                    result[relative] = _digest(stream)
            else:
                raise ValueError(f"Special file refused: {relative}")

    walk(root)
    if not result:
        raise ValueError("Empty tree refused")
    return result


def _load_json(path, label):
    try:
        with _regular_stream(path) as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError(f"Oversized {label}")
        return json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid {label}: {error}") from error


def file_record(path):
    with _regular_stream(path) as stream:
        return _digest(stream)


def notice_sources(source_root):
    """Require the complete original-file map before copying or packaging."""
    root = Path(source_root) / NOTICE_SOURCE
    index = _load_json(root / "NOTICE-INDEX.json", "original notice index")
    rows = index.get("files")
    if (index.get("schemaVersion") != 1 or not isinstance(rows, list) or not rows
            or type(index.get("fileCount")) is not int or index["fileCount"] != len(rows)):
        raise ValueError("Incomplete original notice index")
    expected, seen = {}, {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid original notice row")
        name = _checked_path(row.get("path"))
        _register_path(name, seen)
        if (not name.startswith("originals/") or type(row.get("bytes")) is not int
                or row["bytes"] < 0 or not isinstance(row.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("Invalid original notice path/size/hash")
        expected[name.removeprefix("originals/")] = {key: row[key] for key in ("bytes", "sha256")}
    # Exact set equality rejects both omitted mappings and unindexed additions.
    # Zero-byte original files are valid only at their recorded exact hash.
    if inventory_tree(root / "originals") != expected:
        raise ValueError("Original notice files differ from complete index")
    return {f"{NOTICE_DESTINATION}/originals/{name}": f"{NOTICE_SOURCE}/originals/{name}"
            for name in expected}


def copy_notice_supplement(source_root, release):
    source_root, release = Path(source_root), Path(release)
    copies = notice_sources(source_root)
    copies.update({target: source for target, source in SOURCE_COPIES.items()
                   if target.startswith(NOTICE_DESTINATION + "/")})
    measured = {target: file_record(source_root / source) for target, source in copies.items()}
    parent = release / NOTICE_DESTINATION
    for ancestor in parent.absolute().parents:
        if ancestor.exists() or os.path.lexists(ancestor):
            _reject_link(ancestor)
    if os.path.lexists(parent):
        raise ValueError("Notice destination already exists; preserving prior bytes")
    parent.mkdir(parents=True)
    for target, source in copies.items():
        path = release / target
        path.parent.mkdir(parents=True, exist_ok=True)
        with _regular_stream(source_root / source) as original, path.open("xb") as output:
            shutil.copyfileobj(original, output, 1024 * 1024)
        if file_record(path) != measured[target]:
            raise ValueError("Original notice changed while copying")
    expected = {name.removeprefix(NOTICE_DESTINATION + "/"): value for name, value in measured.items()}
    if inventory_tree(parent) != expected:
        raise ValueError("Copied notice supplement differs from exact sources")
    return measured


def source_inputs(source_root):
    source_root = Path(source_root)
    control = (source_root / "src/core/control/Control.cpp").read_text(encoding="utf-8")
    title = re.search(r"void Control::updateWindowTitle\(\).*?\n}\s*", control, re.S)
    if (
        not title
        or 'title = _("Unsaved Document");' not in title[0]
        or 'title += " - InkQuay";' not in title[0]
    ):
        raise ValueError(
            "Actual application title differs from exact InkQuay qualification title"
        )
    names = tuple(SOURCE_FILES) + tuple(notice_sources(source_root).values())
    return {name: file_record(source_root / name) for name in names}


def create_input_inventory(release, source_root, source_commit):
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit or ""):
        raise ValueError("Exact source commit required")
    release, source_root = Path(release), Path(source_root)
    files = inventory_tree(release)
    for name in REQUIRED_RELEASE_FILES:
        if name not in files or files[name]["bytes"] == 0:
            raise ValueError(f"Missing runtime/resource/notice: {name}")
    sources = source_inputs(source_root)
    copies = dict(SOURCE_COPIES, **notice_sources(source_root))
    for staged, original in copies.items():
        if files.get(staged) != sources[original]:
            raise ValueError(
                f"Original source notice/artwork changed or missing: {original}"
            )
    native_path = source_root / "build/inkquay-windows-inventory.json"
    native = _load_json(native_path, "same-run native provenance")
    if (
        native.get("schemaVersion") != 3
        or native.get("sourceCommit") != source_commit
        or native.get("platform") != "win32"
        or native.get("msystem") != "MINGW64"
    ):
        raise ValueError("Native inventory schema, source or platform mismatch")
    if not isinstance(native.get("files"), list) or not isinstance(
        native.get("packages"), dict
    ):
        raise ValueError("Missing complete native inventory files/packages")
    source_index = _load_json(source_root / NOTICE_SOURCE / "SOURCE-INPUTS.json", "retained source-input index")
    if (source_index.get("schemaVersion") != 1
            or source_index.get("sourceUrl") != "https://inkquay.trieflow.com/source"
            or not isinstance(source_index.get("nativeOwners"), list)):
        raise ValueError("Invalid retained source-input index")
    source_versions = {}
    for owner in source_index["nativeOwners"]:
        if (not isinstance(owner, dict) or not isinstance(owner.get("package"), str)
                or not owner["package"] or owner["package"] in source_versions
                or not isinstance(owner.get("version"), str) or not owner["version"]):
            raise ValueError("Invalid or duplicate retained source owner")
        source_versions[owner["package"]] = owner["version"]
    built = {
        "bin/inkquay.exe": native.get("builtApplication", {}).get("sha256"),
        "bin/inkquay-wrapper.exe": native.get("builtWrapper", {}).get("sha256"),
    }
    if any(files[name]["sha256"] != sha for name, sha in built.items()):
        raise ValueError("Native inventory does not bind both exact built executables")
    recorded, seen, unresolved = {}, {}, []
    for row in native["files"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid native provenance row")
        name = _checked_path(row.get("path"))
        _register_path(name, seen)
        if (
            type(row.get("bytes")) is not int
            or row["bytes"] < 0
            or not isinstance(row.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        ):
            raise ValueError("Invalid native provenance size/hash")
        recorded[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
        package = row.get("package")
        if package:
            if (
                not isinstance(package, str)
                or native["packages"].get(package) != row.get("packageVersion")
                or not row.get("packageVersion")
            ):
                raise ValueError(
                    "Native owner differs from installed package version snapshot"
                )
            if source_versions.get(package) != row["packageVersion"]:
                raise ValueError(f"Native owner/version has no matching retained source: {package}")
        elif Path(name).suffix.lower() in (".exe", ".dll"):
            if built.get(name) != row["sha256"]:
                raise ValueError(
                    f"Native executable lacks exact package/build provenance: {name}"
                )
        else:
            unresolved.append(name)
    if recorded != files:
        raise ValueError("Native inventory files differ from exact full stage")
    return dict(
        schemaVersion=1,
        sourceCommit=source_commit,
        files=files,
        sourceInputs=sources,
        runtime=dict(RUNTIME),
        nativeInventory=file_record(native_path),
        unresolvedResources=unresolved,
        buildProvenance=dict(
            application="Both exact compiled application and crash-wrapper hashes verified",
            dependencies="Same-run schema3 Windows MINGW64 inventory and exact installed package versions",
            inventoryIsLicenseClearance=False,
            unresolvedResources="Unowned resources are explicit audit inputs, not permission to release",
        ),
    )


def validate_input_evidence(release, inventory, startup, source_root, source_commit):
    recorded = _load_json(inventory, "same-run stage inventory")
    measured = create_input_inventory(release, source_root, source_commit)
    if recorded != measured:
        raise ValueError(
            "Full stage inventory or source metadata differs from current source-bound inputs"
        )
    receipt = _load_json(startup, "same-run native startup receipt")
    if (
        receipt.get("source_commit") != source_commit
        or receipt.get("windows_native_startup") is not True
        or receipt.get("window_title") != "Unsaved Document - InkQuay"
        or str(receipt.get("executable_sha256", "")).lower()
        != measured["files"]["bin/inkquay.exe"]["sha256"]
        or receipt.get("package_inventory_sha256") != file_record(inventory)["sha256"]
    ):
        raise ValueError(
            "Native startup receipt does not bind this exact source, inventory and executable"
        )
    return recorded, receipt


def create_manifest():
    identity = QUALIFICATION_IDENTITY
    package = ET.Element(f"{{{APPX_NS}}}Package", {"IgnorableNamespaces": "uap rescap"})
    ET.SubElement(
        package,
        f"{{{APPX_NS}}}Identity",
        {
            "Name": identity["packageName"],
            "Publisher": identity["publisher"],
            "Version": identity["version"],
            "ProcessorArchitecture": identity["architecture"],
        },
    )
    properties = ET.SubElement(package, f"{{{APPX_NS}}}Properties")
    for name, value in (
        ("DisplayName", "InkQuay"),
        ("PublisherDisplayName", "Trieflow LLC"),
        ("Description", "InkQuay qualification package"),
        ("Logo", r"Assets\StoreLogo.png"),
    ):
        ET.SubElement(properties, f"{{{APPX_NS}}}{name}").text = value
    resources = ET.SubElement(package, f"{{{APPX_NS}}}Resources")
    ET.SubElement(resources, f"{{{APPX_NS}}}Resource", {"Language": "en-US"})
    dependencies = ET.SubElement(package, f"{{{APPX_NS}}}Dependencies")
    ET.SubElement(
        dependencies,
        f"{{{APPX_NS}}}TargetDeviceFamily",
        {
            "Name": identity["deviceFamily"],
            "MinVersion": identity["minVersion"],
            "MaxVersionTested": identity["maxVersionTested"],
        },
    )
    applications = ET.SubElement(package, f"{{{APPX_NS}}}Applications")
    application = ET.SubElement(
        applications,
        f"{{{APPX_NS}}}Application",
        {
            "Id": identity["applicationId"],
            "Executable": identity["executable"],
            "EntryPoint": "Windows.FullTrustApplication",
        },
    )
    ET.SubElement(
        application,
        f"{{{UAP_NS}}}VisualElements",
        {
            "DisplayName": "InkQuay",
            "Description": "InkQuay qualification package",
            "BackgroundColor": "#142e38",
            "Square150x150Logo": r"Assets\Square150x150Logo.png",
            "Square44x44Logo": r"Assets\Square44x44Logo.png",
        },
    )
    capabilities = ET.SubElement(package, f"{{{APPX_NS}}}Capabilities")
    ET.SubElement(
        capabilities, f"{{{RESCAP_NS}}}Capability", {"Name": identity["capability"]}
    )
    ET.indent(package, space="  ")
    return ET.tostring(package, encoding="utf-8", xml_declaration=True)


def _one(parent, tag, label):
    items = parent.findall(tag)
    if len(items) != 1:
        raise ValueError(f"Manifest requires exactly one {label}")
    return items[0]


def validate_manifest(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError(f"Invalid manifest XML: {error}") from error
    if root.tag != f"{{{APPX_NS}}}Package" or root.attrib != {
        "IgnorableNamespaces": "uap rescap"
    }:
        raise ValueError("Invalid manifest package root")
    expected_children = [
        f"{{{APPX_NS}}}Identity",
        f"{{{APPX_NS}}}Properties",
        f"{{{APPX_NS}}}Resources",
        f"{{{APPX_NS}}}Dependencies",
        f"{{{APPX_NS}}}Applications",
        f"{{{APPX_NS}}}Capabilities",
    ]
    if [child.tag for child in root] != expected_children:
        raise ValueError("Unexpected manifest sections or extensions")
    identity_node = _one(root, f"{{{APPX_NS}}}Identity", "identity")
    identity = QUALIFICATION_IDENTITY
    if identity_node.attrib != {
        "Name": identity["packageName"],
        "Publisher": identity["publisher"],
        "Version": identity["version"],
        "ProcessorArchitecture": identity["architecture"],
    }:
        raise ValueError("Unexpected qualification identity")
    properties = _one(root, f"{{{APPX_NS}}}Properties", "properties")
    expected_properties = {
        "DisplayName": "InkQuay",
        "PublisherDisplayName": "Trieflow LLC",
        "Description": "InkQuay qualification package",
        "Logo": r"Assets\StoreLogo.png",
    }
    if (
        len(properties) != len(expected_properties)
        or {child.tag.rsplit("}", 1)[-1]: child.text for child in properties}
        != expected_properties
        or any(child.attrib or len(child) for child in properties)
    ):
        raise ValueError("Unexpected manifest properties")
    resources = _one(root, f"{{{APPX_NS}}}Resources", "resources")
    resource = _one(resources, f"{{{APPX_NS}}}Resource", "resource")
    if len(resources) != 1 or resource.attrib != {"Language": "en-US"} or len(resource):
        raise ValueError("Unexpected manifest resources")
    dependencies = _one(root, f"{{{APPX_NS}}}Dependencies", "dependencies")
    family = _one(
        dependencies, f"{{{APPX_NS}}}TargetDeviceFamily", "target device family"
    )
    if (
        len(dependencies) != 1
        or family.attrib
        != {
            "Name": identity["deviceFamily"],
            "MinVersion": identity["minVersion"],
            "MaxVersionTested": identity["maxVersionTested"],
        }
        or len(family)
    ):
        raise ValueError("Unexpected target device family")
    applications = _one(root, f"{{{APPX_NS}}}Applications", "applications")
    application = _one(applications, f"{{{APPX_NS}}}Application", "application")
    if len(applications) != 1 or application.attrib != {
        "Id": identity["applicationId"],
        "Executable": identity["executable"],
        "EntryPoint": "Windows.FullTrustApplication",
    }:
        raise ValueError("Unexpected manifest executable/application")
    visual = _one(application, f"{{{UAP_NS}}}VisualElements", "visual elements")
    if (
        len(application) != 1
        or visual.attrib
        != {
            "DisplayName": "InkQuay",
            "Description": "InkQuay qualification package",
            "BackgroundColor": "#142e38",
            "Square150x150Logo": r"Assets\Square150x150Logo.png",
            "Square44x44Logo": r"Assets\Square44x44Logo.png",
        }
        or len(visual)
    ):
        raise ValueError("Unexpected manifest visual elements")
    capabilities = _one(root, f"{{{APPX_NS}}}Capabilities", "capabilities")
    capability = _one(capabilities, f"{{{RESCAP_NS}}}Capability", "capability")
    if (
        len(capabilities) != 1
        or capability.attrib != {"Name": identity["capability"]}
        or len(capability)
    ):
        raise ValueError("Unexpected manifest capabilities")
    return dict(identity)


def _png_chunks(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Artwork is not PNG")
    position = 8
    while position < len(data):
        if position + 12 > len(data):
            raise ValueError("Truncated PNG")
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        crc = data[position + 8 + length : position + 12 + length]
        if (
            len(body) != length
            or len(crc) != 4
            or zlib.crc32(kind + body) & 0xFFFFFFFF != struct.unpack(">I", crc)[0]
        ):
            raise ValueError("Invalid PNG chunk")
        position += 12 + length
        yield kind, body
        if kind == b"IEND":
            if position != len(data):
                raise ValueError("Trailing PNG data")
            return
    raise ValueError("PNG is missing IEND")


def png_dimensions(data):
    chunks = list(_png_chunks(data))
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        raise ValueError("PNG is missing IHDR")
    return struct.unpack(">II", chunks[0][1][:8])


def _decode_rgba_png(data):
    chunks = list(_png_chunks(data))
    if chunks[0][0] != b"IHDR":
        raise ValueError("PNG is missing IHDR")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    if not (
        0 < width <= 4096
        and 0 < height <= 4096
        and depth == 8
        and color == 6
        and compression == filtering == interlace == 0
    ):
        raise ValueError("Artwork must be bounded noninterlaced 8-bit RGBA PNG")
    compressed = b"".join(body for kind, body in chunks if kind == b"IDAT")
    try:
        raw = zlib.decompress(compressed)
    except zlib.error as error:
        raise ValueError(f"Invalid compressed PNG: {error}") from error
    stride = width * 4
    if len(raw) != (stride + 1) * height:
        raise ValueError("Unexpected PNG data size")
    rows = []
    prior = bytearray(stride)
    for row_number in range(height):
        start = row_number * (stride + 1)
        filter_type = raw[start]
        encoded = raw[start + 1 : start + stride + 1]
        if filter_type > 4:
            raise ValueError("Unsupported PNG filter")
        row = bytearray(stride)
        for index, value in enumerate(encoded):
            left = row[index - 4] if index >= 4 else 0
            up = prior[index]
            upper_left = prior[index - 4] if index >= 4 else 0
            if filter_type == 0:
                prediction = 0
            elif filter_type == 1:
                prediction = left
            elif filter_type == 2:
                prediction = up
            elif filter_type == 3:
                prediction = (left + up) // 2
            else:
                candidate = left + up - upper_left
                dl, du, dul = (
                    abs(candidate - left),
                    abs(candidate - up),
                    abs(candidate - upper_left),
                )
                prediction = (
                    left if dl <= du and dl <= dul else up if du <= dul else upper_left
                )
            row[index] = (value + prediction) & 0xFF
        rows.append(bytes(row))
        prior = row
    return width, height, rows


def _chunk(kind, body):
    return (
        struct.pack(">I", len(body))
        + kind
        + body
        + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    )


def resize_png(data, target):
    if target not in (44, 50, 150):
        raise ValueError("Unreviewed qualification asset size")
    width, height, rows = _decode_rgba_png(data)
    output = bytearray()
    for y in range(target):
        source_row = rows[min(height - 1, y * height // target)]
        output.append(0)
        for x in range(target):
            start = min(width - 1, x * width // target) * 4
            output.extend(source_row[start : start + 4])
    header = struct.pack(">IIBBBBB", target, target, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(output), 9))
        + _chunk(b"IEND", b"")
    )


def _write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def stage_release(
    release, artwork, stage, source_commit, inventory, startup, source_root
):
    release, artwork, stage = Path(release), Path(artwork), Path(stage)
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit or ""):
        raise ValueError("Exact 40-character source commit is required")
    if os.path.lexists(stage):
        raise ValueError(f"Stage already exists and will not be replaced: {stage}")
    input_inventory = inventory_tree(release)
    for relative in REQUIRED_RELEASE_FILES:
        if relative not in input_inventory:
            raise ValueError(f"Required release file missing: {relative}")
    if "AppxManifest.xml" in input_inventory or any(
        name.casefold().startswith("assets/") for name in input_inventory
    ):
        raise ValueError("Release collides with qualification-owned manifest/assets")
    input_record, startup_record = validate_input_evidence(
        release, inventory, startup, source_root, source_commit
    )
    with _regular_stream(artwork) as stream:
        artwork_data = stream.read()
    artwork_record = {
        "bytes": len(artwork_data),
        "sha256": hashlib.sha256(artwork_data).hexdigest(),
    }
    if (
        artwork_record
        != input_record["sourceInputs"]["ui/pixmaps/com.trieflow.inkquay.png"]
    ):
        raise ValueError(
            "Qualification artwork differs from the source-bound application artwork"
        )
    assets = {}
    stage.mkdir(parents=False)
    try:
        for relative in sorted(input_inventory):
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with _regular_stream(release / relative) as source, target.open(
                "xb"
            ) as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
        for name, size in (
            ("StoreLogo.png", 50),
            ("Square44x44Logo.png", 44),
            ("Square150x150Logo.png", 150),
        ):
            data = resize_png(artwork_data, size)
            relative = f"Assets/{name}"
            _write_new(stage / relative, data)
            assets[relative] = {
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "pixels": [size, size],
            }
        manifest = create_manifest()
        validate_manifest(manifest)
        _write_new(stage / "AppxManifest.xml", manifest)
        if inventory_tree(release) != input_inventory:
            raise ValueError("Release input changed while staging")
        payload = inventory_tree(stage)
        for relative, record in input_inventory.items():
            if payload.get(relative) != record:
                raise ValueError(f"Staged release differs from input: {relative}")
        return {
            "schemaVersion": 1,
            "sourceCommit": source_commit,
            "qualificationIdentityOnly": True,
            "identity": dict(QUALIFICATION_IDENTITY),
            "releaseInput": input_inventory,
            "payload": payload,
            "inputInventory": file_record(inventory),
            "startupReceipt": file_record(startup),
            "sourceInputs": input_record["sourceInputs"],
            "runtime": dict(RUNTIME),
            "buildProvenance": input_record["buildProvenance"],
            "unresolvedResources": input_record["unresolvedResources"],
            "artworkSource": artwork_record,
            "assets": assets,
            "licenseClearanceClaimed": False,
            "publicRelease": False,
            "signed": False,
            "installationQualificationPassed": False,
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _decode_opc_path(value):
    # MakeAppx stores OPC URI names in the ZIP, e.g. libc++.dll becomes
    # libc%2B%2B.dll. Decode once before payload/hash and alias comparison.
    # Escaped separators cannot change the archive's directory hierarchy.
    if re.search(r"%(?![0-9A-Fa-f]{2})|%(?:2f|5c)", value, re.I):
        raise ValueError(f"Malformed or hierarchy-changing OPC path: {value!r}")
    return _checked_path(unquote(value, encoding="utf-8", errors="strict"))


def verify_msix(path, expected):
    if not isinstance(expected, dict) or "AppxManifest.xml" not in expected:
        raise ValueError("Invalid expected package payload")
    allowed_directories = {
        str(parent)
        for name in set(expected) | PACKAGE_METADATA
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    }
    seen = {}
    actual = {}
    metadata = set()
    directories = set()
    manifest_data = None
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = _decode_opc_path(
                info.filename.rstrip("/") if info.is_dir() else info.filename
            )
            mode = info.external_attr >> 16
            if info.flag_bits & 1:
                raise ValueError(f"Encrypted package entry: {info.filename}")
            if info.is_dir():
                key = unicodedata.normalize("NFC", name).casefold()
                if (
                    stat.S_IFMT(mode) not in (0, stat.S_IFDIR)
                    or name not in allowed_directories
                    or key in directories
                ):
                    raise ValueError(
                        f"Unexpected/special package directory: {info.filename}"
                    )
                directories.add(key)
                continue
            _register_path(name, seen)
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError(f"Special package entry: {name}")
            if name in PACKAGE_METADATA:
                if info.file_size > 32 * 1024 * 1024:
                    raise ValueError(f"Oversized package metadata: {name}")
                metadata.add(name)
                continue
            record = expected.get(name)
            if not record or info.file_size != record["bytes"]:
                raise ValueError(f"Unexpected package entry or size: {name}")
            with archive.open(info) as stream:
                measured = _digest(stream)
            if measured != record:
                raise ValueError(f"Package hash mismatch: {name}")
            actual[name] = measured
            if name == "AppxManifest.xml":
                manifest_data = archive.read(info)
    if set(actual) != set(expected):
        raise ValueError("Package payload is missing expected files")
    if not {"[Content_Types].xml", "AppxBlockMap.xml"}.issubset(metadata):
        raise ValueError("Package metadata is incomplete")
    validate_manifest(manifest_data)
    with _regular_stream(path) as stream:
        package = _digest(stream)
    return {
        "verifiedPayloadFiles": len(actual),
        "metadata": sorted(metadata),
        "package": package,
    }


def verify_unpacked(root, expected):
    actual = inventory_tree(root)
    for metadata in PACKAGE_METADATA:
        actual.pop(metadata, None)
    if actual != expected:
        raise ValueError("SDK-unpacked payload differs from staged payload")
    validate_manifest((Path(root) / "AppxManifest.xml").read_bytes())
    return {"verifiedPayloadFiles": len(actual)}


def verify_installed(root, expected):
    actual = inventory_tree(root)
    for metadata in PACKAGE_METADATA | {"AppxSignature.p7x"}:
        actual.pop(metadata, None)
    if actual != expected:
        raise ValueError(
            "Installed package has missing, altered or extra payload files"
        )
    validate_manifest((Path(root) / "AppxManifest.xml").read_bytes())
    return {"verifiedPayloadFiles": len(actual)}


def verify_record_inputs(
    package,
    record_path,
    release,
    artwork,
    source_commit,
    inventory,
    startup,
    source_root,
):
    record = _load_json(record_path, "qualification record")
    # Recreate the package boundary from current source/stage/receipt rather than
    # trusting a coherent replacement of the package and its own recorded hashes.
    with tempfile.TemporaryDirectory(prefix="inkquay-record-") as temporary:
        expected = stage_release(
            release,
            artwork,
            Path(temporary).resolve() / "stage",
            source_commit,
            inventory,
            startup,
            source_root,
        )
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "Package record no longer matches source-bound qualification inputs"
        )
    actual = verify_msix(package, expected["payload"])
    if record.get("containerVerification") != actual:
        raise ValueError(
            "Package record differs from independent container verification"
        )
    unpacked = record.get("unpackedVerification")
    if (
        not isinstance(unpacked, dict)
        or set(unpacked) != {"verifiedPayloadFiles"}
        or type(unpacked["verifiedPayloadFiles"]) is not int
        or unpacked["verifiedPayloadFiles"] != len(expected["payload"])
    ):
        raise ValueError("Package record lacks exact source-bound SDK unpack evidence")
    return True


def _tool_record(path, sdk_version):
    path = Path(path)
    if not path.is_absolute() or path.name.casefold() != "makeappx.exe":
        raise ValueError("Absolute MakeAppx.exe path is required")
    if sdk_version != "10.0.26100.0":
        raise ValueError("Exact Windows SDK version is required")
    normalized = [part.casefold() for part in path.parts]
    expected_tail = [
        "windows kits",
        "10",
        "bin",
        sdk_version.casefold(),
        "x64",
        "makeappx.exe",
    ]
    if normalized[-6:] != expected_tail:
        raise ValueError(
            "MakeAppx SDK path must end with Windows Kits/10/bin/<exact-version>/x64/makeappx.exe"
        )
    with _regular_stream(path) as stream:
        record = _digest(stream)
    record.update({"path": str(path), "sdkVersion": sdk_version})
    return record


def _run(command):
    subprocess.run(command, check=True, shell=False, timeout=900)


def build_qualification(
    release,
    artwork,
    source_commit,
    makeappx,
    sdk_version,
    output,
    inventory,
    startup,
    source_root,
    runner=_run,
):
    output = Path(output).absolute()
    if os.path.lexists(output):
        raise ValueError(f"Output already exists and will not be replaced: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".inkquay-msix-", dir=output.parent))
    try:
        tool = _tool_record(makeappx, sdk_version)
        stage = temporary / "stage"
        record = stage_release(
            release, artwork, stage, source_commit, inventory, startup, source_root
        )
        package = temporary / "InkQuay.Qualification_1.0.0.0_x64.msix"
        unpacked = temporary / "unpacked"
        commands = [
            [
                str(makeappx),
                "pack",
                "/d",
                str(stage),
                "/p",
                str(package),
                "/v",
                "/h",
                "SHA256",
            ],
            [str(makeappx), "unpack", "/p", str(package), "/d", str(unpacked), "/v"],
        ]
        for command in commands:
            if _tool_record(makeappx, sdk_version) != tool:
                raise ValueError("MakeAppx changed during qualification build")
            runner(command)
            if inventory_tree(stage) != record["payload"]:
                raise ValueError("Package stage changed during SDK execution")
        container = verify_msix(package, record["payload"])
        unpacked_result = verify_unpacked(unpacked, record["payload"])
        if _tool_record(makeappx, sdk_version) != tool:
            raise ValueError("MakeAppx changed during qualification build")
        record.update(
            {
                "makeAppx": tool,
                "containerVerification": container,
                "unpackedVerification": unpacked_result,
            }
        )
        output.mkdir()
        try:
            with _regular_stream(package) as source, (output / package.name).open(
                "xb"
            ) as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)
            _write_new(output / "package-record.json", _canonical_json(record))
        except Exception:
            # This directory was created by this invocation; retain it as explicit incomplete evidence.
            _write_new(
                output / "INCOMPLETE.txt",
                b"Packaging output is incomplete and must not be consumed.\n",
            )
            raise
        shutil.rmtree(temporary)
        return output
    except Exception as error:
        raise ValueError(
            f"Qualification packaging failed; evidence retained at {temporary}: {error}"
        ) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--artwork", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--makeappx", type=Path, required=True)
    parser.add_argument("--sdk-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--startup", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("CI") != "true":
        parser.error("Qualification package builds require disposable Windows CI")
    try:
        actual = subprocess.run(
            ["git", "-C", str(args.source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        if actual != args.source_commit:
            raise ValueError(
                f"Source commit mismatch: expected {args.source_commit}, found {actual}"
            )
        dirty = subprocess.run(
            [
                "git",
                "-C",
                str(args.source_root),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        if dirty:
            raise ValueError(
                "Source checkout must be clean so the recorded commit identifies every packaging input"
            )
        print(
            build_qualification(
                args.release,
                args.artwork,
                args.source_commit,
                args.makeappx,
                args.sdk_version,
                args.output,
                args.inventory,
                args.startup,
                args.source_root,
            )
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
