# Copyright 2026 Trieflow LLC. MIT.
"""Owned input preparation and independent Poppler checks. Never drives product internals."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET

LIMIT = 16 * 1024 * 1024
# Exact disclosure emitted by PdfExportVerifier::verify even for Passed.
SCOPE_DISCLOSURE = (
    "Checks cover PDF structure, page count, positive page sizes and unchanged "
    "protected files; visual fidelity and accessibility were not checked."
)


def _lstat_nonreparse_chain(path):
    target = None
    for item in (path, *path.parents):
        observed = item.lstat()
        if stat.S_ISLNK(observed.st_mode) or getattr(
            observed, "st_file_attributes", 0
        ) & 0x400:
            raise ValueError("Linked/reparse workflow path: " + str(item))
        if target is None:
            target = observed
    return target


def _identity_content(observed):
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_size,
        observed.st_mtime_ns,
    )


def read_regular(path):
    path = Path(path).absolute()
    initial_path = _lstat_nonreparse_chain(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > LIMIT:
            raise ValueError("Expected bounded regular workflow file: " + str(path))
        data = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
        final_path = _lstat_nonreparse_chain(path)

    initial_values = _identity_content(initial_path)
    before_values = _identity_content(before)
    after_values = _identity_content(after)
    path_values = _identity_content(final_path)
    reasons = []
    if initial_values[:2] != before_values[:2]:
        reasons.append("opened_identity")
    elif initial_values[2:] != before_values[2:]:
        reasons.append("opened_content_metadata")
    if before_values[:2] != after_values[:2]:
        reasons.append("descriptor_identity")
    elif before_values[2:] != after_values[2:]:
        reasons.append("descriptor_content_metadata")
    if len(data) != after.st_size:
        reasons.append("read_length")
    if path_values[:2] != after_values[:2]:
        reasons.append("path_identity")
    elif path_values[2:] != after_values[2:]:
        reasons.append("path_content_metadata")
    if reasons:
        raise ValueError(
            "Workflow file changed during observation: "
            f"{path}; reasons={','.join(reasons)}; before={before_values}; "
            f"after={after_values}; path={path_values}; read_length={len(data)}; "
            f"initial_path={initial_values}"
        )
    return data


def fingerprint(path):
    data = read_regular(path)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_new(path, data):
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def make_pdf(streams):
    # Original deterministic fixture, uncompressed so its source content is reviewable.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for stream in streams:
        n = len(objects) + 1
        kids.append(f"{n} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.275591 841.889764] /Resources << /Font << /F1 3 0 R >> >> /Contents {n+1} 0 R >>".encode()
        )
        data = stream.encode("ascii")
        objects.append(f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")
    objects[1] = f'<< /Type /Pages /Count {len(kids)} /Kids [{" ".join(kids)}] >>'.encode()
    result, offsets = b"%PDF-1.4\n", [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    pos = len(result)
    result += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets[1:])
    return (
        result
        + f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{pos}\n%%EOF\n".encode()
    )


def prepare(root):
    root = Path(root).absolute()
    for parent in (root.parent, *root.parent.parents):
        st = parent.lstat()
        if not stat.S_ISDIR(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
            raise ValueError("Fixture parent is not a non-link directory")
    root.mkdir()  # Existing path never conveys ownership or authorizes overwrite.
    pdf = root / "background.pdf"
    write_new(
        pdf,
        make_pdf(
            [
                "BT /F1 18 Tf 50 760 Td (Scriblark qualification source) Tj ET 1 0 0 RG 3 w 50 650 160 50 re S"
            ]
        ),
    )
    doc = ET.Element("xournal", creator="Scriblark owned qualification fixture", fileversion="4")
    ET.SubElement(doc, "title").text = "Synthetic owned Scriblark note"
    page = ET.SubElement(doc, "page", width="595.275591", height="841.889764")
    ET.SubElement(page, "background", type="pdf", domain="absolute", filename=str(pdf), pageno="1")
    layer = ET.SubElement(page, "layer")
    ET.SubElement(
        layer, "text", font="Arial", size="18", x="50", y="150", color="#000000ff"
    ).text = "Scriblark owned note"
    ET.SubElement(layer, "stroke", tool="pen", color="#0066ffff", width="3").text = (
        "50 210 90 220 130 210"
    )
    write_new(
        root / "source.xopp",
        gzip.compress(ET.tostring(doc, encoding="utf-8", xml_declaration=True), mtime=0),
    )
    originals = {name: fingerprint(root / name) for name in ("source.xopp", "background.pdf")}
    write_new(root / "originals.json", json.dumps(originals, indent=2).encode())
    return originals


def originals_unchanged(root):
    originals = json.loads(read_regular(root / "originals.json"))
    for name in ("source.xopp", "background.pdf"):
        if fingerprint(root / name) != originals[name]:
            raise ValueError("Protected original changed: " + name)
    return originals


def verify_note(root):
    root = Path(root)
    originals_unchanged(root)
    compressed = read_regular(root / "saved.xopp")
    # gzip's API is bounded here to avoid trusting an unbounded decompressed document.
    import io

    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Saved document exceeds bound")
    doc = ET.fromstring(data)
    pages = doc.findall("page")
    if len(pages) != 2:
        raise ValueError("Expected two saved note pages")
    if "Scriblark owned note" not in "".join(pages[0].itertext()) or not pages[0].findall(
        "./layer/stroke"
    ):
        raise ValueError("Original note content missing")
    background = pages[0].find("background")
    if background is None or background.get("type") != "pdf" or background.get("pageno") != "1":
        raise ValueError("Original PDF background missing")
    filename = Path(background.get("filename", ""))
    if not filename.is_absolute():
        filename = root / filename
    if os.path.normcase(os.path.abspath(filename)) != os.path.normcase(
        str((root / "background.pdf").absolute())
    ):
        raise ValueError("Original background path changed")
    background = pages[1].find("background")
    if (
        background is None
        or background.get("type") != "solid"
        or background.get("style") != "lined"
        or background.get("config") != "iq=2,m1=166,r1=24"
    ):
        raise ValueError("Saved Cornell template was not applied to new page")
    if (
        abs(float(pages[1].get("width")) - 595.275591) > 0.01
        or abs(float(pages[1].get("height")) - 841.889764) > 0.01
    ):
        raise ValueError("Saved template dimensions differ")
    return fingerprint(root / "saved.xopp")


def canonical(path):
    return os.path.normcase(os.path.abspath(path))


def verify_export(root, name, protected, tools):
    root = Path(root)
    originals_unchanged(root)
    verify_note(root)
    if name not in ("first.pdf", "reopened.pdf"):
        raise ValueError("Unknown workflow output")
    output = root / name
    before = fingerprint(output)
    reports = list(root.glob(name + ".*.inkquay-report.json"))
    if len(reports) != 1 or not re.fullmatch(
        re.escape(name) + r"\.[0-9a-f-]{36}\.inkquay-report\.json", reports[0].name
    ):
        raise ValueError("Expected one unique application PDF report")
    report_bytes = read_regular(reports[0])
    report_identity = {
        "bytes": len(report_bytes),
        "sha256": hashlib.sha256(report_bytes).hexdigest(),
    }
    report = json.loads(report_bytes)
    if (
        type(report.get("version")) is not int
        or report.get("version") != 1
        or report.get("status") != "passed"
        or report.get("published") is not True
        or report.get("error") != ""
        or report.get("warnings") != [SCOPE_DISCLOSURE]
        or report.get("recoveryFiles") != []
        or canonical(report.get("output", "")) != canonical(output)
    ):
        raise ValueError("Application report did not prove published checked output")
    for key, expected in [
        ("expectedPages", 2),
        ("actualPages", 2),
        ("outputBytes", before["bytes"]),
    ]:
        if type(report.get(key)) is not int or report[key] != expected:
            raise ValueError("Invalid application report " + key)
    expected = {canonical(root / p): fingerprint(root / p)["sha256"] for p in protected}
    actual = report.get("protectedFiles")
    if (
        not isinstance(actual, list)
        or len(actual) != len(expected)
        or {canonical(p["path"]): p["sha256Before"] for p in actual} != expected
    ):
        raise ValueError("Application report protected input identities differ")
    tool_evidence = {}

    def run(tool, args):
        executable = Path(tools[tool]).absolute()
        identity = fingerprint(executable)
        try:
            result = subprocess.run(
                [str(executable), *map(str, args)], capture_output=True, timeout=30
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError(
                f"{tool} timed out; stdout={(error.stdout or b'')[-8192:]!r}; stderr={(error.stderr or b'')[-8192:]!r}"
            ) from error
        if fingerprint(executable) != identity:
            raise ValueError("PDF checker executable changed")
        if result.returncode:
            raise ValueError(f"{tool} exit {result.returncode}: {result.stderr[-8192:]!r}")
        tool_evidence[tool] = dict(
            path=str(executable),
            **identity,
            exit_code=result.returncode,
            stderr=result.stderr.decode("utf-8", "replace")[-8192:],
        )
        return result.stdout

    info = run("pdfinfo", [output]).decode("utf-8", "replace")
    if not re.search(r"^Pages:\s+2\s*$", info, re.M):
        raise ValueError("Independent PDF page count differs")
    text = run("pdftotext", [output, "-"]).decode("utf-8", "replace")
    if any(token not in text for token in ("Scriblark qualification source", "Scriblark owned note")):
        raise ValueError("Independent PDF source/note text is missing")
    page_text = text.split("\f")
    if len(page_text) < 2 or any(
        token not in page_text[1] for token in ("Topic / Date", "Cues", "Notes", "Summary")
    ):
        raise ValueError("Independent exported Cornell template labels are missing")
    with tempfile.TemporaryDirectory(prefix="inkquay-pdf-render-") as temporary:
        prefix = Path(temporary).resolve() / "page"
        run("pdftoppm", ["-f", "2", "-l", "2", "-singlefile", "-scale-to", "850", output, prefix])
        ppm = read_regular(prefix.with_suffix(".ppm"))
        header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", ppm)
        if not header:
            raise ValueError("Unexpected independent PDF raster")
        width, height = map(int, header.groups())
        pixels = ppm[header.end() :]
        if len(pixels) != width * height * 3 or width < 500 or height < 750:
            raise ValueError("Incomplete PDF raster")
        dark = sum(min(pixels[i : i + 3]) < 225 for i in range(0, len(pixels), 3))
        # Cornell's real renderer scales the cue divider x=166/600 from y=56/800
        # through 648/800. Check its central span with a two-pixel raster tolerance.
        center = round(width * 166 / 600)
        rows = range(round(height * 0.12), round(height * 0.75))
        divider = max(
            sum(min(pixels[(y * width + x) * 3 : (y * width + x) * 3 + 3]) < 225 for y in rows)
            for x in range(center - 2, center + 3)
        )
        if dark < 200 or divider < len(rows) * 0.8:
            raise ValueError("Exported Cornell template ruling is missing")
    if fingerprint(output) != before:
        raise ValueError("Output changed during independent verification")
    if fingerprint(reports[0]) != report_identity:
        raise ValueError("Application report changed during verification")
    originals_unchanged(root)
    return dict(
        output=name,
        **before,
        pages=2,
        text_markers_verified=True,
        template_dark_pixels=dark,
        template_divider_pixels=divider,
        report_name=reports[0].name,
        report=report_identity,
        application_report=report,
        saved_note=fingerprint(root / "saved.xopp"),
        tools=tool_evidence,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["prepare", "note", "first", "reopened"])
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--tool-directory", type=Path)
    args = p.parse_args()
    if args.mode == "prepare":
        result = prepare(args.root)
    elif args.mode == "note":
        result = verify_note(args.root)
    else:
        if not args.tool_directory:
            p.error("tool-directory required")
        suffix = ".exe" if os.name == "nt" else ""
        tools = {
            name: args.tool_directory / (name + suffix)
            for name in ("pdfinfo", "pdftotext", "pdftoppm")
        }
        result = verify_export(
            args.root,
            args.mode + ".pdf",
            ("saved.xopp", "background.pdf") if args.mode == "first" else ("first.pdf",),
            tools,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
