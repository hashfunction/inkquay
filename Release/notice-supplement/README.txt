InkQuay source and original notice supplement

Source, build instructions and the matching dependency source inputs:
https://inkquay.trieflow.com/source

SOURCE-INPUTS.json identifies all 66 retained native source packages, their
recipes and archive hashes, and all 359 locked Cargo source archives used to
prepare librsvg. It also identifies the original source-collection baseline;
the package's sourceInputs record binds the current application revision.
The current winpthreads 14.0.0.r375.g9c1abbbf5-1 source is a separate published
supplement, explicitly indexed with its own URL, size, hash and matching MINGW64
binary recipe evidence. It is not a member of the original frozen collection:
https://github.com/hashfunction/pixelquay/releases/download/native-sources-2026-09-12-tintfable/mingw-w64-winpthreads-14.0.0.r375.g9c1abbbf5-1.src.tar.zst
The source archive supports multiple MinGW environments; the index binds this
application's MINGW64 binary, not another application's CLANG64 binary. Original
libwinpthread COPYING is unchanged and retained in the existing MSYS2 notices.
The source page supplies the current application source, the indexed native
inputs, original notices, and build/relink/repackage instructions. Rebuild
outside WindowsApps and use your own distinct package identity and certificate.

NOTICE-INDEX.json binds every retained original file in originals/. Paths are
preserved to avoid same-basename collisions. These supplement, and do not replace,
the original application LICENSE, AUTHORS, copyright.txt, Debian copyright and
the existing MSYS2 notices in the parent licenses directory.

Contents: 46 native notice/data files, 643 original Cargo notice files,
42 original Cargo attribution/manifest/source files, one pinned upstream license
and three Rust 1.98.1 runtime notices. The complete Cargo lock includes additional
platform, development and build-only packages. Inclusion here does not claim
that every package or source file is linked into the application. Empty original
files, including DjVuLibre AUTHORS, are intentionally preserved byte-for-byte.

Original LGPL, MPL, permissive and asset notices remain under their own terms;
none is rewritten or converted by this supplement. The original detailed
copyright.txt describes application and asset attributions. The source collection
includes GPLv3 text with the native notices; the application's GPL-2.0-or-later
grant permits distribution under that later version while original grants remain.

Copyright 2026 Trieflow LLC for this explanatory notice and index arrangement.
Original files retain their upstream copyright notices and licenses.
