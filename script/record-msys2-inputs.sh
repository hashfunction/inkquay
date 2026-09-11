#!/usr/bin/env bash
set -euo pipefail
# The setup action clears its download cache. Retrieve packages for the actual
# installed native environment, then reject any version mismatch before recording hashes.
mkdir -p build-evidence/package-cache
pacman -Q | awk -v prefix="$MINGW_PACKAGE_PREFIX-" 'index($1,prefix)==1' | sort > build-evidence/native-installed-versions.txt
mapfile -t portfolio_native_packages < <(awk '{print $1}' build-evidence/native-installed-versions.txt)
if (( ${#portfolio_native_packages[@]} == 0 )); then echo "No native packages found" >&2; exit 1; fi
pacman -Sw --noconfirm --cachedir "$PWD/build-evidence/package-cache" "${portfolio_native_packages[@]}"
pacman -Qp build-evidence/package-cache/*.pkg.tar.zst | sort > build-evidence/native-downloaded-versions.txt
diff -u build-evidence/native-installed-versions.txt build-evidence/native-downloaded-versions.txt
sha256sum build-evidence/package-cache/*.pkg.tar.* > build-evidence/msys2-cache-sha256.txt
