# Bookmark focus and the second PDF export

Original diagnostic run 34705967156, public source
`0d8de6a12f5d5f91120ea87b6471d6da6b826616`, retained PID 9768/main HWND 983088:
`input-diagnostics.jsonl` has 176 records / 156,208 bytes and SHA-256
`de9eee32a1cf1b31dd5076126a236a212387b364e5a4d570695c8b85ad16f5f9`.
It was not truncated. First export E press reaches GTK with state 28 and
GtkXournal focus (sequences 109–111); propagation returns false, followed by the
normal export action. After PDF reopening, file-loaded records GtkTreeView focus
(sequence 147). The second native E press reaches GTK with the same state
(sequences 148–152), but propagation returns true, preventing action activation.
The main loop stays active with export enabled, no grab and released modifiers.
The original failure remains the second exact Export File window wait, found 0.
The first PDF passed its two-page/text/template/report checks. Full acceptance,
normal close and uninstall verification did not pass in that diagnostic run.

`SidebarIndexPage::documentChanged` refreshes its model and calls
`treeBookmarkSelected`, which previously always grabbed keyboard focus even when
the bookmark tab was inactive. This is the source-backed explanation for the
observed focus change: the Windows trace identified GtkTreeView, but did not
record exact bookmark identity or realized/mapped state. The screenshot shows
the thumbnail tab. GTK 3.24.52's [focus propagation](https://raw.githubusercontent.com/GNOME/gtk/3.24.52/gtk/gtkwindow.c)
and [unrealized-widget event guard](https://raw.githubusercontent.com/GNOME/gtk/3.24.52/gtk/gtkwidget.c)
explain why a hidden, never-realized focus widget consumes the event. The
unrealized condition is reproduced locally, not claimed as directly logged on
Windows. The application explicitly assigns Ctrl+Alt+E to Export as PDF in
`ui/mainmenubar.xml`; there is no intended hidden-bookmark reservation of it.

The production change is limited to the existing bookmark focus request: the
shared `focusBookmarkTree` helper requests focus only while the tree is mapped.
The callback's selection/navigation code, global propagation, accelerators,
consumer input sequence and diagnostic streams/budgets remain unchanged.

`BookmarkFocusTest` calls that actual production helper in a real GTK window
with the original propagation wrapper and normal export action/accelerator.
Before the guard, it fails with hidden GtkTreeView focus, handled=true, zero
export actions and GTK's unrealized-widget assertion. After the guard, the
identical shortcut activates once; a visible selected bookmark still receives
focus and preserves its row. A previously realized tree hidden again also
preserves canvas focus, rejecting insufficient visible-only or realized-only
fixes. All three normal shortcuts activate exactly once. The existing actual
GTK child-consumption and diagnostic flood/return tests still pass unchanged.

Local validation: application and both test targets built; all 137 CTest cases
passed, including the new regression and existing InputDiagnosticsTest. Red and
green logs are retained privately as `/private/tmp/scriblark-bookmark-before-test.log`
and `/private/tmp/scriblark-bookmark-after-tests.log`; full results are
`/private/tmp/scriblark-bookmark-all-tests.log`. Fresh Windows compilation and
both complete installed export/reopen/export lifecycles remain required.
