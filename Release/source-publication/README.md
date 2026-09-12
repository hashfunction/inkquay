# Retained source publication evidence

These JSON files are exact copies of already published and independently downloaded
source evidence. They preserve historical product names, snapshots, license scope
and clearance flags. They do not describe a newly executed application build.

- `source-manifest.json`, `delivery-files.json`, `public-delivery-verification.json`
  and 65 `binary-metadata/*/evidence.json` records originate from the InkQuay
  `native-sources-2026-09-11-7c8469` collection. The original 360,591,360-byte tar
  has SHA-256 `9d4f550e4c4660036ae9cbb8816b4365cf792a1dfd6c370c8181c92610632625`.
  Its 1,711 members were anonymously downloaded and verified. The binary records
  map actual shipped file hashes to exact package archives and PKGBUILD hashes.
- `tint-source-manifest.json` and `tint-native-source-delivery.json` retain the
  related PixelQuay `native-sources-2026-09-11-c9f4add` source collection, from
  which 44 current InkQuay native source archives are reused. Original counts
  and historical product statements remain unchanged.
- `tint-source-supplements.json` and
  `tint-native-source-supplement-publication.json` preserve the separately
  published current winpthread preferred-form source and anonymous verification.
  This archive was not part of either original collection. Its exact MINGW64
  runtime/recipe binding is in `Release/notice-supplement/SOURCE-INPUTS.json`.

The exporter verifies the current owned native bytes, archive hashes and versions
against these proofs; current source/member/notice mappings against the original
indexes; and anonymous public release asset hashes, sizes and locations. It also
verifies that the current application commit and complete tree are public. The
original archives need not be downloaded again by every Windows qualification.

Complete current application source, build instructions, source delivery and
original notices are linked from https://scriblark.trieflow.com/source. Dependency
binary reproduction and blanket legal clearance are not claimed by these scripts.
