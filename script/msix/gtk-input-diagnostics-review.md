# Bounded GTK input diagnostic for Scriblark

This change observes the unresolved second-export failure. It does not fix that failure or confer consumer acceptance.

## Original evidence

Run **34699692508**, public source `e4cc0bf0e81b02f34c634d200a0ac989155562b9`, retained a real first PDF of 24,219 bytes, SHA-256 `8480e836498ecb09fec70af6d532e975da88781fe4a1fbbc7eacd23b5a614983`. The application report and independent checks passed two pages, protected input hashes, text and Cornell raster checks. After Ctrl+O reopened that PDF, the title and both thumbnails painted in the original process 5440 / HWND 655852. The second six-event native Ctrl+Alt+E insertion completed at 15:02:04.646Z, but the original 20-second chooser observation found no Export File dialog. Native foreground/focus remained owned, GUI flags were zero and no modifiers remained held. The run is failed; the reopened export remains unverified.

The actual before/after JSON, screenshots, first report and workflow receipt were read from `/private/tmp/scriblark-34699692508-review/Scriblark-Windows-qualification/build-evidence/msix-install/workflow`. Earlier attempts with the normal File menu also failed after reopening the PDF. Neither a further shortcut nor a delay is supported by this evidence.

The source trace establishes:

- `EXPORT_AS_PDF` has no document-type predicate; the action defaults enabled. `openPdfFile` changes the cursor and document but does not call `Control::block`.
- `fileLoaded` updates title, page numbers and page actions but does not request GTK widget focus. Native HWND focus does not identify the internal focused widget.
- `XojOpenDlg` genuinely defers its callback. `Util::execInUiThread` uses `G_PRIORITY_DEFAULT_IDLE`; GTK 3.24.52 `gtk_window_close` queues deletion at `G_PRIORITY_DEFAULT`, so its apparent source line order is not proof of a callback-before-close bug.
- The existing MainWindow handler explicitly propagates to the focused widget before GTK's default handler. If that propagation returns true, the default accelerator handler is not reached. The normal GtkXournal handler has no Ctrl+Alt+E branch; actual focus/grab/consumption is missing from the native receipt.

Primary references: [GTK 3.24.52 window implementation](https://raw.githubusercontent.com/GNOME/gtk/3.24.52/gtk/gtkwindow.c), [GTK 3.24.52 event dispatch](https://raw.githubusercontent.com/GNOME/gtk/3.24.52/gtk/gtkmain.c), [focused widget query](https://docs.gtk.org/gtk3/method.Window.get_focus.html).

## Implementation

`InputDiagnostics.{h,cpp}` is owned by `XournalMainPrivate` only when the explicit `--input-diagnostics PATH` option is supplied. It exclusively creates a new binary-mode UTF-8 JSONL file in an existing absolute parent without path redirection. Existing files, directories, relative paths, missing parents and links are refused. There is no default logfile, environment-triggered activation or normal-mode timer/hook.

After MainWindow and its action map are initialized, the helper observes:

1. A Windows GDK native filter for Ctrl/Alt and the E/O/F chord codes, including WM_KEYDOWN/UP and WM_SYSKEYDOWN/UP. It always returns `GDK_FILTER_CONTINUE`.
2. GTK's public key snooper for those same relevant keys. It always returns `FALSE` and never changes the event. This GTK3 API is deprecated, but remains available in the actual 3.24.52 dependency and is used only for the expressly selected diagnostic.
3. Before/after the existing **single** `gtk_window_propagate_key_event` call and its exact boolean result. The inactive wrapper immediately performs that original call, with no diagnostic inspection or allocation.
4. Actual focus type/sensitivity/main-window ancestry, group/device-grab type and state, event target type, top-level focus/active state, and OPEN/EXPORT_AS_PDF action presence/enabled/activate observations.
5. `fileLoaded` completion and a one-second event-loop heartbeat.

Only fixed phase names, numeric IDs/keycodes/modifier masks, booleans and bounded GObject type names enter the trace. No key string, document filename/path, window title, widget name, entry text or action parameter is inspected or logged. Filtering retains the reviewed E/O/F codes during an observed modifier-down sequence even if the event loses its raw modifier mask; that raw mask is recorded unchanged. Independent native and GTK sequence state is used only to avoid concealing this diagnostic case. Hooks and heartbeat are removed before ordinary shutdown. Each row is flushed; maximum output is **512 records / 1 MiB**, including a reserved terminal `truncated` record. Logging failures suppress further logging and leave event propagation intact.

Primary APIs: [GDK native filter](https://docs.gtk.org/gdk3/method.Window.add_filter.html), [GTK key snooper](https://docs.gtk.org/gtk3/func.key_snooper_install.html), [GTK focus propagation](https://docs.gtk.org/gtk3/method.Window.propagate_key_event.html).

The independent workflow flag is `capture_input_diagnostics`. It threads `-CaptureInputDiagnostics` through both PowerShell coordinators and supplies only the quoted diagnostic path through the existing [ActivationManager argument](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-iapplicationactivationmanager-activateapplication). The file lives in that invocation's freshly owned `.inkquay-install-<nonce>` directory. Normal activation continues to pass null arguments. This flag does not build or attach GDB.

After original owned-process cleanup, `input_diagnostics.ps1` performs a bounded read and requires the retained broker PID, exact owned path, no reparse points, schema/sequence/phase/types/keycode allowlists, UTF-8 and complete lines. It copies those exact bytes exclusively to `build-evidence/msix-install/input-diagnostics.jsonl` and records length/hash/count/truncation. Collection errors are secondary `input_diagnostic_errors`; the original primary and cleanup errors remain intact. The production cleanup-operation replay caught and corrected an initial local-scope loader issue before commit.

Diagnostic mode cannot build the Store identity, run the unsigned exporter or upload a Store package. Installation/consumer acceptance flags remain false even when its original workflow happens to complete. The independent exporter also rejects the diagnostic environment, receipt flags, embedded workflow flag and diagnostic output. Default qualification still requires the complete original two-identity workflow and cleanup.

## Verification

Red observations: the new native fixture initially failed because the helper did not exist; the new export-context tests demonstrated that input diagnostic mode was previously accepted. Green verification:

- Real current C++ application, unit and GTK test targets build locally. All **136 native/GTK tests pass**.
- New real GtkTest fixture asserts the same single focused-child delivery, consumed return and default accelerator effects with logging disabled/enabled. It checks actual focus/action/fileLoaded/heartbeat records, unrelated-key and private-text exclusion, existing/missing/relative/directory/link output refusal, and exactly 512 records ending in truncation. An additional actual GTK red/green case requires the E event with a lost raw modifier mask to remain visible after an observed Control-down.
- The fixture includes a Windows-only real owned HWND/SendInput branch that requires one actual GTK action plus the native-filter record. That branch **has not run on macOS** and is required in fresh Windows CI.
- The actual built `Scriblark --input-diagnostics EXISTING_FILE` exits 1 and preserves the original file bytes.
- All **95 Python MSIX tests pass**; the 13 complete installed-evidence and three unsigned-export tests were rerun after final evidence changes.
- Production PowerShell diagnostic reader passes eight malformed/foreign/oversized refusal cases, exclusive/dormant argument cases, and a replay of **20 unmodified records from the final actual C++ GTK writer**.
- Ten actual final-reporting cases preserve successful diagnostic execution without acceptance and original failure/cleanup evidence after a diagnostic collection failure. Five original coordinator cases plus all four GDB/input flag combinations exercise the actual final dispatch expression.
- Original six installer-orchestration cases, public shortcut/window ownership fixtures, 22 debugger ownership cases and all PowerShell parsing pass.

Representative commands from the source root:

```sh
cmake -S . -B build
cmake --build build --target xournalpp test-units test-gtk-integration --parallel 2
ctest --test-dir build --timeout 60 --output-on-failure
python3 -m unittest discover -s script/msix -p 'test_*.py'
../../filequay/source/.tools/powershell-7.6.6/pwsh -NoProfile -File script/msix/test_input_diagnostics.ps1
../../filequay/source/.tools/powershell-7.6.6/pwsh -NoProfile -File script/msix/test_msix_evidence.ps1
../../filequay/source/.tools/powershell-7.6.6/pwsh -NoProfile -File script/msix/test_store_orchestration.ps1
```

Root dispatch after review/public snapshot: workflow `windows.yml`, **`capture_input_diagnostics=true`, `capture_crash_stack=false`**. Read the new JSONL alongside the unchanged native before/after observations. A continuing heartbeat with native events but no GTK key identifies the GDK/GTK boundary; a GTK target/grab outside the main window identifies routing; a true propagation result identifies focused-child consumption; a false result with disabled action identifies action availability. None should be inferred before the new native trace exists. No push, Store mutation, marketing change or acceptance claim was made here; marketing preparation commit `cbfea06d` is preserved.
