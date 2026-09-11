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
