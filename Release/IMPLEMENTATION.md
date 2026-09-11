# InkQuay source handoff

Implementation based on Xournal++ v1.3.7, commit `104f89826a9b1e2d0c098cea58639d6686f78526`, with upstream history and notices retained on `codex/inkquay`. This is a source/native macOS validation handoff. Windows execution, packaged dependency licensing and Store release are not complete.

## Implemented behavior

- The existing Paper Template dialog now selects named templates, saves the current paper settings as a user preset, renames/deletes user presets, and exposes retry after load failure. Built-ins are immutable. Selection changes the dialog model; only the existing OK action changes the default. Existing `.xopt` import/export remains available. Settings live under InkQuay's own configuration directory; upstream settings are not migrated implicitly.
- A versioned GKeyFile collection stores canonical page-template strings, validates Unicode names/IDs/page dimensions, and writes through GLib consistent/durable replacement. Failed loads lock every mutation until a successful explicit reload; on-disk changes since load are rejected. This prevents ordinary stale writes, but is not a cross-process compare-and-swap transaction.
- Original meeting, Cornell, storyboard and practice-staff patterns are real vector backgrounds rendered by the existing native Cairo factory. The `iq` configuration retains an existing `.xopp` ruling type so older readers have a conventional ruling fallback. The application/file icons are original Trieflow vectors.
- Ordinary PDF Export, Custom PDF Export and the CLI helper use the existing Cairo/qpdf backend through a checked, same-directory staged export. Poppler reopens the file and checks exact requested page count, finite positive sizes and nonzero bytes. Source document/background paths, directory-symlink aliases and hardlinks are protected; source hashes must remain unchanged.
- Each attempt writes a distinct JSON report with expected/actual pages, bytes, source hashes, output/diagnostic path, recovery files, warnings, status and a publication flag. Failed/short output remains in its staging directory for diagnosis. The PDF chooser captures file identity (volume/device and file ID/inode), size and SHA-256 before asking to replace an existing file. Both ordinary and custom PDF jobs retain that exact consent through export. A new name never grants replacement permission. For a confirmed existing target, the worker moves it into the unique staging directory with a native no-replace rename, validates the moved identity/content, then publishes the PDF with a no-replace hardlink. On failure/cancellation it restores the previous file with another no-replace rename; if a concurrent file blocks restoration, the original, competing file and diagnostic export remain available and recovery paths are reported. Successful replacement also retains the original as `previous-output.pdf`. Filesystems without the required no-replace operations fail safely. CLI export refuses existing destinations. This is a recovery protocol, not an atomic cross-process conditional replacement: the target can temporarily be absent, interruption may leave recovery files, and an external process can still alter files it owns. No approved original is automatically deleted.
- Worker jobs perform PDF hashing/verification off the GTK thread, then present results through their existing scheduler callback. Structural checks do not assert visual fidelity, accessibility, or correct annotation appearance. Existing upstream GUI PDF jobs are blocking and have no cancel API: engine cancellation is tested, but no new GUI cancel control is claimed.
- Product display, executable/wrapper, application ID, config directory, main icons, Windows registry/associations/publisher and support metadata use InkQuay / Trieflow LLC / `com.trieflow.inkquay`. Product, privacy, support and source publication belong under `https://inkquay.trieflow.com`. Internal upstream target/class/format names and copyright attribution remain. No Store identity is invented.
- Unqualified Lua/plugins, audio, GTKSourceView and cpptrace downloads are off in the release configuration. Upstream service/release/Crowdin workflows are retained outside the active workflows directory. System GoogleTest is required; no silent source download occurs.

## Validation

See `verification/summary.json` and logs. Native compilation uses Apple Clang 21.0.0 (Xcode 26.6.0, SDK 26.5), CMake 3.26.4, Ninja 1.13.2, GTK3 3.24.52, Poppler 26.09.0, qpdf 12.4.1 and Cairo 1.18.4. This local build targets macOS 26.0 because the current Homebrew dependencies require it; it is not a tested macOS distribution target.

The GoogleTest 1.18.0 Homebrew bottle is C++17 and lacks its C++20 `char8_t` printer. The same release source was hash-verified and built with C++20 under ignored `build-deps`; its source URL/SHA are recorded in `windows-dependencies.json`. GoogleTest is test-only.

Tests cover library roundtrip/validation/immutability/corrupt and stale files; deterministic own-generated native PDF files; short/invalid/empty exports; source aliases; failed, cancelled and changed-target runs; explicit overwrite authorization; immutable report names/escaping; existing Document/CLI Cairo, qpdf background/range and progressive layer export; distinct native vector layouts; and the upstream serialization/model suite. The real GTK dialog test compiles but was not executed on the locked Mac. The native-layout PNGs are Cairo fixture artifacts, not application screenshots.

Local commands (requires the documented native dependencies):

```sh
PKG_CONFIG_PATH=/opt/homebrew/opt/libxml2/lib/pkgconfig cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DENABLE_GTEST=ON -DDOWNLOAD_GTEST=OFF \
  -DENABLE_CPPTRACE=OFF -DENABLE_AUDIO=OFF -DENABLE_PLUGINS=OFF -DENABLE_GTK_SOURCEVIEW=OFF \
  -DCMAKE_PREFIX_PATH=/opt/homebrew -DCMAKE_OSX_DEPLOYMENT_TARGET=26.0 \
  -DGTest_DIR="$PWD/build-deps/gtest-install/lib/cmake/GTest"
cmake --build build --target pot translations
cmake --build build
cmake --build build --target test-units test-gtk-integration
ctest --test-dir build -E 'PaletteTabTest|PageTemplateDialogTest|PdfDestinationConsentTest' --output-on-failure
cmake --install build --prefix "$PWD/build/stage"
```

## Windows handoff commands — prepared, not executed

Use MSYS2 MINGW64 on Windows x64 with the package list in `.github/actions/install_deps_windows/action.yml`. Root should freeze the actual package archives/source inputs after the first qualified build; rolling package names and `update: true` do not constitute reproducible pins.

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DENABLE_GTEST=ON -DDOWNLOAD_GTEST=OFF -DENABLE_CPPTRACE=OFF \
  -DENABLE_AUDIO=OFF -DENABLE_PLUGINS=OFF -DENABLE_GTK_SOURCEVIEW=OFF
cmake --build build --target pot translations
cmake --build build
cmake --build build --target test-units test-gtk-integration
ctest --test-dir build --output-on-failure
bash windows-setup/package.sh build
# Optional NSIS qualification only:
INKQUAY_BUILD_NSIS=1 bash windows-setup/package.sh build
```

`build/dist` is the input for root's own MSIX identity/layout. `build/inkquay-windows-inventory.json` records actual package versions, every staged file/hash and matched owner or explicit unmatched provenance. Inventory/notice generation is not licensing clearance. The MSIX tools must validate root's real manifest and runtime stage; no Windows build, installer, signing or certification has run here.

Remaining acceptance: execute all GTK tests and real keyboard/restart/100–200% scaling flows; Windows pen pressure/eraser/buttons/touch suppression; encrypted/unusual/missing-background PDFs, large scans, read-only and long Unicode paths; export cancellation/progress and source retention; install/upgrade/uninstall; every DLL/data/icon/locale notice and corresponding-source obligation; exact package/source archive freezes; root's source publication, canonical site/DNS, paid Store identity, signing and certification. Preserve GPLv2-or-later application rights and separately reconcile retained GPLv3+/ISC/CC BY-SA/CC0/BSD/BSL and native dependencies before distribution.


## Review repair: chooser consent and GTK test resources

Review `../review-implementation.md` found that the original GUI jobs passed `allowOverwrite=true` even when the chooser selected a new name. Two real Cairo/Poppler regressions reproduced both late-created and replaced destinations being overwritten. The bool API has been removed. `SaveExportDialog` now returns an `ExportDestination` for PDF jobs; hashing runs off the GTK thread, the replacement question identifies the captured path, and the exact consent is stored in `BaseExportJob` and passed by both PDF workers. Legacy non-PDF save callbacks keep their original contract. See the recovery protocol above and `verification/consent-repair-summary.json` for exact evidence.

The palette GTK tests were loading `paletteSettings.glade` from the install prefix although CTest runs before package installation. They now resolve the configured source UI directory and assert the resource exists before constructing GtkBuilder. The GTK fixture uses a non-unique test application and tears down windows, application references and arguments. GtkApplication already initializes GTK in its startup sequence; adding a separate `gtk_init` was not the identified remedy. The Windows run `34578272374` compiled and passed its 119 native tests, then stalled at the first GTK palette test. That log does not contain the stalled process stack. The resource defect is established by source/configuration inspection; attribution of the whole Windows stall and success of the repair require the Windows rerun.

A new GTK regression exercises the actual save chooser, changes an existing file while its confirmation question is open, and verifies that both confirmed and new-name selections reach the worker with the original consent. It is compiled locally, not executed on the locked Mac. Four GTK tests remain for Windows execution. Root owns CI, package launch, native input/license closure, MSIX and Store gates.
