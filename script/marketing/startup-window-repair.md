# Capture startup window convergence

Original run `34723271468` failed in marketing activation with `Actual capture main window unavailable`. Its artifact contains no PNGs. The original `failure-windows.json` (275 bytes, SHA256 `7f289e5355686db49a0d8717025991700ab1f58998425b6ad9fb9ae5cef225b6`) records one visible, enabled `gdkWindowToplevel`, HWND `590310`, PID `5592`, owner `0`, title `Unsaved Document - Scriblark`, bounds `78,78,816,639`. The process/package/executable checks had passed. The result records no cleanup errors, no residual package, unchanged unsigned bytes, and forced cleanup exit `-1`; it does not claim normal close or successful capture.

The rejected `Process.MainWindowHandle` and `Process.MainWindowTitle` values were not recorded. Therefore the original does not prove whether the title was transient or a getter/native observation differed. The concrete premature-failure path is visible in the capture code: it stops waiting on any nonzero handle, then checks the title only once. The successful qualification uses the same broker and exact initial title, with a different refresh/poll order and later stability observation.

The capture-only waiter now converges on the complete original process handle/title predicate within the same 30-second deadline, and additionally uses the unchanged qualified `Select-InkWorkflowWindow` for native PID, handle, title, class, visibility, enabled state, dimensions and ambiguity checks. Retained process/package/executable ownership is revalidated on each read; ownership failures remain terminal. No activation or input is replayed. A result observed after the deadline cannot be accepted.

`startup-window-observations.json` retains the getter values alongside the actual native inventory, elapsed time, acceptance state and last rejection. It is bounded to 301 samples and 64 windows per sample, with explicit omitted-sample count. The exclusive original JSON writer records it once. Failure observation remains secondary to the original lifecycle error.

Focused verification:

- `pwsh -NoProfile -File script/marketing/test_capture_operations.ps1`: existing loader, single activation contract and lifecycle/cleanup scenarios pass; 12 new production-waiter scenarios cover valid/transient readiness, wrong title, foreign/duplicate/hidden/disabled/wrong-class windows, zero handle, late readiness, and lost ownership. The actual qualified selector executes; only read/sleep leaves are substituted. Original exclusive JSON writer preserves rejected and accepted samples. The new fixture failed before the waiter existed and passed after implementation.
- `python3 -m unittest discover -s script/marketing -p 'test_*.py' -v`: 5 passed.

The Store binding remains run `34710260935`, source `21476437b6a187b3a8717d844fefe5f47815386c`, unsigned MSIX SHA256 `72169ef657f1adc8c47be28760d503763e25017ef2b0f883dfeaf36b770e1deb`. Product code, qualified helpers, binary and lifecycle acceptance are unchanged. A fresh actual Windows capture is still required.
