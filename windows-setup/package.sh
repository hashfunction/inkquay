#!/bin/bash
set -euo pipefail

# Windows packaging script. This does the following:
# 1. Run "install" target from CMake into setup folder
# 2. Copy runtime dependencies into setup folder
# 3. Create version file and execute NSIS to create installer

if [ -z "${1:-}" ]; then
    build_dir="$(pwd)"
else
    build_dir="$(cd "$1"; pwd)"
fi
setup_dir_name="dist"  # Same as in xournalpp.nsis
installer_name="InkQuay-setup.exe"  # Same as in xournalpp.nsis
setup_dir="$build_dir/$setup_dir_name"
script_dir=$(dirname $(readlink -f "$0"))
echo "Installing to $setup_dir and making installer $build_dir/$installer_name"

prefix=${MSYSTEM_PREFIX:-/mingw64}
echo "Set prefix to ${prefix}"

# Only replace the build-owned staging tree, never arbitrary user directories.
[[ -f "$build_dir/CMakeCache.txt" && -f "$build_dir/inkquay.exe" ]] || { echo "Expected an InkQuay Windows build directory" >&2; exit 1; }
# delete old setup, if there
echo "clean dist folder"
rm -rf "$setup_dir"
rm -rf "$build_dir/$installer_name"

mkdir "$setup_dir"
mkdir "$setup_dir"/lib

echo "copy installed files"
(cd "$build_dir" && cmake --install . --prefix "$setup_dir")

echo "copy libraries"
ldd "$build_dir/inkquay.exe" | grep "${prefix}.*\.dll" -o | sort -u | xargs -I{} cp "{}" "$setup_dir"/bin/
echo "Installing GTK/Glib translations"
# Copy system locale files
for trans in "$build_dir"/po/*.gmo; do
    # Bail if there are no translations at all
    [ -f "$trans" ] || break;

    # Retrieve locale from name of translation file
    locale=$(basename -s .gmo "$trans")
    locale_no_country=${locale%%_*}

    # GTK / GLib Translation
    for f in "glib20.mo" "gdk-pixbuf.mo" "gtk30.mo" "gtk30-properties.mo"; do
        for candidate in "$locale" "$locale_no_country"; do
            if [[ -f "$prefix/share/locale/$candidate/LC_MESSAGES/$f" ]]; then
                install -Dvm644 "$prefix/share/locale/$candidate/LC_MESSAGES/$f" "$setup_dir/share/locale/$candidate/LC_MESSAGES/$f"
                break
            fi
        done
    done
done

echo "copy pixbuf libs"
cp -r "$prefix"/lib/gdk-pixbuf-2.0 "$setup_dir"/lib/

echo "copy pixbuf lib dependencies"
# most of the dependencies are not linked directly, using strings to find them
find "$prefix/lib/gdk-pixbuf-2.0" -type f -name "*.dll" -exec strings {} \; | grep "^lib.*\.dll$" | grep -v "libpixbufloader" | sort | uniq | xargs -I{} cp "$prefix/bin/{}" "$setup_dir/bin/"

echo "copy icons"
cp -r "$prefix"/share/icons "$setup_dir"/share/

echo "copy glib shared"
cp -r "$prefix"/share/glib-2.0 "$setup_dir"/share/

echo "copy poppler shared"
cp -r "$prefix"/share/poppler "$setup_dir"/share/

echo "copy font configuration and included rules"
# libfontconfig resolves ../etc/fonts relative to its DLL on Windows. Preserve
# the package configuration and materialize any conf.d links in the app stage.
mkdir -p "$setup_dir/etc" "$setup_dir/share/xml"
cp -Lr "$prefix/etc/fonts" "$setup_dir/etc/"
cp -Lr "$prefix/share/fontconfig" "$setup_dir/share/"
cp -Lr "$prefix/share/xml/fontconfig" "$setup_dir/share/xml/"

echo "copy gspawn-win64-helper"
cp "$prefix"/bin/gspawn-win64-helper{,-console}.exe "$setup_dir"/bin/

echo "copy gdbus"
cp "$prefix"/bin/gdbus.exe "$setup_dir"/bin

# LuaGObject, plugin resources, audio and GTK demo programs are deliberately omitted.

echo "copy qpdf"
cp "$prefix"/bin/libqpdf*.dll "$setup_dir"/bin

echo "record package and copied-file provenance"
mkdir -p "$setup_dir/share/inkquay/licenses"
cp "$script_dir/../LICENSE" "$script_dir/../AUTHORS" "$script_dir/../debian/copyright" "$script_dir/../copyright.txt" "$script_dir/../Release/THIRD-PARTY-NOTICES.txt" "$setup_dir/share/inkquay/licenses/"
# Include package-provided notice directories; the final distribution inventory remains a release gate.
if [[ -d "$prefix/share/licenses" ]]; then cp -r "$prefix/share/licenses" "$setup_dir/share/inkquay/licenses/msys2"; fi
python "$script_dir/../script/inventoryWindows.py" "$setup_dir" "$prefix" "$build_dir/inkquay-windows-inventory.json" "$build_dir/inkquay.exe"

# Root's MSIX pipeline consumes dist. NSIS is an explicit local packaging option.
if [[ "${INKQUAY_BUILD_NSIS:-0}" == 1 ]]; then
    version=$(sed -n '1p' "$build_dir/VERSION")
    "/c/Program Files (x86)/NSIS/Bin/makensis.exe" -NOCD -DXOURNALPP_VERSION="$version" -DSETUP_DIR="$setup_dir" -DOUTPUT_INSTALLER_FILE="$build_dir/$installer_name" -DSCRIPT_DIR="$script_dir" "$script_dir/xournalpp.nsi"
fi
echo "InkQuay Windows stage ready for independent runtime and package qualification"
