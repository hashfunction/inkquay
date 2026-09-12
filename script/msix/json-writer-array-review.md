# Preserve declared JSON array shape

Run 34708354136 completed both actual installed Scriblark workflows and normal
cleanup, then failed the independent exporter’s exact accessible-tree equality.
In both original artifact directories, `accessible-window-tree.json` is an
object while `window-observation.json.controls` is a one-element array. Wrapping
the original standalone object in an array produces exact equality. The nodes
are the actual `Unsaved Document - Scriblark` GTK window, owned by PID 2744 in
qualification mode and PID 7340 in Store mode. Original artifacts were not edited.

`Get-WindowQualification` already supplies `@($items)`. The shared writer’s
pipeline into `ConvertTo-Json` enumerates that array: zero items generate no JSON,
one generates an object, and multiple items generate an array. The one-line
repair passes the declared value through `ConvertTo-Json -InputObject` instead.
Depth, encoding, exclusive file creation and all consumer/export equality gates
remain unchanged.

The new fixture calls the actual production writer. Before the repair, zero-item
JSON parsing failed and the singleton root was an object. Afterward, all four
cases pass: zero/single/multiple root arrays with nested empty/single/multiple
arrays and typed values, exact standalone/embedded node equality, unchanged UTC
text, and refusal to overwrite an existing output. The existing genuine GTK-root
window fixture and six negative scenarios also pass. The writer fixture is added
to the existing Windows MSIX preflight list. `git diff --check` passes.

These are local PowerShell serialization checks, not a new Windows run. No
exporter change, reconstructed historical receipt, app rebuild, push or dispatch
was performed. A fresh native run remains necessary for final Store export.
