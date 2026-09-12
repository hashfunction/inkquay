# Scriblark one-shot File-menu observation

This separate candidate is based on Store/export commit
`040119b9e7c333c114e586ec4e1ca42f4ddf7041`. It changes the external installed
workflow observer and its exact event verifier only. No application code,
identity, package version, source publication, historical evidence, Store/site
state or publication was changed.

## Actual failure and source evidence

Run `34691122756`, source/public commit
`a56efe8f3e43b162a3911f43de43db2d81c6aa9c`, passed 135 native tests. Its real
uninstrumented installed workflow inserted the saved Cornell preset, saved the
two-page note, exported and independently checked `first.pdf`, dismissed the
owned checked-export report, and reopened that PDF. The first PDF was 24,219
bytes, SHA-256
`e15a70ddf769d32938c67a95345843c177cbe697053a99cfa12005c904ecb6b7`.

The receipt contains 22 completed input events, ending with:

| UTC on 2026-09-12 | Action | Actual title / HWND |
| --- | --- | --- |
| 11:49:23.8516191 | export-first.pdf | saved.xopp - Scriblark / 328084 |
| 11:49:24.2716824 | chooser-location | Export File / 655754 |
| 11:49:25.1841877 | choose-first.pdf | Export File / 655754 |
| 11:49:26.5577589 | dismiss-checked-export-report | empty title / 720950 |
| 11:49:27.1884568 | open-first.pdf | saved.xopp - Scriblark / 328084 |
| 11:49:27.6104292 | chooser-location | Open file / 786486 |
| 11:49:28.5268729 | choose-first.pdf | Open file / 786486 |
| 11:49:29.7844761 | export-reopened.pdf | first.pdf - Scriblark / 328084 |

All are PID 8244. The second `%fe` was followed by the original error
`Expected one exact owned workflow window: Export File (found 0)`. At failure,
the retained process was alive and its sole visible native window was the enabled
`gdkWindowToplevel` HWND 328084, owner 0, titled `first.pdf - Scriblark`, at
(130,81), 816×639. The actual failure PNG was viewed: it shows the reopened
two-page PDF editor, without an export chooser. Later owned cleanup forced exit
-1. This is not a new crash finding or a completed installed qualification.

Original evidence under the downloaded artifact's `msix-install/workflow`:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| workflow-result.json | 8121 | 17ff0027c2788d53b7ddb44055d4ae54cf8c45122339f746232dd6bc85be2afb |
| failure-windows.json | 237 | 109066f805663c84d2eb211d21348adf555f6b3848a4b9dfabd5ba39d4341bc6 |
| failure.png | 79044 | b4e420a435fda64f246a29bda5f024c945efc752ac09ee2fa1576854e7258632 |

Current `ui/mainmenubar.xml` has exactly one `_File` submenu and a direct
`win.export-as-pdf` item labeled `_Export as PDF`. The separate `win.export-as`
item, `Export as...`, uses Ctrl+E and is a different action. The source contract
now checks the exact File/PDF-export labels and action before running the UI.
`Control::exportAsPdf()` in `src/core/control/Control.cpp` creates `PdfExportJob`
and calls `showFileChooser`; `BaseExportJob.cpp` constructs `SaveExportDialog`
with title `Export File`. Those source paths do not establish why the second
mnemonic did not produce the chooser. No speculative runtime fix was made.

## Bounded observation and input sequence

Each original `%fe` is split into one `%f` and one `e`. There is one initial
owned-main focus operation, with no refocus or retry between these two sends.
For both `first` and `reopened`, production executes:

1. Observe `before-file`.
2. Send `%f`, record `open-export-menu-first.pdf` or
   `open-export-menu-reopened.pdf`.
3. Observe `after-file`.
4. Observe `before-export`.
5. Send `e`, record the existing `export-first.pdf` or `export-reopened.pdf`.
6. Observe `after-export`.

The independent Store verifier now requires all **27** exact action/title/PID/HWND
and ordered timestamp events, including those two new adjacent pairs. The first
pair uses `saved.xopp - Scriblark`; the reopened pair uses
`first.pdf - Scriblark`. All subsequent real chooser, file/report, PDF content,
reopen, eight original screenshots, module, normal-exit and cleanup gates remain.

Each observation retains actual main/foreground/focus HWNDs and PIDs,
GetGUIThreadInfo flags/menu owner, modifier state, same-process native windows
with title/class/rect/visible/enabled facts, and a bounded owner chain. Each send
freshly rechecks the retained process handle, executable and exact package, then
native input ownership. Foreground must be the enabled exact main window or one
uniquely observed visible/enabled `gdkWindowTemp` whose actual owner chain reaches
the main. Focus must be in that same process and rooted in the main/accepted
popup. Foreign foreground/focus, inconsistent ownership or changed title stops
input. The second send never restores/focuses the main window.

Optional UIA Menu/MenuItem facts are observed only under the retained main and
an actual foreground GTK popup: at most two roots, 256 returned elements per
root, 128 menu controls, 512 characters per name, and bounded error strings.
Empty/unsupported UIA is explicitly retained; it is not menu readiness or export
success. No synthetic menu property or provider is introduced. Native windows
retain the existing 100-window bound and owner traversal is limited to 16.
These are result/traversal bounds; individual synchronous OS/UIA calls are not
represented as cancellable remote-call timeouts.

The PNGs copy actual main-window screen pixels without `ShowWindow` or
`SetForegroundWindow`, because refocusing could dismiss the observed menu. Each
has a unique name and hash, as do the JSON snapshots indexed by the already
source/run/package-bound workflow receipt. Optional UIA/PNG errors are recorded
in the observation. An input/observation exception stops the sequence, attempts
one read-only `input-failure` snapshot, and preserves the original exception even
if secondary observation/recording fails. There is no mutating-action replay.
Missing menu metadata does not replace any original consumer acceptance predicate.

## Verification and limits

- **93** Python MSIX tests passed in 99.995 seconds, including all existing
  actual Poppler checks, source closure, Store identity/export, diagnostic and
  workflow boundaries. Log: `/private/tmp/scriblark-export-menu-python.log`.
- **14** isolated PowerShell suites passed, plus the ten actual registration
  ownership scenarios in Store mode. All MSIX PowerShell files parsed. Log:
  `/private/tmp/scriblark-export-menu-powershell.log`.
- The new fixture invokes the actual production sequence and C# input guard.
  It covers both exact source-backed sequences; six failure boundaries for each;
  secondary-error and original-error retention; main and owned-popup positives;
  twelve negative foreground/focus/ownership/visibility/title cases; and four
  actual source XML label/action mutations. The independent Python verifier
  rejects omission, replay, reordering or title substitution of either new input.
- The existing Windows HWND fixture now checks the real collector against an
  actual WinForms child Edit focus and an owned popup/main owner chain, including
  wrong-PID rejection. That branch explicitly did not execute on macOS. C#
  compilation and pure guard tests did execute using PowerShell 7.6.6 at
  `/Users/hashfunction/workspace/project_app_factory/microsoft-store/apps/filequay/source/.tools/powershell-7.6.6/pwsh`;
  this was read-only runtime reuse, with no FileQuay edits.
- The changed Python modules pass Black checking, and `git diff --check` is clean.
  The initial sequence fixture failed before implementation; later validation
  caught and corrected a fixture variable collision without changing semantics.

Root independent review and a fresh actual Windows dual-identity run are still
required. The actual new menu/focus state, full second PDF export, normal close,
and Store unsigned retention are not claimed by these portable tests. Observation
and the explicit interval between sends may affect timing; a later successful run
would establish that exact flow, not prove the cause of the old missing chooser.
