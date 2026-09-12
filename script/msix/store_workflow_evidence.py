"""Independent complete installed workflow/evidence boundary for unsigned retention.
Copyright 2026 Trieflow LLC. MIT. No substitute for the actual native workflow.
"""

from datetime import datetime
from pathlib import Path, PureWindowsPath
import re
import math
import os
import hashlib
import msix_qualification as msix
from source_publication import require, fingerprint, load
from workflow_files import SCOPE_DISCLOSURE, original_files

HELPERS = (
    "qualify-msix-install.ps1",
    "qualify-workflow.ps1",
    "WorkflowNative.cs",
    "workflow_files.py",
)
EVENTS = [
    ("open-source.xopp", "Unsaved Document - Scriblark"),
    ("chooser-location", "Open file"),
    ("choose-source.xopp", "Open file"),
    ("configure-template", "source.xopp - Scriblark"),
    ("select-and-name-cornell-preset", "Configure new page template"),
    ("save-named-preset", "Configure new page template"),
    ("cancel-template-defaults", "Configure new page template"),
    ("configure-template", "source.xopp - Scriblark"),
    ("reload-saved-preset", "Configure new page template"),
    ("apply-saved-template", "Configure new page template"),
    ("insert-template-page", "source.xopp - Scriblark"),
    ("save-new-note", "*source.xopp - Scriblark"),
    ("chooser-location", "Save File"),
    ("choose-saved.xopp", "Save File"),
    ("open-export-menu-first.pdf", "saved.xopp - Scriblark"),
    ("export-first.pdf", "saved.xopp - Scriblark"),
    ("chooser-location", "Export File"),
    ("choose-first.pdf", "Export File"),
    ("dismiss-checked-export-report", None),
    ("open-first.pdf", "saved.xopp - Scriblark"),
    ("chooser-location", "Open file"),
    ("choose-first.pdf", "Open file"),
    ("open-export-menu-reopened.pdf", "first.pdf - Scriblark"),
    ("export-reopened.pdf", "first.pdf - Scriblark"),
    ("chooser-location", "Export File"),
    ("choose-reopened.pdf", "Export File"),
    ("dismiss-checked-export-report", None),
]
CAPTURES = {
    "saved-template": "Configure new page template",
    "reloaded-template": "Configure new page template",
    "saved-two-page-note": "saved.xopp - Scriblark",
    "first-report-dialog": None,
    "first-editor": "saved.xopp - Scriblark",
    "reopened-export": "first.pdf - Scriblark",
    "reopened-report-dialog": None,
    "reopened-editor": "first.pdf - Scriblark",
}


def positive(value):
    return type(value) is int and value > 0


def sha(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def fact(value):
    require(
        isinstance(value, dict)
        and positive(value.get("bytes"))
        and sha(value.get("sha256")),
        "Missing exact file identity",
    )


def winpath(path):
    require(
        isinstance(path, str) and PureWindowsPath(path).is_absolute(),
        "Expected absolute native path",
    )
    require(".." not in PureWindowsPath(path).parts, "Noncanonical native path")
    # CPython-MINGW uses '/' even for PureWindowsPath string rendering.
    # Keep the evidence comparison representation independent of that runtime.
    return PureWindowsPath(path).as_posix().replace("/", "\\").casefold()


def inside(path, root):
    return winpath(path).startswith(winpath(root).rstrip("\\") + "\\")


def screenshot(path, expected, width, height):
    require(msix.file_record(path)["sha256"] == expected, "Screenshot hash differs")
    with msix._regular_stream(path) as stream:
        data = stream.read(16 * 1024 * 1024 + 1)
    require(len(data) <= 16 * 1024 * 1024, "Screenshot exceeds bound")
    w, h, pixels = msix._decode_rgba_png(data)
    require(
        (w, h) == (math.ceil(width), math.ceil(height)) and w >= 200 and h >= 100,
        "Native screenshot dimensions differ",
    )
    require(
        len(
            set(
                tuple(pixels[y][x * 4 : x * 4 + 4])
                for y in range(0, h, 7)
                for x in range(0, w, 7)
            )
        )
        >= 16,
        "Native screenshot is blank",
    )


def modules(rows, record, package_name):
    require(
        isinstance(rows, list) and 7 <= len(rows) <= 512,
        "Incomplete module observation",
    )
    seen = set()
    runtime = set()
    package_root = None
    for row in rows:
        path = winpath(row["path"])
        require(
            path not in seen and sha(row["sha256"]),
            "Duplicate or invalid module observation",
        )
        seen.add(path)
        require(
            PureWindowsPath(path).name == row["name"].casefold(),
            "Module filename differs",
        )
        if row["origin"] == "package":
            rel = row["relative_path"]
            require(
                rel in record["payload"]
                and row["sha256"] == record["payload"][rel]["sha256"],
                "Module differs from current package",
            )
            tail = (
                "\\"
                + package_name.casefold()
                + "\\"
                + rel.replace("/", "\\").casefold()
            )
            require(
                path.endswith(tail)
                and "\\windowsapps\\" in path
                and row["platform_signature"] is None,
                "Package module path/identity differs",
            )
            root = path[: -len(rel.replace("/", "\\"))].rstrip("\\")
            if package_root is None:
                package_root = root
            require(root == package_root, "Modules span package installations")
            runtime.add(rel)
        elif row["origin"] == "windows":
            require(
                inside(path, os.environ.get("SystemRoot", r"C:\Windows"))
                and row["relative_path"] is None
                and row["platform_signature"] is None,
                "Foreign module mislabeled Windows",
            )
        elif row["origin"] == "microsoft_defender_signed_platform":
            signature = row["platform_signature"]
            require(
                re.fullmatch(
                    r"[a-z]:\\programdata\\microsoft\\windows defender\\platform\\\d+\.\d+\.\d+\.\d+-\d+\\mpoav\.dll",
                    path,
                )
                and row["relative_path"] is None
                and signature["sha256"] == row["sha256"]
                and signature["signature_status"] == "Valid"
                and signature["signer_common_name"]
                in (
                    "Microsoft Windows Publisher",
                    "Microsoft Corporation",
                    "Microsoft Windows",
                )
                and signature["signer_organization"] == "Microsoft Corporation"
                and re.fullmatch("[0-9a-fA-F]{40}", signature["signer_thumbprint"])
                and signature["signer_subject"]
                and signature["signer_issuer"],
                "Foreign or unverified Defender module",
            )
        else:
            raise ValueError("Unaccepted loaded-module origin")
    require(
        set(record["runtime"].values()) <= runtime,
        "Required packaged runtime not observed",
    )
    return package_root


def validate_original_fixture(originals, first_report):
    # The actual MINGW64 Python producer records paths with forward slashes;
    # the C++ report output uses escaped backslashes. Reproduce the producer's
    # exact input bytes, rather than normalizing recorded evidence in place.
    path = (
        PureWindowsPath(first_report["output"]).parent / "background.pdf"
    ).as_posix()
    expected = {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in original_files(path).items()
    }
    require(
        originals == expected,
        "Workflow inputs differ from deterministic current source fixture",
    )


def validate_installation(folder, record, source, context, mode, tool_directory):
    try:
        return _validate_installation(
            Path(folder), record, Path(source), context, mode, Path(tool_directory)
        )
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError(
            "Incomplete installed consumer evidence: " + str(error)
        ) from error


def _validate_installation(folder, record, source, context, mode, tool_directory):
    receipt = load(folder / "installation-qualification.json")
    identity = msix.identity_for_mode(mode)
    require(
        receipt["schema_version"] == 1
        and receipt["identity"] == identity
        and receipt["identity_mode"] == mode
        and receipt["qualification_identity_only"] is (mode == "qualification")
        and receipt["store_identity_used"] is (mode == "store"),
        "Installed identity/mode differs",
    )
    for key in ("source_commit", "workflow_run_id", "workflow_run_attempt"):
        require(
            receipt[key] == context[key] and isinstance(receipt[key], str),
            "Installed source/run/attempt differs",
        )
    for key in (
        "add_appx_completed",
        "registration_ownership_established",
        "unsigned_package_unchanged",
        "process_identity_ownership_established",
        "clean_close_verified",
        "uninstall_verified",
        "installation_qualification_passed",
        "workflow_acceptance",
        "template_pdf_workflow_tested",
        "interactive_pdf_workflows_verified",
    ):
        require(receipt[key] is True, "Incomplete installed acceptance: " + key)
    for key in (
        "certificate_private_key_exported",
        "diagnostic_observer_requested",
        "diagnostic_observer_attached",
        "diagnostic_run_completed",
        "physical_tablet_tested",
        "upgrade_tested",
        "wack_tested",
        "public_release",
    ):
        require(receipt[key] is False, "Unaccepted diagnostic/release claim: " + key)
    for key in (
        "preflight_package_full_names",
        "residual_package_full_names",
        "observer_diagnostic_errors",
        "cleanup_errors",
        "evidence_errors",
    ):
        require(receipt[key] == [], "Residual/error evidence: " + key)
    require(
        receipt["primary_error"] is None and receipt["diagnostic_observer"] is None,
        "Primary or observer evidence present",
    )
    full = receipt["package_full_name"]
    prefix = identity["packageName"] + "_" + identity["version"] + "_x64__"
    publisher_id = "r3hxytd7jt6c4" if mode == "store" else "fjvr7t994vwc4"
    require(
        full == prefix + publisher_id, "Exact package full name/publisher ID missing"
    )
    require(
        receipt["owned_package_full_name"]
        == receipt["activated_process_package_full_name"]
        == full
        and receipt["aumid"]
        == identity["packageName"] + "_" + full[len(prefix) :] + "!InkQuay",
        "Activated/owned package differs",
    )
    require(
        receipt["unsigned_package_sha256"]
        == record["containerVerification"]["package"]["sha256"]
        and sha(receipt["signed_copy_sha256"])
        and receipt["signed_copy_sha256"] != receipt["unsigned_package_sha256"]
        and receipt["executable_sha256"]
        == record["payload"]["bin/Scriblark.exe"]["sha256"],
        "Installed binary/package hashes differ",
    )
    require(
        receipt["qualification_helpers"]
        == {name: msix.file_record(source / "script/msix" / name) for name in HELPERS},
        "Qualification helpers differ from current source",
    )
    sign = receipt["signtool"]
    fact(sign)
    require(
        sign["sdk_version"] == "10.0.26100.0"
        and winpath(sign["path"])
        == winpath(str(
            PureWindowsPath(record["makeAppx"]["path"]).with_name("signtool.exe")
        )),
        "Signing tool SDK identity differs",
    )
    window = load(folder / "window-observation.json")
    require(window == receipt["window"], "Standalone/embedded window differs")
    pid = window["process_id"]
    require(
        positive(pid)
        and window["title"] == "Unsaved Document - Scriblark"
        and window["visible"] is True
        and window["screenshot_captured"] is True
        and window["screenshot_error"] is None
        and window["width"] >= 400
        and window["height"] >= 300
        and window["sampled_colors"] >= 16,
        "Actual startup window evidence incomplete",
    )
    tree = load(folder / "accessible-window-tree.json")
    require(tree == window["controls"], "Standalone accessible tree differs")
    require(
        len(
            [
                x
                for x in tree
                if x["name"] == window["title"]
                and x["control_type"] == "ControlType.Window"
                and x["offscreen"] is False
                and x["process_id"] == pid
            ]
        )
        == 1,
        "Owned accessible root missing",
    )
    screenshot(
        folder / "qualification-window.png",
        window["screenshot_sha256"],
        window["width"],
        window["height"],
    )
    for key in ("process_exit", "cleanup_process_exit"):
        exit = receipt[key]
        require(
            exit["process_id"] == pid
            and exit["wait_completed"] is True
            and type(exit["exit_code"]) is int
            and exit["exit_code"] == 0
            and exit["normal_exit"] is True
            and exit["observation_error"] is None,
            "Normal owned process exit/cleanup missing",
        )
    first_modules = load(folder / "loaded-modules.json")
    last_modules = load(folder / "workflow-loaded-modules.json")
    require(
        modules(first_modules, record, full) == modules(last_modules, record, full)
        and receipt["loaded_module_count"] == len(last_modules),
        "Post-workflow module observation differs",
    )
    workflow = load(folder / "workflow/workflow-result.json")
    require(workflow == receipt["workflow"], "Standalone/embedded workflow differs")
    for key in ("source_commit", "workflow_run_id", "workflow_run_attempt"):
        require(workflow[key] == context[key], "Workflow context differs")
    require(
        workflow["schema_version"] == 1
        and workflow["process_id"] == pid
        and workflow["package_full_name"] == full
        and workflow["passed"] is True
        and workflow["gtk_keyboard_workflow"] is True
        and workflow["diagnostic_observer"] is False
        and workflow["error"] is None
        and workflow["diagnostic_errors"] == []
        and workflow["failed_operation"] is None
        and workflow["crash_diagnostics"] is None,
        "Incomplete actual consumer workflow",
    )
    events = workflow["events"]
    require(len(events) == len(EVENTS), "Incomplete actual input sequence")
    main = events[0]["handle"]
    require(positive(main), "Missing owned main HWND")
    previous = None
    for event, (action, title) in zip(events, EVENTS):
        require(
            event["action"] == action
            and event["process_id"] == pid
            and positive(event["handle"])
            and (
                event["title"] == title
                if title is not None
                else event["title"] in ("", "Scriblark")
            ),
            "Actual input action/title/owner differs",
        )
        if title and title.endswith(" - Scriblark"):
            require(event["handle"] == main, "Input main HWND changed")
        if action.startswith(("open-export-menu-", "export-")):
            expected_count = 4 if action.startswith("open-") else 2
            require(event.get("native_input_method") == "SendInput"
                    and type(event.get("native_sendinput_events")) is int
                    and event["native_sendinput_events"] == expected_count,
                    "Native export chord insertion is incomplete or unobserved")
        instant = datetime.fromisoformat(
            re.sub(r"(\.\d{6})\d+(?=Z|[+-])", r"\1", event["at_utc"]).replace(
                "Z", "+00:00"
            )
        )
        require(
            instant.tzinfo is not None and (previous is None or instant >= previous),
            "Input timestamps are not ordered",
        )
        previous = instant
    for name, title in CAPTURES.items():
        snap = load(folder / "workflow" / (name + ".json"))
        w = snap["window"]
        require(
            w["ProcessId"] == pid
            and w["Visible"] is True
            and w["Enabled"] is True
            and w["ClassName"] == "gdkWindowToplevel"
            and positive(w["Handle"])
            and (
                w["Title"] == title
                if title is not None
                else w["Title"] in ("", "Scriblark")
            )
            and snap["sampled_colors"] >= 16
            and snap["screenshot"] == name + ".png",
            "Actual workflow capture differs",
        )
        if title and title.endswith(" - Scriblark"):
            require(w["Handle"] == main, "Captured editor HWND differs")
        else:
            require(
                w["Owner"] == main and w["Handle"] != main,
                "Captured dialog owner differs",
            )
        screenshot(
            folder / "workflow" / (name + ".png"),
            snap["sha256"],
            w["Width"],
            w["Height"],
        )
    originals = workflow["originals"]
    require(
        set(originals) == {"source.xopp", "background.pdf"},
        "Original fixture identities missing",
    )
    for original in originals.values():
        fact(original)
    first = workflow["first"]
    reopened = workflow["reopened"]
    fact(first["saved_note"])
    require(
        reopened["saved_note"] == first["saved_note"],
        "Saved two-page note changed across reopen/export",
    )
    roots = []
    for name, output in (("first", first), ("reopened", reopened)):
        fact(output)
        fact(output["report"])
        require(
            output["output"] == name + ".pdf"
            and output["pages"] == 2
            and output["text_markers_verified"] is True
            and output["template_raster_width"] >= 500
            and output["template_raster_height"] >= 750
            and output["template_dark_pixels"] >= 200
            and output["template_divider_pixels"]
            >= (
                round(output["template_raster_height"] * 0.75)
                - round(output["template_raster_height"] * 0.12)
            )
            * 0.8,
            "Independent PDF content/ruling check incomplete",
        )
        report_path = folder / "workflow" / (name + "-application-report.json")
        report = load(report_path)
        require(
            msix.file_record(report_path) == output["report"]
            and report == output["application_report"],
            "Original application report differs",
        )
        require(
            re.fullmatch(
                name + r"\.pdf\.[0-9a-f-]{36}\.inkquay-report\.json",
                output["report_name"],
            )
            is not None,
            "Unique report filename missing",
        )
        require(
            msix.file_record(
                folder / "workflow" / ("retained-" + output["report_name"])
            )
            == output["report"],
            "Retained original report differs",
        )
        require(
            report["version"] == 1
            and report["status"] == "passed"
            and report["published"] is True
            and report["error"] == ""
            and report["warnings"] == [SCOPE_DISCLOSURE]
            and report["recoveryFiles"] == []
            and report["expectedPages"] == report["actualPages"] == 2
            and report["outputBytes"] == output["bytes"],
            "Application checked export failed or has unexpected scope",
        )
        path = PureWindowsPath(report["output"])
        require(
            path.name == name + ".pdf" and path.parent.name == "consumer-files",
            "Unexpected owned consumer output path",
        )
        root = str(path.parent)
        winpath(root)
        roots.append(winpath(root))
        protected = report["protectedFiles"]
        expected = (
            {
                "saved.xopp": first["saved_note"]["sha256"],
                "background.pdf": originals["background.pdf"]["sha256"],
            }
            if name == "first"
            else {"first.pdf": first["sha256"]}
        )
        require(
            len(protected) == len(expected)
            and {winpath(x["path"]): x["sha256Before"] for x in protected}
            == {
                winpath(str(PureWindowsPath(root) / key)): value
                for key, value in expected.items()
            },
            "Protected input/hash continuity differs",
        )
        require(
            set(output["tools"]) == {"pdfinfo", "pdftotext", "pdftoppm"},
            "Independent PDF tool observations missing",
        )
        for tool, observed in output["tools"].items():
            require(
                Path(observed["path"]).absolute()
                == (tool_directory / (tool + ".exe")).absolute()
                and fingerprint(observed)
                == msix.file_record(tool_directory / (tool + ".exe"))
                and observed["exit_code"] == 0
                and isinstance(observed["stderr"], str),
                "Independent PDF checker changed or failed",
            )
    require(
        len(set(roots)) == 1, "PDF exports do not share the owned consumer input root"
    )
    validate_original_fixture(originals, first["application_report"])
    return {
        "process_id": pid,
        "package_full_name": full,
        "input_events": len(events),
        "workflow_captures": len(CAPTURES),
        "first_pdf": fingerprint(first),
        "reopened_pdf": fingerprint(reopened),
        "saved_note": first["saved_note"],
        "normal_close": True,
        "uninstalled": True,
        "diagnostic_observer": False,
    }
