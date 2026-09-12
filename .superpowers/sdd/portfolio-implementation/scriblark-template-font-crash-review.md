# Scriblark template-label rendering — actual Windows crash investigation

Base source: `8fc6368c7e221695022fda4bdd3e07cde6e34cc6` (Scriblark 1.0.1).
This candidate changes only template-label rendering and native rendering tests.
It preserves the renamed product, compatibility paths, source dependencies,
package identity and the complete installed qualification/observer policies.

## Actual fault evidence

Diagnostic run [34687949814](https://github.com/hashfunction/inkquay/actions/runs/34687949814)
uses pre-rename public source `8b01a77365457f4b96c7cf34275dbfd0713803c4`.
Its four real Windows debugger preflight cases all passed: signal-pass captured
the original leaf and target exit 1; normal-detach, abrupt-debugger-exit and
timeout-detach each preserved the target until its expected exit 0.
The installed observer then actually attached and resumed exact retained PID
7816, executable SHA256
`c4b9762b857117ccd000cf60feddccafd31f73078814eb3e23de8d2ec5567fd7`, in
`Trieflow.InkQuay.Qualification_1.0.0.0_x64__fjvr7t994vwc4`.
The actual GDB SHA256 was
`28ed040148637aed56f9e9497ba34d89b1bbc60c207390796608e0d626deb3b8`.

The workflow inserted the Cornell template at 10:56:31.7918836 UTC. Three
SIGSEGV stops followed before the recorded Save input at 10:56:32.2163218:

| Stop (UTC) | Actual stack path |
| --- | --- |
| 10:56:31.827892 | Main thread: d2d1 → libcairo → `PagePreviewDecoration::drawPageNumberBelowPreview` → `SidebarPreviewBaseEntry::drawCallback` → GTK |
| 10:56:31.857414 | XournalSchedule thread: d2d1 → libcairo → template label `cairo_show_text` (`InkQuayBackgroundView.cpp:25`) → background draw → DocumentView → RenderJob → Scheduler |
| 10:56:31.894557 | Same scheduler template-label path |

All stop records identify address `0x7ffc9bdafbe2`. The independently matched
Application Error event reports d2d1.dll offset `0x2fbe2`; the retained target
exited `0xC0000005`. GDB's `D2D1MakeSkewMatrix` labels are nearest exported
symbols, not proof of the exact internal Direct2D function. The source-resolved
application frames establish the conflicting drawing paths. This is a template
insertion/rendering failure, not evidence of a Save picker defect.

The actual `reloaded-template.png` was viewed: it shows the owned configuration
dialog with the Cornell template. It does not establish a completed working
page, saved document or accepted consumer workflow.

Observer capture succeeded, but observer cleanup did not finish cleanly:
`Detach: GDB command failed: 33^error,msg="The program is not being run."`
was retained after the target died, with debugger fallback termination and
debugger exit 1. That secondary diagnostic error remains separate from the
original access violation. Installation cleanup errors were empty; normal exit
and consumer acceptance were false. This candidate does not modify that code.

The independently inspected normal renamed run
[34688926273](https://github.com/hashfunction/inkquay/actions/runs/34688926273),
public source `f6f85b3c7cd9f00b384626d0c428b1a0136b7caf`, failed immediately
after the same insertion boundary. Its retained Scriblark PID 5892 exited 1,
with no observer requested and no matching Application Error. It supplies no
additional native stack and cannot independently establish the DLL cause.

Downloaded metadata only: old artifact 10296996882 (1,149,137 bytes) under
`/private/tmp/inkquay-34687949814-review/build-evidence`; renamed artifact
10296223105 (1,121,973 bytes) under
`/private/tmp/scriblark-34688926273-review/build-evidence`.
Old diagnostic evidence SHA256 values:

| File | SHA256 |
| --- | --- |
| crash-observer-preflight.json | `b149cb7ad525c51938ed47da26be009f2f7cd101c0705b2c59deb56740d4a08d` |
| crash-observer-tool.json | `f4f529140ec6c8631560d8e825bd39030b298313b336ab21d4251ea936675093` |
| msix-install/crash-observer.json | `813b5e3d78347bfe9e17fc886ab41dee3c2ce1f8585a9711c50984fc0183e6b4` |
| msix-install/crash-observer.txt | `c5c13e30cf1dd9b8b504f08cb34ff70b19f1d1e5fd6fa889fbadbb3b8298571f` |
| msix-install/installation-qualification.json | `f41aefa81181f71a63079acf5a85a75254fa0969d0f0c5a31ddbb2dd1b3317bf` |
| msix-install/workflow/workflow-result.json | `f95b2387580afa1ab7896aa6287f9ba12945422a86c56f31e09bf7f5aa078d5d` |
| inkquay-windows-inventory.json | `5b7d017de395701ca3a82f08429a6c5044b22d46ed8b73321336e41bd3b4a0d0` |

## Exact dependency source proof

The actual inventory binds libcairo-2.dll (1,247,164 bytes, SHA256
`c474166543aed18b389b20122ca2741189504994dafd86cd5ed121e95bd82ce4`) to
`mingw-w64-x86_64-cairo 1.18.4-4`. The existing SOURCE-INPUTS record pins binary
archive SHA256 `1487120562e42601a8462d9953098f685c513999a2e472a3524fa96434be3290`
and PKGBUILD SHA256
`c6474a55d3fdd53d0fe40aa0d183536d0704abbe3d3a791e98688e588a694ffb`.

The retained exact preferred-source archive
`mingw-w64-cairo-1.18.4-4.src.tar.zst` was rehashed: 32,574,040 bytes,
SHA256 `3a83c94fd2818872441db8ded3e500aa1401e673fa389390b8423be954bafea2`.
It already exists under Pixel's `Release/native-source/runtime-source-archives`
and remains delivered through the unchanged
[original source collection](https://github.com/hashfunction/pixelquay/releases/download/native-sources-2026-09-11-c9f4add/pixelquay-native-sources-c9f4add.tar).
No new dependency archive was downloaded and no runtime input was substituted.

That recipe enables DirectWrite, Fontconfig and FreeType. Its included
[DWrite patch](https://github.com/msys2/MINGW-packages/blob/305ebda98c3041d9986d6fae498b45d2b2b9f4e8/mingw-w64-cairo/0001-DWrite-Get-glyph-bitmap-with-D2D-in-selected-cases.patch)
is 17,156 bytes, SHA256
`b54b016d088078ee78e9617524653fd0f0a1e8cff346cbe7ef795dce7c6a5e4f`.
The official file and the directly extracted source-archive member have this
same hash, also matching retained source-member metadata. The patch identifies
upstream commit `b97172ca313627df4fac14c386e5baeeba5fbd6e`. It routes default/
good/best/subpixel antialiasing to `create_glyph_bitmap_d2d` first.

The upstream [Cairo 1.18.4 DirectWrite implementation](https://gitlab.freedesktop.org/cairo/cairo/-/blob/1.18.4/src/win32/cairo-dwrite-font.cpp)
was extracted directly from the nested cairo-1.18.4.tar.xz in that exact source
archive and compared with the official tagged file: 85,251 bytes, SHA256
`d2ab7245580ace45feac79d180eae871c9ca4ded3fd1291dfbc61e324d87ad8c`.
Its `D2DFactory` owns a global factory created with
`D2D1_FACTORY_TYPE_SINGLE_THREADED` and shared render target; the patched glyph
path uses that factory. Microsoft documents that a
[single-threaded Direct2D factory requires application synchronization](https://learn.microsoft.com/en-us/windows/win32/direct2d/multi-threaded-direct2d-apps).
The actual simultaneous main/sidebar and scheduler/template fault stacks,
together with this exact dependency implementation, identify the unsafe new
template worker's Cairo toy-font path. They do not identify an internal d2d1
instruction's precise defect without private symbols.

## Bounded repair

Template labels now use a Pango layout per draw, following existing document
text rendering. `src/exe/Xournalpp.cpp` already selects
`PANGOCAIRO_BACKEND=fc` on Windows. Pango's
[default Cairo font map is per thread](https://gitlab.gnome.org/GNOME/pango/-/blob/1.58.2/pango/pangocairo-fontmap.c).
The worker therefore uses existing Fontconfig/FreeType text rendering instead
of the DirectWrite/D2D factory shared with sidebar toy text. No global mutex,
runtime dependency patch, observer exception policy or new backend selection
is introduced.

All four labels retain Sans, absolute size 10, original strings/colors and
baseline coordinates. Fractional glyph positions and the Pango context matrix
follow `Text::createPangoLayout`/`TextView::initPango`; subtracting Pango's actual
baseline preserves the existing Cairo baseline placement. Existing page scaling,
rules and Cairo save/restore remain. Font rasterization intentionally follows
the document renderer, so this does not claim identical toy-font pixels.

## Regression and local verification

The new pixel regression renders actual production templates and independently
renders the same label through the existing Text/TextView code. It rejects blank
labels, compares every label-region byte and checks Cornell's vertical rule.
Before the repair, the four header comparisons failed with 1,442 / 1,108 /
1,952 / 2,689 differing bytes at scale 1. After repair they pass at scales 0.5,
1 and 1.5 (12 comparisons).

The real concurrency test synchronizes two template worker threads with a third
thread doing the same Cairo toy-font operations as the sidebar. Forty-eight
actual template renders use varying cold font sizes and all four templates;
their Cairo status and pixel hashes must match subsequent serial renders. Each
worker selects the actual Fontconfig backend using a thread-local font map and
restores it afterward. The test does not fabricate UI or assume a stress test
reliably reproduces a Windows race on macOS.

Commands from the nested source root:

```
cmake --build build --target test-units test-gtk-integration --parallel 2
ctest --test-dir build --timeout 60 --output-on-failure
clang-format --dry-run --Werror src/core/view/background/InkQuayBackgroundView.cpp test/unit_tests/control/InkQuayBackgroundTest.cpp
git diff --check
```

Result: all 135 native tests passed, including GTK integration and the three
template tests; build and formatting checks passed. Existing local macOS
Cairo 1.18.4/Pango 1.58.2 build dependencies were reused. Logs are under
`/private/tmp/inkquay-34687949814-research`: `labels-red.log`,
`templates-final.log`, `test-build-final.log`, `ctest.log`.

Independent review and a fresh Windows run remain required. Neither the macOS
tests nor this product repair claim that renamed installed workflow, normal
close, module closure, uninstall or Store qualification has passed. No push,
dispatch, parent/site/Store changes or FileQuay edits were performed.
