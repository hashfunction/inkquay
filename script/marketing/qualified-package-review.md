# Exact Scriblark marketing input review

The capture binding selects the existing unsigned Store package from successful
Windows run **34710260935**, attempt **1**, public source
`21476437b6a187b3a8717d844fefe5f47815386c`. No application rebuild or new Windows
qualification was performed for this binding.

| Original input | Bytes | SHA256 |
| --- | ---: | --- |
| `Scriblark_1.0.1.0_x64.msix` | 92089651 | `72169ef657f1adc8c47be28760d503763e25017ef2b0f883dfeaf36b770e1deb` |
| `release-ready.json` | 71392 | `5e1e81a225fd345d85448636a9ac2b74f1fff091f694129c400ba3ac88326f4d` |

Original artifact IDs are **10303592946** (`Scriblark-Store-unsigned`) and
**10303203736** (`Scriblark-Windows-qualification`). GitHub run and artifact
metadata independently matched the repository, exact source, run, attempt,
successful conclusion and unexpired artifacts.

Unchanged helpers from the clean qualified public source passed against the
downloaded originals:

- `capture_checks.verify_inputs`: unsigned fixed Store identity, every one of
  4,637 payload members, readiness receipt, retained evidence hashes, exact
  original source helpers and both complete installed workflows.
- `store_workflow_evidence.validate_installation`: both complete original
  installed lifecycles, including 25 owned input events and eight workflow
  screenshots each, original startup screenshots, pre/post module inventories,
  saved-note continuity, two-page PDF content/ruling observations, protected
  inputs, checked export reports, normal exit code 0 and uninstall.
  Returned summaries exactly matched `release-ready.json`.
- `python3 script/marketing/test_capture_files.py -v`: all five tests passed.

To run the unchanged full receipt validator on the review host, the three PDF
checker executables were extracted from the exact recorded MSYS2 Poppler
26.08.0-1 package (archive SHA256
`24f5ae117d6e64351f476d52a01ce87c705662293dda38da572d01e58d09b3cc`).
Their original relative drive-spelled paths were materialized under a private
temporary review directory. The helper verified their exact bytes and hashes
against both original Windows receipts; no original path or receipt was edited,
no helper was replaced, and no Windows executable was run on the review host.
The original native PDF checks remain the Windows run's evidence.

The qualification and Store process IDs were 7596 and 6516 respectively. Both
lifecycles retained the immutable application ID `InkQuay`; the Store package is
`1659hashfunction.InkQuay_1.0.1.0_x64__r3hxytd7jt6c4`. The original readiness
receipt still makes no Store certification, submission, public release or
blanket license-clearance claim.

Marketing capture remains pending. Its separate workflow must capture the exact
bound package through the existing normal UI, retain raw screenshots and output
facts, then prove its own normal close, uninstall and owned cleanup. This review
does not certify future screenshots or substitute marketing for qualification.

## First marketing activation correction

Marketing run 34721890864 (capture source
`663c9f9b02316d37ff3059add4830ba249b4c7ba`) stopped before process activation:
the capture caller passed one argument to the qualified helper's only public
`ActivationBroker.Activate(string appUserModelId, string arguments)` overload.
The native qualification caller already supplies both arguments. The capture
caller now also supplies `$null` for ordinary startup without arguments.

Original artifact 10306049515 retains `capture-result.json`, 5,128 bytes,
SHA256 `f687172ed7c4847f0c6f6d8deb6f76ad68f470f5cd23d123691bac6e2bcdbaee`.
Its inputs/screenshots are empty and captured=false. It records unchanged
original package bytes, no residual package, restored display, and correctly
refused demo/profile cleanup because process ownership was never established.
This failure does not invalidate or rerun either qualified package lifecycle.

The extended existing `test_capture_operations.ps1` compiles the unchanged
qualified broker to inspect its real signature, then executes the actual
capture Activate closure with only the COM leaf substituted. It reproduced
the argument-binding failure before the one-line correction. Afterward one
attempt reaches the exact AUMID with no startup arguments; the intentional
leaf failure cannot fabricate a PID, retained process or process ownership.
All original lifecycle/failure cleanup cases pass. The test's qualified helper
bytes also matched the successful Store installation receipt. Fresh Windows
marketing capture remains pending; no package/source binding or acceptance
gate changed.
