# Packaged original notice supplement

This bounded packaging change retains the prepared original native/Cargo/Rust
notices in the application source and copies them through the existing Windows
`package.sh` path. It changes no application behavior, native dependency version,
build option, package identity, website or submission status.

The input is the frozen source collection manifest SHA-256
`4e6aa5ecac3e97a52c50e620957df32fa757aa718a0f4894bec36376728bfee5`, prepared against
successful native run `34641324772`. That descriptor remains unchanged. Its
application snapshot is explicitly identified as the collection baseline, not
misrepresented as the newly built package's application commit. The ordinary
MSIX source-input record binds the current source, copy helper and every notice.

## Exact contents

`Release/notice-supplement/originals/` contains **735 exact original files**,
**3,656,502 bytes**: 46 native notice/data files, 643 Cargo notices, 42 original
Cargo attribution/manifest/source files, one pinned upstream license and three
Rust 1.98.1 texts. Every byte was compared with the frozen collection. Full paths
are preserved; empty DjVuLibre AUTHORS is retained intentionally. Existing
application and package-provided MSYS2 notices are not replaced.

Three additional files provide the complete map and useful source guidance:

- `NOTICE-INDEX.json`: 389,522 bytes, SHA-256
  `9af8ba17ebda43c78a27d3c80ac302b3b238b67448f973d244c8ec23048a18f9`.
- `SOURCE-INPUTS.json`: 224,435 bytes, SHA-256
  `8a047903f9b6bffd8c557e33c76c222efdd4833b17d8b024e526ed573ff2d074`.
  It identifies 66 native owners/source archives and 359 locked Cargo inputs,
  exact hashes, original source URLs and the source-collection reference.
- `README.txt`: source/build/relink/repackage guidance at
  <https://inkquay.trieflow.com/source>. Publication of the matching collection
  and this source route remains the coordinator's distribution action.

All **738** files are copied to `share/inkquay/licenses/supplement/` before the
native stage inventory. The helper requires a complete unique safe-path index,
exact original size/hash equality and a fresh destination. It rejects linked or
changed sources and preserves an existing destination. After copying it verifies
the complete destination against the measured source files. MSIX preparation
independently requires the same original files and metadata bytes even if stage
inventory hashes were refreshed. Actual native owner versions must match the
retained source index, preventing a later dependency change from silently carrying
stale source guidance. All 66 current prepared versions match the retained
successful native inventory; no dependency update is made by this patch.

## Verification

- RED: the real package fixture omitted native/Cargo/Rust notices/source index;
  Git's previous text policy rewrote original CRLF notice bytes. Both regressions
  passed after the packaging and `-text` changes.
- RED: a coherently recorded unretained native package version was accepted;
  the source-index binding now rejects it.
- **33 MSIX/source-status tests passed**, including actual shell invocation of
  the package copy command, complete copy, omission/corruption after native
  rehashing, missing/duplicate/traversal/hash index failures, changed/missing/
  linked source preservation, prior-destination preservation, and original
  empty-file handling. **Nine native inventory tests passed.**
- A separate actual Git repository/clone with `core.autocrlf=true` materialized
  all 735 retained originals with their exact hashes, including the one actual
  CRLF original. Git status remained clean under both true and false autocrlf.
  The source attributes use `-text` for originals, preserving their raw bytes.
- Shell syntax and `git diff --check` passed. No Windows application build,
  new installed-package test or publication was performed locally for this patch.

The coordinator reviews this source change, publishes the matching source
collection/route and dispatches native qualification of this exact revision.
