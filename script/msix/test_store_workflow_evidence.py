"""Coherent actual-file receipt fixtures exercise the independent exporter boundary.
These are parser tests, never evidence of Windows execution.
"""

import copy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import tempfile
import struct
import zlib
import unittest
from unittest.mock import patch
import msix_qualification as msix
import store_workflow_evidence as policy
from source_publication import fingerprint


class MinGWRenderedWindowsPath(PureWindowsPath):
    """Replay CPython-MINGW 3.14.7's sys._use_alt_sep rendering on any host.

    Parsing remains Windows parsing; only the documented fork's string
    separator differs. This is a parser fixture, not native execution.
    """

    def __str__(self):
        return super().__str__().replace("\\", "/")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.folder = self.root / "installed"
        self.folder.mkdir()
        (self.folder / "workflow").mkdir()
        self.source = Path(__file__).resolve().parents[2]
        self.tools = self.root / "tools"
        self.tools.mkdir()
        for name in ("pdfinfo", "pdftotext", "pdftoppm"):
            (self.tools / (name + ".exe")).write_bytes(name.encode())
        self.context = {
            "source_commit": "a" * 40,
            "workflow_run_id": "123",
            "workflow_run_attempt": "1",
        }
        self.image = (
            b"\x89PNG\r\n\x1a\n"
            + msix._chunk(b"IHDR", struct.pack(">IIBBBBB", 400, 400, 8, 6, 0, 0, 0))
            + msix._chunk(
                b"IDAT",
                zlib.compress(
                    b"".join(
                        b"\x00"
                        + b"".join(
                            bytes((x % 256, y % 256, (x + y) % 256, 255))
                            for x in range(400)
                        )
                        for y in range(400)
                    )
                ),
            )
            + msix._chunk(b"IEND", b"")
        )
        self.image_sha = hashlib.sha256(self.image).hexdigest()
        self.full = "1659hashfunction.InkQuay_1.0.1.0_x64__r3hxytd7jt6c4"
        self.record = {
            "identity": msix.STORE_IDENTITY,
            "containerVerification": {"package": {"sha256": "b" * 64}},
            "payload": {},
            "runtime": msix.RUNTIME,
            "makeAppx": {
                "path": r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe"
            },
        }
        modules = []
        for name in msix.RUNTIME.values():
            self.record["payload"][name] = {"bytes": 5, "sha256": "c" * 64}
            modules.append(
                {
                    "name": Path(name).name,
                    "path": "C:\\Program Files\\WindowsApps\\"
                    + self.full
                    + "\\"
                    + name.replace("/", "\\"),
                    "origin": "package",
                    "relative_path": name,
                    "sha256": "c" * 64,
                    "platform_signature": None,
                }
            )
        self.write("loaded-modules.json", modules)
        self.write("workflow-loaded-modules.json", modules)
        window = {
            "process_id": 17,
            "title": "Unsaved Document - Scriblark",
            "visible": True,
            "screenshot_captured": True,
            "screenshot_error": None,
            "width": 400,
            "height": 400,
            "sampled_colors": 25,
            "screenshot_sha256": self.image_sha,
            "controls": [
                {
                    "name": "Unsaved Document - Scriblark",
                    "control_type": "ControlType.Window",
                    "offscreen": False,
                    "process_id": 17,
                }
            ],
        }
        self.write("window-observation.json", window)
        self.write("accessible-window-tree.json", window["controls"])
        (self.folder / "qualification-window.png").write_bytes(self.image)
        events = [
            {
                "action": action,
                "title": title if title is not None else "Scriblark",
                "process_id": 17,
                "handle": 100 if title and title.endswith(" - Scriblark") else 101,
                "at_utc": f"2026-09-12T10:00:{i:02d}.1234567Z",
            }
            for i, (action, title) in enumerate(policy.EVENTS)
        ]
        for event in events:
            if event['action'].startswith(('open-export-menu-', 'export-')):
                event['native_input_method'] = 'SendInput'
                event['native_sendinput_events'] = 4 if event['action'].startswith('open-') else 2
        self.workflow = {
            "schema_version": 1,
            **self.context,
            "process_id": 17,
            "package_full_name": self.full,
            "passed": True,
            "gtk_keyboard_workflow": True,
            "diagnostic_observer": False,
            "error": None,
            "diagnostic_errors": [],
            "failed_operation": None,
            "crash_diagnostics": None,
            "events": events,
            "originals": {
                "source.xopp": {"bytes": 300, "sha256": "d" * 64},
                "background.pdf": {"bytes": 700, "sha256": "e" * 64},
            },
        }
        for name, title in policy.CAPTURES.items():
            self.write(
                "workflow/" + name + ".json",
                {
                    "window": {
                        "ProcessId": 17,
                        "Visible": True,
                        "Enabled": True,
                        "ClassName": "gdkWindowToplevel",
                        "Handle": (
                            100 if title and title.endswith(" - Scriblark") else 101
                        ),
                        "Owner": 100,
                        "Title": title if title is not None else "Scriblark",
                        "Width": 400,
                        "Height": 400,
                    },
                    "sampled_colors": 25,
                    "screenshot": name + ".png",
                    "sha256": self.image_sha,
                },
            )
            (self.folder / "workflow" / (name + ".png")).write_bytes(self.image)
        for name in ("first", "reopened"):
            root = r"C:\owned-temporary\consumer-files"
            report = {
                "version": 1,
                "status": "passed",
                "published": True,
                "error": "",
                "warnings": [policy.SCOPE_DISCLOSURE],
                "recoveryFiles": [],
                "expectedPages": 2,
                "actualPages": 2,
                "outputBytes": 1200,
                "output": root + "\\" + name + ".pdf",
                "protectedFiles": [
                    {"path": root + "\\" + path, "sha256Before": sha}
                    for path, sha in (
                        [("saved.xopp", "f" * 64), ("background.pdf", "e" * 64)]
                        if name == "first"
                        else [("first.pdf", "1" * 64)]
                    )
                ],
            }
            report_name = name + ".pdf." + "a" * 36 + ".inkquay-report.json"
            self.write("workflow/" + name + "-application-report.json", report)
            self.write("workflow/retained-" + report_name, report)
            self.workflow[name] = {
                "output": name + ".pdf",
                "bytes": 1200,
                "sha256": "1" * 64 if name == "first" else "2" * 64,
                "pages": 2,
                "text_markers_verified": True,
                "template_raster_width": 600,
                "template_raster_height": 850,
                "template_dark_pixels": 5000,
                "template_divider_pixels": 500,
                "report_name": report_name,
                "report": msix.file_record(
                    self.folder / "workflow" / (name + "-application-report.json")
                ),
                "application_report": report,
                "saved_note": {"bytes": 500, "sha256": "f" * 64},
                "tools": {
                    tool: {
                        "path": str(self.tools / (tool + ".exe")),
                        **msix.file_record(self.tools / (tool + ".exe")),
                        "exit_code": 0,
                        "stderr": "",
                    }
                    for tool in ("pdfinfo", "pdftotext", "pdftoppm")
                },
            }
        self.workflow["originals"] = {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in policy.original_files(
                "C:/owned-temporary/consumer-files/background.pdf"
            ).items()
        }
        self.workflow["first"]["application_report"]["protectedFiles"][1][
            "sha256Before"
        ] = self.workflow["originals"]["background.pdf"]["sha256"]
        self.write(
            "workflow/first-application-report.json",
            self.workflow["first"]["application_report"],
        )
        self.write(
            "workflow/retained-" + self.workflow["first"]["report_name"],
            self.workflow["first"]["application_report"],
        )
        self.workflow["first"]["report"] = msix.file_record(
            self.folder / "workflow/first-application-report.json"
        )
        self.receipt = {
            "schema_version": 1,
            **self.context,
            "identity": msix.STORE_IDENTITY,
            "identity_mode": "store",
            "qualification_identity_only": False,
            "store_identity_used": True,
            "package_full_name": self.full,
            "owned_package_full_name": self.full,
            "activated_process_package_full_name": self.full,
            "aumid": "1659hashfunction.InkQuay_r3hxytd7jt6c4!InkQuay",
            "unsigned_package_sha256": "b" * 64,
            "signed_copy_sha256": "9" * 64,
            "executable_sha256": "c" * 64,
            "qualification_helpers": {
                name: msix.file_record(self.source / "script/msix" / name)
                for name in policy.HELPERS
            },
            "signtool": {
                "path": str(
                    policy.PureWindowsPath(self.record["makeAppx"]["path"]).with_name(
                        "signtool.exe"
                    )
                ),
                "bytes": 123,
                "sha256": "a" * 64,
                "sdk_version": "10.0.26100.0",
            },
            "window": window,
            "loaded_module_count": len(modules),
            "primary_error": None,
            "diagnostic_observer": None,
        }
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
            self.receipt[key] = True
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
            self.receipt[key] = False
        for key in (
            "preflight_package_full_names",
            "residual_package_full_names",
            "observer_diagnostic_errors",
            "cleanup_errors",
            "evidence_errors",
        ):
            self.receipt[key] = []
        for key in ("process_exit", "cleanup_process_exit"):
            self.receipt[key] = {
                "process_id": 17,
                "wait_completed": True,
                "exit_code": 0,
                "normal_exit": True,
                "observation_error": None,
            }
        self.publish()

    def write(self, name, data):
        (self.folder / name).write_text(json.dumps(data), encoding="utf8")

    def publish(self):
        self.receipt["workflow"] = copy.deepcopy(self.workflow)
        self.write("workflow/workflow-result.json", self.workflow)
        self.write("installation-qualification.json", self.receipt)

    def check(self):
        return policy.validate_installation(
            self.folder, self.record, self.source, self.context, "store", self.tools
        )

    def test_real_windows_original_input_bytes_and_report_paths(self):
        actual = json.loads(
            (
                self.source
                / "script/msix/fixtures/scriblark-34691122756-first-export.json"
            ).read_text()
        )
        policy.validate_original_fixture(
            actual["originals"], actual["first"]["application_report"]
        )
        actual["originals"]["source.xopp"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "deterministic current source"):
            policy.validate_original_fixture(
                actual["originals"], actual["first"]["application_report"]
            )

    def test_complete_disposable_identity_replay(self):
        full = "Trieflow.InkQuay.Qualification_1.0.1.0_x64__fjvr7t994vwc4"
        self.receipt.update(
            identity=msix.QUALIFICATION_IDENTITY,
            identity_mode="qualification",
            qualification_identity_only=True,
            store_identity_used=False,
            package_full_name=full,
            owned_package_full_name=full,
            activated_process_package_full_name=full,
            aumid="Trieflow.InkQuay.Qualification_fjvr7t994vwc4!InkQuay",
        )
        self.record["identity"] = msix.QUALIFICATION_IDENTITY
        self.workflow["package_full_name"] = full
        for filename in ("loaded-modules.json", "workflow-loaded-modules.json"):
            rows = json.loads((self.folder / filename).read_text())
            for row in rows:
                row["path"] = row["path"].replace(self.full, full)
            self.write(filename, rows)
        self.publish()
        result = policy.validate_installation(
            self.folder,
            self.record,
            self.source,
            self.context,
            "qualification",
            self.tools,
        )
        self.assertEqual(result["package_full_name"], full)

    def test_wrong_publisher_family_is_rejected(self):
        full = self.full.replace("r3hxytd7jt6c4", "aaaaaaaaaaaaa")
        self.receipt.update(
            package_full_name=full,
            owned_package_full_name=full,
            activated_process_package_full_name=full,
            aumid="1659hashfunction.InkQuay_aaaaaaaaaaaaa!InkQuay",
        )
        self.workflow["package_full_name"] = full
        self.publish()
        with self.assertRaisesRegex(ValueError, "publisher ID"):
            self.check()

    def test_complete_independent_replay(self):
        self.assertEqual(self.check()["input_events"], 27)

    def test_mingw_path_rendering_preserves_complete_receipt_and_refusals(self):
        with patch.object(policy, "PureWindowsPath", MinGWRenderedWindowsPath):
            self.assertEqual(
                policy.winpath(r"C:\Program Files\WindowsApps\Package\bin\App.exe"),
                r"c:\program files\windowsapps\package\bin\app.exe",
            )
            self.assertEqual(self.check()["input_events"], 27)
            rows = json.loads((self.folder / "loaded-modules.json").read_text())
            for origin in ("WindowsAppsBackup", "foreign"):
                changed = copy.deepcopy(rows)
                changed[0]["path"] = changed[0]["path"].replace("WindowsApps", origin)
                with self.assertRaisesRegex(ValueError, "Package module path/identity"):
                    policy.modules(changed, self.record, self.full)
            with self.assertRaisesRegex(ValueError, "Noncanonical"):
                policy.winpath(r"C:\owned\..\foreign\App.exe")

    def test_export_menu_inputs_are_exact_one_shot_pairs(self):
        self.assertEqual(
            [x for x in policy.EVENTS if "export-" in x[0] and "report" not in x[0]],
            [
                ("open-export-menu-first.pdf", "saved.xopp - Scriblark"),
                ("export-first.pdf", "saved.xopp - Scriblark"),
                ("open-export-menu-reopened.pdf", "first.pdf - Scriblark"),
                ("export-reopened.pdf", "first.pdf - Scriblark"),
            ],
        )
        original = copy.deepcopy(self.workflow)
        for action in ("open-export-menu-first.pdf", "open-export-menu-reopened.pdf"):
            for mutation in ("omit", "replay", "reorder", "wrong-title"):
                self.workflow = copy.deepcopy(original)
                events = self.workflow["events"]
                index = next(i for i, e in enumerate(events) if e["action"] == action)
                if mutation == "omit":
                    del events[index]
                elif mutation == "replay":
                    events.insert(index, copy.deepcopy(events[index]))
                elif mutation == "reorder":
                    events[index], events[index + 1] = events[index + 1], events[index]
                else:
                    events[index]["title"] = "another document - Scriblark"
                self.publish()
                with self.subTest(action=action, mutation=mutation), self.assertRaises(
                    ValueError
                ):
                    self.check()

    def test_native_export_emission_requires_typed_complete_event_counts(self):
        original = copy.deepcopy(self.workflow)
        for action in ('open-export-menu-first.pdf', 'export-first.pdf',
                       'open-export-menu-reopened.pdf', 'export-reopened.pdf'):
            for field, value in [('native_sendinput_events', None), ('native_sendinput_events', True),
                                 ('native_sendinput_events', 0), ('native_sendinput_events', 3),
                                 ('native_input_method', 'SendKeys')]:
                self.workflow = copy.deepcopy(original)
                next(e for e in self.workflow['events'] if e['action'] == action)[field] = value
                self.publish()
                with self.subTest(action=action, field=field, value=value), self.assertRaisesRegex(ValueError, 'Native export'):
                    self.check()

    def test_partial_workflow_and_coherent_fabricated_success_fail(self):
        original = copy.deepcopy(self.workflow)
        for field, value in [
            ("events", []),
            ("first", None),
            ("diagnostic_observer", True),
            ("process_id", 18),
            ("diagnostic_errors", ["failure"]),
            ("workflow_run_attempt", "2"),
            (
                "originals",
                {
                    "source.xopp": {"bytes": 300, "sha256": "0" * 64},
                    "background.pdf": {"bytes": 700, "sha256": "e" * 64},
                },
            ),
            ("failed_operation", {"action": "save-new-note"}),
        ]:
            self.workflow = copy.deepcopy(original)
            self.workflow[field] = value
            self.publish()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check()

    def test_input_owner_action_and_order_mutation_fail(self):
        original = copy.deepcopy(self.workflow)
        for field, value in [
            ("action", "fabricated-save"),
            ("title", "wrong window"),
            ("handle", 999),
            ("process_id", 18),
            ("at_utc", "2020-01-01T00:00:00Z"),
        ]:
            self.workflow = copy.deepcopy(original)
            self.workflow["events"][11][field] = value
            self.publish()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check()

    def test_output_note_raster_and_tool_continuity_fail(self):
        original = copy.deepcopy(self.workflow)
        for mutation in ("note", "ruling", "text", "tool", "report"):
            self.workflow = copy.deepcopy(original)
            output = self.workflow["reopened"]
            if mutation == "note":
                output["saved_note"]["sha256"] = "0" * 64
            if mutation == "ruling":
                output["template_divider_pixels"] = 200
            if mutation == "text":
                output["text_markers_verified"] = False
            if mutation == "tool":
                output["tools"]["pdfinfo"]["sha256"] = "0" * 64
            if mutation == "report":
                output["application_report"]["protectedFiles"] = []
            self.publish()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check()

    def test_standalone_equality_and_original_files_are_required(self):
        self.workflow["events"][0]["at_utc"] = "2026-09-12T09:00:00Z"
        self.write("workflow/workflow-result.json", self.workflow)
        with self.assertRaisesRegex(ValueError, "Standalone/embedded workflow"):
            self.check()
        self.publish()
        (self.folder / "workflow/first-editor.png").write_bytes(b"edited image")
        with self.assertRaisesRegex(ValueError, "Screenshot hash"):
            self.check()

    def test_cleanup_and_diagnostic_flags_fail_closed(self):
        original = copy.deepcopy(self.receipt)
        for mutation in (
            "observer",
            "normal_exit",
            "uninstall",
            "residual",
            "source",
            "private_key",
        ):
            self.receipt = copy.deepcopy(original)
            if mutation == "observer":
                self.receipt["diagnostic_observer_requested"] = True
            if mutation == "normal_exit":
                self.receipt["process_exit"]["exit_code"] = 1
            if mutation == "uninstall":
                self.receipt["uninstall_verified"] = False
            if mutation == "residual":
                self.receipt["residual_package_full_names"] = [self.full]
            if mutation == "source":
                self.receipt["source_commit"] = "b" * 40
            if mutation == "private_key":
                self.receipt["certificate_private_key_exported"] = True
            self.publish()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check()

    def test_post_workflow_foreign_or_changed_module_fails(self):
        rows = json.loads((self.folder / "workflow-loaded-modules.json").read_text())
        rows[0]["path"] = r"C:\foreign\Scriblark.exe"
        self.write("workflow-loaded-modules.json", rows)
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
