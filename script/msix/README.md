# InkQuay temporary MSIX qualification

This pipeline packages the unchanged native `build/dist` stage with a disposable
`Trieflow.InkQuay.Qualification` identity. It does not reserve a Store name, use a
production certificate, publish native binaries or establish license clearance.

The stage receipt binds all files to the same-run MINGW64 provenance inventory,
both compiled executable hashes, exact installed package owner versions and the
source commit. Original source notices and PNG/SVG artwork are byte matched.
Unowned non-executable resources remain explicit audit inputs. Package startup
must identify the actual `Unsaved Document - InkQuay` window and bind the complete
stage receipt. The icon passed to packaging must equal the source-bound PNG.

The pinned Windows SDK 10.0.26100.0 packs and unpacks the full stage; independent
ZIP, path, manifest and byte verification checks both results. Install preflight
reconstructs the expected package from the current clean source, stage and startup
receipt, rejecting a coherently substituted package/record. The original unsigned
package remains unchanged; only an exclusively created temporary copy is signed.

Activation uses the Windows application broker with an empty argument string.
The returned PID must identify the exact installed EXE, retained process handle
and package full name before cleanup ownership starts. Every loaded module must
match the complete package inventory or originate beneath non-reparse Windows
paths. Independently verified, precisely located Microsoft Defender injection is
recorded separately. Actual loaded GTK, GLib, Cairo, Fontconfig and Poppler runtime
files are required. A visible owned root window and bounded screenshot are
required; GTK root-only accessibility is recorded as limited startup evidence.
A normal window close must lead to an observed zero exit. Cleanup removes only
registrations, certificates and temporary directories owned by this invocation;
primary, cleanup and evidence failures remain separate in the final report.

This does not exercise PDF import/export, templates or a physical pen tablet.
Those workflows, upgrade, WACK, production identity and complete corresponding
source/license obligations remain release gates.

## Local verification (2026-09-11)

- 20 Python package tests pass, including SDK pack/unpack fixtures, independent
  ZIP/installed inventory, semantic manifest mutations, coherent record changes,
  all-stage provenance/notice bindings, Windows path aliases and source artwork.
  The valid alternate artwork test first failed before the binding was added.
- Seven PowerShell suites pass: six orchestration scenarios; five final-report
  scenarios; ten actual registration-operation flows; retained-handle zero,
  nonzero and timeout observations plus owned-process cleanup; one real GTK root
  fixture and six negative cases; three positive and sixteen negative Defender
  signature/path fixtures; actual temporary-directory collision preservation.
- All nine helper/fixture PowerShell scripts parse. The fixtures compile the
  embedded native C# helper and execute real child-process observations locally.
- Tests run on macOS using PowerShell 7.6.6 do not establish Windows package,
  signature, broker, UI or module behavior. Fresh Windows qualification is required.

Adapted MIT qualification infrastructure retains its notices in
`PIPELINE-MIT.txt` and `RETICLEQUAY-MIT.txt`. The application and dependencies retain
their existing separate licenses and original notices.

## Independent review repairs

The reviewer reproduced acceptance of missing/false SDK-unpack metadata and an
empty cleanup-error list after successful Add with never-observed ownership.
Seven real-package mutations were RED before requiring the exact typed unpack
count derived from the source-bound payload. The actual Add/cleanup closure was
RED before reporting unresolved registration uncertainty without deleting a
registration whose ownership was never established. Both regressions now pass.

Before creating the stage receipt, `prepare_inventory.py` writes
`build-evidence/source-status.json` from Git's NUL-delimited porcelain status.
Any tracked or untracked source change still fails qualification. The bounded
record and exception retain exact status/path entries (plus the complete status
byte count and SHA-256), so the metadata-only artifact identifies build tooling
that writes outside ignored build directories. Dependency setup records now go
to ignored `build-evidence` paths rather than creating an untracked file under
`Release`.

### Consistent Windows checkout bytes

Windows run `34615260594` built and passed native tests, then rejected 1,183
modified tracked files. Checkout used Git for Windows 2.55.0.windows.5 while
native inventory used MSYS Git 2.55.0. A real-repository regression reproduces
the CRLF checkout mismatch under their differing `core.autocrlf` defaults.
The tracked attributes now require LF for detected text; binary files and raw
compiler/test logs retain their bytes. Git treats only the declared text EOL
representation as checkout metadata; other content changes are not ignored or reset.
The workflow records relevant Git configuration and requires a clean source
checkout before dependency inventory/configuration, as well as at staging.
The exact current Windows checkout and post-build cleanliness still require a
fresh native run; the local regression alone is not native qualification.

## Installed note/template/PDF consumer workflow

The installation qualifier now requires `qualify-workflow.ps1` after the genuine
startup observation and before normal close/uninstall. A new directory under its
already owned temporary tree contains an original generated one-page PDF and a
PDF-backed `.xopp` with text and a pen stroke. The driver opens that note, selects
Cornell in the real template dialog, saves a named preset, cancels the default,
reopens the library, applies its saved final entry, inserts a page, and saves a new
note. It exports through File → Export as PDF, observes/dismisses the result
dialog, reopens the actual PDF through File → Open, and exports again.

The installed GTK startup evidence exposes only its root through UIA. This driver
therefore uses public menu mnemonics, accelerators, GTK chooser location input and
normal Tab navigation, rather than private GTK actions or injected settings.
Every input requires the retained process handle, exact installed executable and
package identity, plus the exact native HWND/title/owner/foreground relationship.
Journal menu order and Cornell selector index come from the actual source
resources. The known `gdkWindowToplevel`/`gdkWindowTemp` classes are present in the
retained GTK 3.24.52 Win32 source. The template selector's mnemonic focuses the
first control; reverse Tab wraps to the last Ok button. That keyboard behavior,
focus delivery, GTK dialog ownership/titles and initial template selection still
require the first actual Windows workflow run; local helpers do not qualify them.
A missing/wrong window or ineffective keyboard sequence times out or produces
incorrect files and fails. Screenshots require the exact owned foreground HWND,
visible-desktop bounds and nonblank pixels. The checked-export message has no
explicit product GtkWindow title; its owned GTK result window is accepted only
after independent verification of the freshly emitted successful PDF report.
Screenshots of those dialogs remain available for human review.

`workflow_files.py` creates only original synthetic fixtures. It never calls an
InkQuay API or writes a template/settings file. Its independent oracle requires:

- Original source/background hashes unchanged; a saved two-page note containing
  the original annotation and PDF reference, and the Cornell second-page config
  and size.
- Exactly one fresh UUID application report per output, strict integer counts,
  published/pass status, exactly the existing structural-scope disclosure and no
  additional warnings/errors/recovery residue, exact output byte
  count/path and the complete expected protected-input hash set.
- Actual Poppler `pdfinfo`/`pdftotext`/`pdftoppm` checks of two pages, original
  source/note text, Cornell labels on page two and its rendered cue divider.
  Raster output is limited to 850 pixels on its larger dimension. These existing
  same-run MSYS2 checker executables are resolved beside the recorded Python,
  fingerprinted before/after use and recorded separately from the installed app.
- The saved note and first export unchanged after the second export. The original
  input manifest is also checked for mutation between steps.

The package source-input record binds the new observer/oracle and the actual menu,
dialog and preset resources. Existing runtime-module confinement is executed again
after the workflow, including any PDF/font modules loaded lazily. Installation
acceptance and `interactive_pdf_workflows_verified` become true only if the entire
workflow, normal exit, uninstall and existing cleanup/package checks pass. The
separate staged-startup receipt remains startup-only.

Only JSON and screenshots under `build-evidence/msix-install/workflow` are added
to the public metadata artifact. App-generated reports, including failed reports,
are retained without changing their bytes. Generated notes/PDFs remain in the
owned temporary tree and are removed by existing cleanup after stopping the owned
process. No app binaries, arbitrary profile files or private keys are uploaded.
Errors from workflow and report retention remain visible, and existing installation
cleanup retains its primary/cleanup-error separation.

Local checks (not Windows acceptance):

```sh
python script/msix/test_workflow_files.py -v
python script/msix/test_msix_qualification.py -v
pwsh -NoProfile -File script/msix/test_workflow_helpers.ps1
```

The eight new real-file/Poppler tests cover altered originals, invalid applied
ruling, failed/mistyped/misbound reports, changed count/text, absent divider,
duplicate reports, links and existing paths. The PowerShell test covers exact
window/owner/PID/handle selection, ambiguity and error surfaces. On Windows it
also opens an owned native fixture to test discovery/foreground and wrong-PID
rejection; on other hosts that native case is explicitly unexecuted. These fixtures
are not consumer-app interaction evidence. No physical tablet, handwriting
recognition, encrypted/large-document, broad accessibility or general visual
fidelity claim is added by this bounded generated-document workflow.
