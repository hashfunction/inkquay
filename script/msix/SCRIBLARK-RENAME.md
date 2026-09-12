# Scriblark runtime and package rename

Prepared from `ed6dc86e94ec68c466744154ac543e865ccdfd82` while the exact original diagnostic Windows run `34687949814` continues independently.

The application is now named Scriblark, version 1.0.1. Customer-facing main-window titles, About/preferences/file dialogs, print jobs, Windows version resources, desktop metadata, support/source links and first-party notices use Scriblark. CMake still uses its original internal project and target names, but emits `Scriblark` and `Scriblark-wrapper`; the wrapper starts the new executable. The optional desktop/bundle packaging references follow those outputs. Original artwork pixels and upstream attribution remain unchanged.

Windows staging, application/wrapper inventory, startup checks, installed executable/module checks, diagnostic target checks, fixture labels and exact title checks use the new executable names. The temporary MSIX filename is `Scriblark.Qualification_1.0.1.0_x64.msix`. Its package identity remains `Trieflow.InkQuay.Qualification`, publisher remains `CN=InkQuay-CI-Qualification`, and application ID remains `InkQuay`. The assigned Microsoft Store identity will likewise retain its original account identity when the separate Store export is implemented.

Existing `%APPDATA%/InkQuay` configuration, `com.trieflow.inkquay` GTK/bundle identity, resource paths under `share/inkquay`, page-template identifiers, export-report format/extension and recipe settings remain compatible. The optional NSIS script retains its registry/ProgID/install-location keys while using the new visible labels and executable targets. It is not the Store package, and no NSIS or macOS release is claimed.

No application save, PDF export, page-template, file-ownership, debugger attach/exit, input or cleanup policy is changed. No original native result is relabeled as a Scriblark result. Current diagnostic run `34687949814` still identifies the earlier InkQuay executable and source. A fresh Windows run must compile the renamed source, exercise its actual GUI workflow and verify normal close/uninstall before release.

Local verification:

- 30 actual-file/ZIP/package-boundary tests passed.
- Nine native-inventory tests and 11 document/PDF oracle tests passed.
- Eight GDB observer tests passed, including updated exact executable fixtures.
- Seven separate PowerShell suites passed: rendered-window evidence, actual module collector, installation orchestration, registration ownership, source-backed workflow helpers, workflow crash matching and observer ownership. The native HWND fixture correctly reports it was not executed on macOS.
- All UI Glade and AppStream XML plus the bundle plist parsed. Legacy configuration source and all 735 retained original notice/source files remain byte-identical to the baseline.

The first-party source index now points to `https://scriblark.trieflow.com/source`; original source archives and notice hashes are preserved. Tests above do not establish a native Windows pass or resolve the earlier observed Save crash.
