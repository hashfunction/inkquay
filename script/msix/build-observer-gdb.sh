#!/usr/bin/env bash
# Copyright 2026 Trieflow LLC. MIT. Private diagnostic tool; never installed or packaged.
set -euo pipefail
test "$CI" = true
test "$MSYSTEM" = MINGW64
test "$GITHUB_REPOSITORY" = hashfunction/inkquay
cd "$(dirname "$0")/../.."
observer_build_root="$PWD"
trap 'observer_build_exit=$?; cd "$observer_build_root"; python script/msix/observer_gdb_build.py finish --exit-code "$observer_build_exit"' EXIT
python script/msix/observer_gdb_build.py prepare
cd build-observer-gdb/build
# Reuse the already recorded native compiler and libraries; do not install or
# replace any toolchain file. Two compile jobs cap memory use on hosted runners.
export CC=/mingw64/bin/gcc CXX=/mingw64/bin/g++
export CFLAGS='-O1 -g0' CXXFLAGS='-O1 -g0'
timeout --kill-after=10 300 bash ../source/gdb-17.2/configure \
  --build=x86_64-w64-mingw32 --host=x86_64-w64-mingw32 --target=x86_64-w64-mingw32 \
  --disable-werror --disable-nls --disable-win32-registry --disable-rpath \
  --disable-binutils --disable-gas --disable-gold --disable-ld --disable-gprof --disable-gprofng --disable-sim --disable-gdbserver \
  --without-python --without-guile --without-debuginfod --without-intel-pt --disable-tui --disable-source-highlight \
  --without-static-standard-libraries --with-system-zlib \
  --with-libiconv-prefix=/mingw64 --with-expat=/mingw64 --with-gmp=/mingw64 --with-mpfr=/mingw64 \
  --with-lzma=/mingw64 --with-zstd=/mingw64 \
  --with-libexpat-type=shared --with-libiconv-type=shared --with-liblzma-type=shared --with-libxxhash-type=shared \
  > ../configure.log 2>&1
timeout --kill-after=10 1200 make -j2 all-gdb MAKEINFO=true > ../make.log 2>&1
