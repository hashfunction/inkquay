# InkQuay private debugger import-reader repair

Base source `82447b94e268091f2a9e36d7f10ce98806dbb54c`; public source
`a8cb9af98128af6ef8fcaef83a8e0975a2df893f`; diagnostic run `34681150165`.
This source-only diagnostic candidate changes neither the product nor consumer
acceptance. Native observer qualification and an actual application crash stack
remain pending.

## Actual failed boundary

Artifacts: `/private/tmp/inkquay-34681150165-review/InkQuay-Windows-qualification`.
`build-evidence/crash-observer-tool.json` has `built=false`, `tool=null` and
`error="Diagnostic PE imports exceed bound"`. Configure/make finished through
`CXXLD gdb.exe`; the recorded interval was 07:38:40–07:51:33 UTC. The finishing
validator passed build exit, unchanged inputs, exact patched source and native
payload selection, then failed inside `runtime_files()`.

That function used `objdump -p`, then rejected its **entire** stdout above 1 MiB
before extracting DLL names. GNU documents `-p` as format-specific private-header
information, not an import-only output. The pinned GNU PE backend also prints
exception/unwind, export and relocation data. The old receipt does not identify
which recursive PE produced the output or its exact stdout/file size; attributing
it specifically to GDB's unwind table would exceed the retained evidence.

The preflight receipt has `passed=false`, `cases=[]`, `results=[]`, and the
secondary build/receipt rejection. The installer explicitly records that live
fixtures did not pass and attachment was forbidden. The workflow diagnostic
flag records the requested mode; it does not establish an attached observer.
The uninstrumented owned process again became unavailable. There is no captured
Save/page-insertion stack and no basis for a product crash repair.

Receipt SHA-256:

- Tool: `b8a7faf50afaaa4a9534740133db8a9254c359453bc7d9f2f10019318c8f53bb`.
- Preflight: `b44d4b59b34a6d42550da78746976d54ff6e667b451d6f3c89901c317090edd5`.

## Bounded replacement

`pe_import_names()` reads the existing owned regular file through one retained
handle. It requires native AMD64/PE32+, bounded COFF/optional headers and at most
96 sections. It resolves import and delay-import descriptors through unambiguous,
file-backed RVAs, requires null termination and safe ASCII DLL basenames, and
rejects unsupported delay-pointer encoding/reserved flags. All table, RVA and
file bounds are checked before reading. It reads at most 64 KiB per file,
permits at most 64 DLL descriptors and 255 bytes per name, and retains the 1 MiB
bound specifically on declared import-directory size. It does not read unrelated
private-table contents or launch objdump. A changed file during parsing fails.

Both standard and delayed imports feed the same recursive resolver. Exact
MinGW-prefix DLL hashes, API-set/System32 exceptions, missing-DLL rejection,
nonempty recorded runtime closure and the 64-module traversal bound are retained.
No new runtime dependency or import-name allowlist is introduced. Malformed PE
errors identify the exact source path and actual file byte size, plus bounded
field/range details; no huge header dump is retained.

The reviewed GNU 17.2 archive/patch hashes, native build flags, tool selection,
input/tool/runtime receipt binding, source/run/attempt checks and private-binary
non-distribution remain unchanged. All four live Windows cases remain mandatory:
signal pass with the original leaf stack, normal detach, abrupt-debugger-exit
survival and timeout detach. Observer input/permissions/bounds and installed
process, module, user-input, workflow, normal-close and cleanup gates are unchanged.

Primary specifications: [Microsoft PE format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)
and [GNU objdump options](https://sourceware.org/binutils/docs/binutils/objdump.html).

## Verification

The new recursive PE-byte regression first reproduced the exact old 1 MiB
exception with a small dependency graph and large unrelated private-output
fixture. It now passes using actual normal/delay descriptor bytes without calling
objdump. Tests include cycles, unresolved DLLs, malformed/truncated headers,
unsafe/non-ASCII/unterminated names, invalid counts/sizes, overlapping or
virtual-only RVA mappings, absent terminators, 65 descriptors, read-budget and
unrelated-section exclusion, redirected files, actual mid-read file changes,
exact failed-receipt path/size retention, and existing source/hash/tool mutations.

- Focused production build/parser boundary: 14 tests pass.
- Full Python regression result: 67 tests pass.
- All 11 PowerShell fixtures pass under separate `pwsh -NoProfile -File` processes.
  An initial single-process invocation leaked fixture function scope and failed;
  the documented standalone invocation passed with no PowerShell source change.
- `git diff --check` passes. Byte comparison confirms unchanged GDB patch/build
  flags, actual observer, all live fixture cases and installed consumer scripts.

Logs: `/private/tmp/ink-observer-imports-red.log`,
`/private/tmp/ink-observer-imports-green.log`,
`/private/tmp/ink-observer-imports-final-python.log`, and
`/private/tmp/ink-observer-imports-all-powershell-isolated.log`.
PowerShell: sibling FileQuay source `.tools/powershell-7.6.6/pwsh`.

A fresh explicit `capture_crash_stack=true` Windows run must still validate the
actual privately built debugger and runtime graph, pass every live survival case,
then capture the owned installed failure. No native attachment, stack, product
crash fix, renamed branding, public push, site or Store change is claimed here.
