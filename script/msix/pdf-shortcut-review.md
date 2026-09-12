# Direct PDF export shortcut

Run 34697785459 built Scriblark and passed its native tests. Its installed
qualification workflow saved the two-page note, exported a valid 24,219-byte PDF,
independently checked both pages and the Cornell template raster, and reopened
that PDF. The next native Alt+F chord inserted all four events but did not open
the GTK File menu. The following Export mnemonic was correctly refused before
input because the required owned menu was absent. No Store package was approved.

The original observation shows only the enabled main GTK window, PID 1080,
HWND 459270, foreground and focus both owned, with all modifiers released. The
same reopened-PDF condition occurred with SendKeys in run 34695588044. Switching
input APIs did not resolve the menu behavior. The underlying cause of the GTK
mnemonic failure is not established; this change does not claim to repair it.

Scriblark now exposes **Ctrl+Alt+E** on its existing Export as PDF menu item.
This is a normal public application shortcut, connected to the same export
action and destination/report flow. The consumer workflow invokes that shortcut
once for each document, using six serial native key events after checking the
sole owned editor, foreground, focus and released modifiers. It still requires
the actual Export File chooser, original application report, independent
Poppler checks, PDF reopening, both full installed identities and normal cleanup.
There is no alternative input replay after a failure.

The original two menu actions become one direct shortcut per export, making
25 recorded inputs instead of 27. The independent evidence validator requires
that exact order and six typed native events for both exports; omission,
duplication, reordering, wrong document, old two/four-event counts and SendKeys
claims are refused. Existing original failed Windows receipts remain failed.

Local verification: the new shortcut contract test failed before implementation;
afterwards its native plan and nine ownership/modifier refusals pass, along with
the original reopened-editor observation and four source shortcut mutations,
including an accelerator collision with an existing menu action.
All 13 independent workflow evidence tests pass. Existing source/menu and native
window fixtures pass locally; their actual Windows HWND branch remains a fresh
runner check. That branch now invokes Ctrl+Alt+E twice against a real owned
native menu action before compiling Scriblark, checking six inserted events,
exactly one action each time and released modifiers.

The complete native Windows application workflow remains required before release.
Marketing capture work is stashed separately and is not part of this change.
