# Ink diagnostic executable selection after run 34676428304

Base source: `81090d951ac74aa73e407e985325a33ac5a866eb`.
Actual public run source: `6dba09184c5ada8e317de511993f0a956c60c429`.
This candidate changes private diagnostic-tool selection and diagnostic reporting.
It changes no product code, branding, corrected GDB source patch, observer attach
permissions, native UI actions, consumer acceptance or ownership/cleanup gates.

## Actual result: no application stack yet

The private GDB compilation reached its final link. Its receipt recorded a
53,248-byte `build/gdb/gdb.exe`, SHA256
`9138a8f5da40515950c337b24bababe469b5fe7337589a6730e313f1c47b8162`,
with an empty runtime DLL map. At 06:21:27 UTC, `verified_debugger()` refused it
with `Diagnostic runtime binding is absent`. This occurred before any of the
four live GDB survival cases. `crash-observer-preflight.json` was absent because
that setup call was outside the live fixture's failure-record try block.

The actual installed observer therefore never attached. The installation receipt
has `diagnostic_observer_attached=false`, and its secondary error is the missing
preflight path. PID 6628 subsequently exited 1 (`0x00000001`) immediately after
`insert-template-page`; the failing operation was observing
`*source.xopp - InkQuay`. There were no matched Application Error events and no
native stack. The primary `Retained owned process is unavailable` and empty
cleanup/evidence error lists remain intact. The page-insertion product cause is
unknown; this candidate does not infer a SIGSEGV site or alter the product.

The retained metadata is
`/private/tmp/inkquay-34676428304-review/InkQuay-Windows-qualification/build-evidence`;
the failed log is `/private/tmp/inkquay-34676428304-failed.log`.
No additional artifact or binary was downloaded.

## Proven diagnostic boundary and repair

The already-local GNU 17.2 archive was rechecked against its exact pinned size
24,658,624 and SHA256
`1c036c0d72e4b3d1fb5c94c88632add6f9d76f4d7c4d2ea793c12a9f19a3228c`.
Its `gdb/Makefile.in` links with Libtool. Its bundled `ltmain.sh` emits a small
Windows launcher and places the actual program under `.libs`, with `gdb.exe` or
`lt-gdb.exe` depending on its fast-install mode. The selected path and small,
OS-only PE import closure explain the observed empty runtime map. The
[GNU Libtool wrapper-executable documentation](https://www.gnu.org/s/libtool/manual/html_node/Wrapper-executables.html)
confirms that layout and that the wrapper launches a separate program.
Retaining that launcher would not retain the actual debugger process.

`resolve_tool()` now accepts exactly one of those two fixed `.libs` paths and
never falls back to the launcher. Missing/ambiguous outputs, links/reparse points,
non-PE, non-AMD64, PE32 and DLL inputs fail before selection. The receipt binds
the selected relative path as well as its exact bytes. The existing bounded
import closure starts at this actual payload; an empty closure now makes the
build record fail immediately. Source, current run/attempt, compiler/dependency,
patch, runtime DLL bytes and real-tool hash checks remain required.

A related production fixture exposed an unconditional success-path TypeError in
`finish()`: constructing the failure message concatenated `None` even when
`built=true`. The success branch now returns normally, while a failed build
retains its original failure and still raises. A positive finish fixture verifies
both real payload selection and the resulting receipt, not only failure paths.

The live preflight now initializes a failed record before verifying the tool,
compiler and fingerprint. Early setup failures retain bounded exact errors with
`passed=false`, no cases and no results. Existing strict preflight validation
rejects that record. The four live cases (signal pass with original leaf stack,
normal detach, abrupt debugger exit survival, timeout detach) and all their
acceptance checks are unchanged. Observer mode remains opt-in and diagnostic
only; passing its fixture never establishes consumer acceptance.

## Verification and native limits

Regression coverage first reproduced the missing real-payload resolver, absent
setup-failure JSON, empty-runtime success record and success-path TypeError.
The final fixtures exercise both real Libtool names, launcher-only/ambiguous
output, native PE architecture/type, Windows reparse metadata without requiring
symlink privilege, real POSIX links, exact receipt path/tool/runtime mutations,
actual import graph traversal, missing DLLs, empty closure refusal, successful
finish, and preflight setup failure without launching any target.

Executed locally on macOS:

- `python3 -m unittest discover -s script/msix -p 'test_*.py' -v`: 62 passed.
- All 11 `script/msix/test_*.ps1` fixtures passed under PowerShell 7.6.6.
- All MSIX PowerShell helpers parsed and `git diff --check` passed.
- Final targeted diagnostic build/reporting rerun: 10 passed.
- Full log: `/private/tmp/inkquay-real-gdb-payload-tests.log`.

PowerShell executable:
`/Users/hashfunction/workspace/project_app_factory/microsoft-store/apps/filequay/source/.tools/powershell-7.6.6/pwsh`.
The prior private build took about 15 minutes. This candidate adds no compiler,
download, build flag or redistributed tool binary. A fresh Windows run must
record the actual `.libs` payload/runtime closure, pass all four unchanged live
survival cases, and then capture the installed failure. Neither native attachment
nor the application crash cause is claimed from these local tests.
