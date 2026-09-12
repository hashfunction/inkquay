# Scriblark Store export implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Root coordinates independent review; no subagents or pushes.

**Goal:** Retain the exact unsigned Scriblark Store MSIX only after both actual installed workflows and complete current source/package evidence pass.

**Architecture:** Extend existing packaging/installation functions with two fixed identity modes, preserving the disposable default. Reuse their exact payload rederivation in a separate exporter; independently check recorded consumer, process, module and public-source facts. Diagnostic observer runs remain incapable of consumer acceptance or Store export.

**Tech stack:** Python standard library, PowerShell 7, Windows SDK 10.0.26100.0, existing MSYS2/native workflow.

**Spec:** Root's approved bounded Store/export task in the current conversation, following Cliptern, DupliSift, TintFable and Jotmorrow implementations.

## Constraints

- Store identity `1659hashfunction.InkQuay`, publisher `CN=B6A2631A-FD32-45CC-AE12-82466975F528`, PublisherDisplayName `hashfunction`, ApplicationId `InkQuay`, version `1.0.1.0`, executable `bin/Scriblark.exe`.
- Keep Scriblark branding, application code, data paths, current Pango repair, original source evidence and all existing input/ownership/lifecycle checks unchanged.
- Both normal installed qualifications run in separate processes with separate temporary/output trees.
- No arbitrary identity, signed/private-key upload, diagnostic-only acceptance or historical receipt rewrite.
- Retain exactly `Scriblark_1.0.1.0_x64.msix` and `release-ready.json`; submitted/public-release/certification flags stay false.
- Native Windows execution and independent review remain required; this task commits locally only. TintFable's final capture binding has priority when its successful artifact becomes available.

## Task 1: Fixed Store identity through existing validators

Files: `script/msix/msix_qualification.py`, `verify_record.py`, `qualify-msix-install.ps1`, `test_store_identity.py`, `test_store_identity.ps1`, existing registration fixture.

Interfaces: `identity_for_mode(mode='qualification')`, `package_name(mode='qualification')`; optional trailing `mode='qualification'` on manifest/stage/container/unpacked/installed/record functions. Build uses keyword mode after existing runner argument. PowerShell exposes `Get-InkQuayIdentity`, independent `Assert-InkQuayRecordIdentity`, and validated `IdentityMode` parameter.

- [x] Add tests before implementation. Positive Store manifest must equal `STORE_IDENTITY`; default must equal original qualification identity. Test mode confusion through actual ZIP, unpacked and installed files; mutate publisher, executable, AppId, version, metadata flags and private signing files.
- [x] Run `python3 -m unittest discover -s script/msix -p test_store_identity.py -v` and observe the missing Store mode failure.
- [x] Thread the fixed mode through existing generation and independent verification; preserve default behavior and false release/license claims.
- [x] Execute real PowerShell identity assertions and registration ownership closures in both modes, including failed Add and foreign registration preservation.

```python
assert msix.validate_manifest(msix.create_manifest('store'), 'store') == msix.STORE_IDENTITY
with self.assertRaises(ValueError):
    msix.validate_manifest(msix.create_manifest('store'), 'qualification')
```

## Task 2: Exact source delivery and independent installed evidence

Files: new `script/msix/source_publication.py`, `store_workflow_evidence.py`, their tests/fixtures and `Release/source-publication/`; minimal context/hash recording in existing installer/workflow receipt constructors.

Interfaces: `validate_native_sources(source, evidence, record)` reconciles actual owner versions/archive hashes with the existing source index; `verify_public_sources(source, evidence, record, commit)` checks retained publication facts against anonymous current endpoints. `validate_installation(folder, record, source, context, mode)` consumes exact standalone/embedded window, workflow, reports, tool/module and exit records.

- [x] Copy retained original source-manifest/delivery-index/public-verification and original related Tint source-delivery metadata byte-for-byte into a separate publication directory; preserve all existing indexes and original notices.
- [x] Add negative tests for owner/archive/source-member/crate/notice mismatch, absent publication, altered public manifests/assets and changed current public source tree.
- [x] Implement exact 66-owner source reconciliation, including original collection membership versus the separate current winpthread supplement; compare all 359 Cargo archives/lock and 735 indexed original files without claiming all crates are runtime-linked.
- [x] Bind source/run/attempt and actual helper hashes in new receipts. Validate complete actual template/save/export/reopen sequence, saved-note continuity, both original application reports, independent Poppler checks, screenshot hashes, both module observations and zero normal exit/cleanup.
- [x] Keep full standalone/embedded equality. Reject observer-requested/attached or incomplete receipt states even if a success boolean is supplied.

```python
for mode in ('qualification', 'store'):
    validate_installation(folder[mode], record[mode], source, context, mode)
with self.assertRaises(ValueError):
    validate_installation(mutated_observer_folder, record['store'], source, context, 'store')
```

## Task 3: Dual orchestration and exact unsigned retention

Files: new `script/msix/store_export.py`, `test_store_export.py`, `test_store_orchestration.ps1`; existing `qualify-msix.ps1`, `.github/workflows/windows.yml`, MSIX README and review report.

- [x] Add real-file/ZIP/Git export fixtures with positive exact two-file retention and negative partial workflow, wrong mode/source/run/attempt, changed payload/report/module, missing source delivery, private signing material, existing output and evidence mutation cases.
- [x] Reuse `verify_record_inputs` for each identity against current `build/dist`, artwork, inventory and startup. Require identical release payload inputs between identities and exact installed unsigned hashes.
- [x] Perform publication checks, recheck all consumed bytes and source cleanliness, copy only the exact unsigned Store package and write a separate readiness receipt. Failures cannot retain a ready receipt.
- [x] Run qualification mode then Store mode in separate PowerShell processes. A diagnostic request follows only the existing diagnostic qualification branch and skips Store export.
- [x] Add success-only exact two-file artifact upload; expand metadata-only retention to both installed evidence trees.
- [x] Run all `script/msix/test_*.py`, isolated PowerShell fixtures and both registration modes; run `git diff --check`. Inspect full production diff, record test counts/Windows limits, commit source and deliver exact SHA to root.

```powershell
Invoke-Checked $powerShell $qualificationArguments
if (-not $CaptureCrashStack) {
    Invoke-Checked $powerShell $storeArguments
    Invoke-Checked $python $exportArguments
}
```

## Execution result

Implemented locally; see `.superpowers/sdd/portfolio-implementation/scriblark-store-export-review.md`
for all 92 Python tests, 13 PowerShell suites, actual partial evidence replay and
source publication checks. The exporter uses real package/ZIP boundary fixtures,
complete constructed workflow receipts, retained actual partial Windows metadata,
and real Git commit/tree comparisons as separate focused tests; no combined
successful native fixture was invented. Root independently reviews the local
commit. Actual full Windows dual qualification remains pending, with the existing
second-export mnemonic observation tracked separately.
