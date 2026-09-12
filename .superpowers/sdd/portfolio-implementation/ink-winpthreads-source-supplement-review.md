# InkQuay current winpthreads source supplement

## Observed failure and exact boundary

Native run `34685959483`, public source
`53deb7c21f219c2f5479b9d3942a820671082653`, nested source
`368fad7479e3438ac75b322cb6a8ddb521eaaa10`, failed in
`prepare_inventory.py` → `create_input_inventory` with
`Native owner/version has no matching retained source: mingw-w64-x86_64-libwinpthread`.
The inventory contains version `14.0.0.r375.g9c1abbbf5-1`; the source index still
bound `14.0.0.r353.g6df76fa52-2`. This was the sole changed used runtime owner.
The strict source gate correctly stopped before installed qualification. This
run provides no new crash-observer attach result or application crash stack.

The original metadata is retained at
`/private/tmp/inkquay-34685959483-review/InkQuay-Windows-qualification/build-evidence`.
Its native inventory is 1,818,168 bytes, SHA-256
`b02e76cfa56ea0d459fb1d179494de8c3f9ff71101a2b3794033b048d85c6837`;
its cache-hash receipt is 40,608 bytes, SHA-256
`331ee97492e1fe4783fdc816adecb1da76cce30a046af11158943b7cbd83993f`.

## Independently checked binary and matching source

Downloaded only the 30,551-byte exact MINGW64 binary archive from
[the MSYS2 mirror](https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-libwinpthread-14.0.0.r375.g9c1abbbf5-1-any.pkg.tar.zst).
Its SHA-256 `1d0ed7fda332a5c879de210f3d72c75fa1f3df7cc63dd951e763dec8eb02c1ee`
exactly matches the failed runner's cache receipt. The package metadata identifies
`mingw-w64-x86_64-libwinpthread`, base `mingw-w64-winpthreads`, the exact version,
and license declaration `spdx:MIT AND BSD-3-Clause-Clear`.

The extracted `mingw64/bin/libwinpthread-1.dll` is 63,840 bytes, SHA-256
`2da71960a872bd1e59b60377f798f285ce630106509d6bd1d75e553f16218b7b`,
identical to the actual staged DLL. Extracted `.BUILDINFO` identifies recipe
SHA-256 `7e5cec4463bd044cddeeb584dc6aab3e91dee5afd088d382e90c6232d0dd4e17`.
Both metadata file hashes are retained in the index. No new signature-verification
claim is made; this independent archive comparison binds to the runner's recorded
package cache and metadata.

Reused the already-retained preferred-form source archive at
`/private/tmp/tintfable-native-source-supplements/`, without downloading another
54 MB copy. It is 54,173,752 bytes, SHA-256
`7bf513784ae0bc4f1a413e1f787f7a3ba2bd7ec0503980ea4d17ddf0e4796c87`.
Rehashed the archive and extracted its actual PKGBUILD, .SRCINFO and patch.
The 4,484-byte PKGBUILD hash exactly matches the MINGW64 binary's .BUILDINFO,
explicitly supports `mingw64`, and selects source commit
`9c1abbbf55a3de2febee4d1f685b1bda20774c5e`. Its 1,789-byte patch matches its declared
SHA-256. .SRCINFO was generated for UCRT64, so it is not substituted for the actual
MINGW64 binary metadata. TintFable's CLANG64 binary hash is also not reused.

The prior retained source proof records exact Git commit resolution and two
matching 140,011,520-byte deterministic exports at SHA-256
`eca113e8ecc9e907065b285036ebfcb09d97084f457098d198149cb43e393066`.
That proof was inspected and hash-bound here; its Git export was not repeated.
The coordinator's prior anonymous publication receipt verifies the
[separate direct source asset](https://github.com/hashfunction/pixelquay/releases/download/native-sources-2026-09-12-tintfable/mingw-w64-winpthreads-14.0.0.r375.g9c1abbbf5-1.src.tar.zst)
at `2026-09-12T09:58:13.503403+00:00`. Its exact proof file is hash-bound in the
index; no new anonymous full-source download was performed for this repair.

The binary archive's original COPYING is 2,883 bytes, SHA-256
`63263614cdd29f2f93cba85e992f041b31f9fc7b4033692f31269489a8a1b177`.
This matches both actual copied `msys2/libwinpthread/COPYING` and
`msys2/winpthreads/COPYING`, and the prior source proof's original notice. Byte
equality of the companion copied path does not establish its package owner.

## Bounded change and preserved provenance

Updated only the current libwinpthread owner and its corresponding source row in
`Release/notice-supplement/SOURCE-INPUTS.json`. Delivery is explicitly
`published_source_asset`, with its direct URL and inherited verification time.
The obsolete source-metadata path and collection-member delivery were removed
from that row. Inline supplement evidence records the binary/source relationship
and the superseded archive; it does not rewrite the original collection.

All other 65 owner and source rows, the collection descriptor, Cargo inputs,
Rust input and source route are unchanged. The original `NOTICE-INDEX.json`
remains SHA-256
`9af8ba17ebda43c78a27d3c80ac302b3b238b67448f973d244c8ec23048a18f9`, and all
735 indexed original files retain their exact bytes. The package still copies
738 supplement files. README and third-party notice explain the separate source
asset; `PACKAGED-NOTICES.md` records the current index hash and labels its earlier
packaging proof as historical.

No production Python/PowerShell, dependency installation, application code,
workflow, identity, observer, acceptance, input or lifecycle logic changed.
Existing copied-notice and source-input hashes bind the updated metadata to the
current package. Existing exact owner/version matching still fails closed on any
unretained version. Public-release and license-clearance flags remain false.

## Verification

- RED: the new production package-boundary fixture rejected the observed current
  owner and still accepted the superseded version; the exact source metadata
  regression also failed on the old row.
- GREEN: the same fixture accepts the exact new owner, carries the current index
  through actual package staging, preserves false release/clearance claims, and
  rejects both the superseded version and an unretained version. File contents
  in this local package fixture are explicitly synthetic, not native execution.
- Exact source regression checks the MINGW64 binary hash, recipe/source hashes,
  direct delivery shape, actual DLL/notice observations, unchanged collection
  baseline and explicit superseded archive.
- Replayed the failed run's actual 66 used owner/version pairs against the updated
  mapping: all 66 match. Direct structured comparison to HEAD confirms only one
  owner and one source row changed, with other top-level records unchanged.
- **69 MSIX/Python tests passed**, including original notice corruption/omission
  rejection after coherent stage rehash, source status and GDB observer helpers.
  **Nine native inventory tests passed.**
- **All 11 isolated PowerShell fixtures passed**, including the corrected Libtool
  observer's 22 ownership/path/hash/process-lifetime checks, retained process
  observation, package/source evidence, module collection and workflow cleanup.
- `git diff --check` passed. No large native build or additional source archive
  download was needed.

Logs and the small independent binary/metadata proof are under
`/private/tmp/inkquay-winpthreads-34685959483/`.

Fresh exact-source Windows qualification is still required, with explicit
`capture_crash_stack=true` for the diagnostic observer. The corrected Libtool
observer from `368fad7479e3438ac75b322cb6a8ddb521eaaa10` remains untouched.
No runtime crash repair is inferred from this prerequisite change, and no push,
dispatch, website, Store or parent-status edit was performed.

Commands from the nested source root:

```sh
python3 -m unittest discover -s script/msix -p 'test_*.py' -v
python3 script/test_inventoryWindows.py
```

Each of the 11 production-listed `script/msix/test_*.ps1` fixtures ran in a fresh
`-NoLogo -NoProfile -File` process using
`/Users/hashfunction/workspace/project_app_factory/microsoft-store/apps/filequay/source/.tools/powershell-7.6.6/pwsh`.
The local fixture suite is not the four real Windows debugger-survival preflight
cases and does not replace their next native execution.
