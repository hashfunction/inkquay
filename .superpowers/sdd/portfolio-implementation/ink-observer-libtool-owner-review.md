# InkQuay observer process ownership — run 34683727152

Base source `d988be375756cfeef0a593eb7be28ecfb47ce700`, public source
`4a379aa9083986e6b94de83bdd443defd35576ad`. This candidate changes only the
PowerShell diagnostic observer's native debugger path resolution and its focused
fixture. It does not fix or infer the original product crash.

## Evidence inspected first

Run 34683727152 completed private GDB preparation, native application compilation
and tests. All four live Windows observer gates passed:

| Case | Actual result |
| --- | --- |
| signal-pass | Exact `observer_fault_leaf` SIGSEGV stack captured; target exits 1 as required |
| normal-detach | Explicit detach; target survives and exits 0 |
| abrupt-debugger-exit | Debugger exits 1; attached target survives and exits 0 |
| timeout-detach | Explicit bounded detach; target survives and exits 0 |

The installed app was exact owned PID 5684, package
`Trieflow.InkQuay.Qualification_1.0.0.0_x64__fjvr7t994vwc4`, executable SHA256
`354b4ce2d350bdab019c7c0ffc9dd806ec0d29ce0973c3f3b6c4a9332e2dc790`.
The observer attached at 09:18:17.677 UTC and resumed at 09:18:17.813. Its ready
record identified debugger PID 3696, created at the recorded FILETIME, and the
same nonce/owned target as the installer. PowerShell then recorded
`Start: Debugger differs from current live fixture.` and requested the normal
stop path. GDB detached at 09:18:18.115, before the workflow began at
09:18:19.193. The observer result has `faults=[]`, `diagnostic_errors=[]`, debugger
exit 0 and no fallback termination. There is no product crash stack in this run.

The build record and live preflight bind the real native debugger to
`build-observer-gdb/build/gdb/.libs/gdb.exe`, 12,183,615 bytes, SHA256
`82b5b10c6065e677aea24a836d7cae1785989550a6b0da5dc9ac105814203927`.
The PowerShell readiness check still expected `build/gdb/gdb.exe`, the Libtool
launcher. Python's builder, preflight and observer already correctly resolve
only `.libs/gdb.exe` or `.libs/lt-gdb.exe`. This stale independent path expectation
fully explains the observed post-readiness rejection and early detach.

Later, after `insert-template-page` and `save-new-note`, the workflow waited for
an exact owned `Save File` window and found none. The retained app was still
alive at failure; its main window remained `*source.xopp - InkQuay`. The genuine
816x639 failure screenshot was viewed and shows that window without a save
picker. Its exit was subsequently -1 from owned cleanup, not a captured normal
close or the previously observed access violation. This different failure does
not establish the original crash's cause or that it has been fixed.

Original evidence under
`/private/tmp/inkquay-34683727152-review/InkQuay-Windows-qualification/build-evidence`:

- `crash-observer-preflight.json`: `5d14fc68de9d81df562b162a17094fa3006b5621305a5655cad5a3dbfeb3da0f`
- `crash-observer-tool.json`: `4ba02111525762e68d370ddec3dab2b284e4353c78306ee407930bc8697f9743`
- `msix-install/crash-observer.json`: `4691ca0c20bc5207296f03ba0ffffb485cd3a4d37a1e6718246b4590da0f882b`
- `msix-install/installation-qualification.json`: `c65eaeeb958bbb36a8ff824273e5d1d15638d54d25f9d265410d34f367a47d0b`
- `msix-install/workflow/workflow-result.json`: `cbbd73060d0f761e3cc5e3380334c75f84b02a7f2eed758d7b8e2209ce7bd850`

## Narrow correction and preserved gates

PowerShell now resolves exactly one regular, non-reparse native output from the
same two fixed Libtool paths allowed by `observer_gdb_build.py`. It never selects
the launcher, an arbitrary preflight path or a second ambiguous native output.
The selected canonical path and its hash must still equal the exact current live
fixture fingerprint. The existing real retained debugger process checks remain:
live state, actual MainModule path, exact readiness start FILETIME, and creation
no earlier than its owned observer helper. The Python observer still independently
verifies source/run/attempt, all four live results, exact build record/tool/helper
and dependency hashes, DWARF, target PID/start/executable/package identity and
nonce before its ready record.

No native GDB source/patch/build inputs, survival test cases, package/runtime
bytes, application code, keyboard input, consumer assertions, module checks,
normal-close/uninstall requirements, diagnostic flags or bounded cleanup were
changed. The default remains off; explicit diagnostic observation cannot produce
consumer acceptance. Existing secondary diagnostic error retention and detach/
fallback logic remain unchanged.

## Regression and validation

The existing PowerShell fixture now extracts and executes the actual
post-readiness ownership block from Start-InkCrashObserver. Only the debugger
Process property adapter is synthetic; actual file reads, hashes, path resolution
and reparse checks execute production code. The initial test fails on the first
valid `.libs/gdb.exe` fixture with the exact observed `Debugger differs from
current live fixture.` error. After repair, both supported native names pass
with a launcher sibling present. Twenty negative cases reject a launcher,
foreign path, hash mismatch, missing/ambiguous payload, reparse ancestor, wrong
actual process module path, wrong start time, exited debugger and process older
than its helper. Existing real helper-process exit/error/cleanup fixtures remain.

Final verification: all 67 Python MSIX tests pass, and all 11 isolated PowerShell
fixtures pass. The observer fixture includes the 22 new actual ownership-block
checks, alongside existing default-off, unowned-target, bounded-error, nonce/
target/type, real helper-exit and cleanup-failure checks. `git diff --check`
passes. Python GDB/build/survival implementation and the complete consumer
workflow implementation are unchanged.

Commands from the nested source root: `python3 -m unittest discover -s
script/msix -p 'test_*.py' -v`; each `script/msix/test_*.ps1` runs separately with
`/Users/hashfunction/workspace/project_app_factory/microsoft-store/apps/filequay/source/.tools/powershell-7.6.6/pwsh -NoProfile -File <fixture>`.
These local checks do not rerun Windows attachment; the original four successful
live cases are the native evidence above. Local logs:
`/private/tmp/ink-libtool-owner-red.log`, `/private/tmp/ink-libtool-owner-green.log`,
`/private/tmp/ink-libtool-owner-python.log` and
`/private/tmp/ink-libtool-owner-powershell.log`.

## Pending

Independent source review and a fresh explicit `capture_crash_stack=true` Windows
run are required. Read the next actual observer lifecycle and fault records,
not just tool/preflight success, before diagnosing the product. Neither this
candidate nor the failed receipt establishes full UI workflow, normal shutdown,
uninstall qualification or public release. No push, Store, site, parent status,
branding or product runtime change was performed.
