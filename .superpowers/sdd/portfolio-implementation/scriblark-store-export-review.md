# Scriblark Store identity and unsigned retention

Candidate is based on `5f16f1893f1440fc15b7d5e4bfbb6052e863ded0`. It changes
qualification/export infrastructure only. Scriblark application code, version,
fonts, document/settings compatibility and the reviewed Pango repair are intact.
No push, Store submission, website or parent release-state change was made.

## Behavior

The builder and independent manifest/container/unpacked/installed validators now
accept exactly two named modes, preserving disposable qualification by default.
Store mode uses `1659hashfunction.InkQuay`, publisher
`CN=B6A2631A-FD32-45CC-AE12-82466975F528`, PublisherDisplayName `hashfunction`,
ApplicationId `InkQuay`, version `1.0.1.0` and `bin/Scriblark.exe`. The installer
independently validates every selected identity field, record mode and typed
boolean flags. It still refuses any existing same-name package and establishes
ownership only after successful Add and observation of the exact registration.
Both real installed flows run in separate PowerShell processes/temporary trees.
The existing normal close, exact module, owned registration/certificate/process
and temporary cleanup operations are unchanged.

`capture_crash_stack=true` remains diagnostic-only and stops after disposable
qualification. A normal run proceeds through disposable and Store qualifications
and can retain only `Scriblark_1.0.1.0_x64.msix` and `release-ready.json` after both
pass. The success-only artifact names those two files explicitly. All metadata is
retained separately. Temporary signed copies/private signing inputs cannot enter
the unsigned payload or artifact. Readiness does not claim Store submission,
certification, public release, dependency binary reproduction or blanket license
clearance.

## Independent checks

The exporter uses the existing exact payload rederivation against current clean
source, full native release, source originals, artwork, generated selected-mode
manifest, package inventory and startup receipt. It repeats this after publication
checks and compares all consumed evidence hashes before copying unsigned bytes.
It revalidates SDK MakeAppx/SignTool fingerprints, exact package metadata, current
source/run/attempt, and both independent installation receipts.

The new workflow parser requires standalone/embedded equality, every existing
acceptance and cleanup predicate, absence of observer/error/residual state,
complete input action/title/PID/HWND sequence, eight actual owned screenshots,
original PDF reports and their retained copies, protected input/output hash
continuity, saved-note continuity, independent Poppler tool hashes and actual
page/text/raster results, two complete loaded-module observations and both normal
exit records. It does not accept a supplied success boolean as a replacement for
those observations. The fixture producer now exposes its unchanged deterministic
input bytes for independent rederivation; the raster receipt includes observed
width/height so the exporter can apply the original divider threshold.

Receipt additions are run/attempt, helper hashes and selected-mode facts. Failure
to collect new helper metadata is secondary evidence failure and cannot erase
an earlier activation or cleanup error.

## Source closure

`Release/source-publication` retains 1,527,233 bytes of JSON copied byte-for-byte
from the original InkQuay and related PixelQuay publication evidence, including
65 original binary/archive/recipe/file proofs and the separately published current
winpthread supplement. Original historical names, source snapshots, collection
counts and clearance flags remain unchanged. No archive was downloaded again.

The current stage must match all 66 exact native owners/versions/archive hashes
and the corresponding owned-file hashes. The original indexes account for the
current 21 included source archives, 44 reused original related-source archives,
and one separate winpthread preferred-form source asset. All 359 resolved Cargo
archives/lock and all 735 original notice files are checked against original
collection membership. Current non-PE application resources remain accounted for
by exact current payload/source binding; they are not incorrectly treated as new
native owners.

Read-only replay of real run `34691122756` passed closure for all 3,361 actual
owned files. Anonymous GitHub release APIs also confirmed exact size/digest/URL
for the original 360,591,360-byte InkQuay collection, 524,318,720-byte related
PixelQuay collection, its 24,904-byte manifest and the current 54,173,752-byte
winpthread source asset. Proof: `/private/tmp/scriblark-source-assets-live.json`.
Local Python initially lacked its CA bundle; using the macOS system bundle
`SSL_CERT_FILE=/etc/ssl/cert.pem` enabled verified TLS. No verification bypass or
production TLS change was made. The exporter additionally requires the current
public application commit and complete Git tree to match the clean checkout.
That new candidate's public verification necessarily waits for root publication.

## Verification and native limit

- All **92** `script/msix/test_*.py` tests passed with Python 3.10.11 in
  98.177 seconds, including the actual Poppler fixture. Log:
  `/private/tmp/scriblark-store-final-python.log`.
- All **13** isolated PowerShell fixture scripts passed, followed by the ten
  actual registration ownership scenarios in Store mode. Both fixed identities,
  five sequencing cases, eight final-report/error cases, retained process,
  module, original diagnostic and cleanup fixtures were exercised. Log:
  `/private/tmp/scriblark-store-final-powershell.log`.
- Runtime used:
  `/Users/hashfunction/workspace/project_app_factory/microsoft-store/apps/filequay/source/.tools/powershell-7.6.6/pwsh`.
  This was read-only runtime reuse; FileQuay source was not edited.
- All MSIX PowerShell files parse; the seven new Python helper/test modules pass
  Black checking; `git diff --check` is clean. Unrelated existing function
  formatting was preserved to keep review focused.
- All **72** copied original publication JSON files still equal their retained
  source bytes. Actual 178-module startup evidence, original-input hashes and
  native RGBA PNG dimensions/colors from `34691122756` pass their applicable
  independent parsers; this is partial evidence replay, not a successful run.

Root's independent review and a fresh actual Windows dual-identity run remain
pending before publication/Store retention. No native execution is inferred from
portable fixtures.

Original missing-mode, missing-publication/export modules, orchestration entry
point and helper-evidence failure were reproduced before their fixes. Regressions
cover coherent package/record substitution, mode confusion, every identity field,
private signing material, current native archive/recipe/owner/file differences,
Cargo/notice membership, missing publication, changed public asset/current source
tree, partial or altered workflow, changed note/report/PNG/module/tool, observer
acceptance, residual state and failed normal exit. Existing actual registration
closures run in both modes, including failed Add races and preservation of foreign
registrations.

Real Windows run `34691122756` passed all 135 native tests and, uninstrumented,
inserted the saved Cornell template, saved the two-page note, exported/checked
`first.pdf` (24,219 bytes), dismissed its real report and reopened the PDF. It
then failed waiting for `Export File` after the second `%fe` mnemonic. PID 8244
remained alive with the exact visible/enabled `first.pdf - Scriblark` editor;
cleanup later terminated it (exit -1). There is no new application crash finding.
The full installed workflow, normal close and Store path remain unqualified.

Actual original input hashes, mixed native path serialization, first application
report and real PNGs were inspected/replayed. The compact retained partial-run
fixture explicitly says that the second export and installed qualification failed;
it cannot confer acceptance. This Store commit intentionally does not repair or
retry that unresolved input boundary. Root requested a separate bounded menu/input
observation candidate next, preserving one-shot inputs and all full-workflow gates.
