// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include "util/ExportDestination.h"

#include <array>
#include <cerrno>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <system_error>

#include <glib.h>
#include <glib/gstdio.h>

#include "util/PathUtil.h"
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#include <windows.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#ifdef __linux__
#include <fcntl.h>
#include <sys/syscall.h>
#endif
#endif
namespace {
struct Stamp {
    uint64_t device, inode, bytes, modified;
    bool operator==(const Stamp&) const = default;
};
Stamp stamp(FILE* file) {
#ifdef _WIN32
    BY_HANDLE_FILE_INFORMATION info{};
    if (!GetFileInformationByHandle(reinterpret_cast<HANDLE>(_get_osfhandle(_fileno(file))), &info))
        throw std::system_error(GetLastError(), std::system_category(), "Cannot inspect export target handle");
    if (info.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))
        throw std::runtime_error("Export target must be a regular file");
    return {info.dwVolumeSerialNumber, (uint64_t(info.nFileIndexHigh) << 32) | info.nFileIndexLow,
            (uint64_t(info.nFileSizeHigh) << 32) | info.nFileSizeLow,
            (uint64_t(info.ftLastWriteTime.dwHighDateTime) << 32) | info.ftLastWriteTime.dwLowDateTime};
#else
    struct stat info{};
    if (fstat(fileno(file), &info) != 0)
        throw std::system_error(errno, std::generic_category());
    if (!S_ISREG(info.st_mode))
        throw std::runtime_error("Export target must be a regular file");
#ifdef __APPLE__
    auto time = info.st_mtimespec;
#else
    auto time = info.st_mtim;
#endif
    return {uint64_t(info.st_dev), uint64_t(info.st_ino), uint64_t(info.st_size),
            uint64_t(time.tv_sec) * 1000000000 + uint64_t(time.tv_nsec)};
#endif
}
fs::file_type exportPathType(const fs::path& path) {
#ifdef _WIN32
    // MinGW does not reliably expose native reparse points via symlink_status.
    const auto attributes = GetFileAttributesW(path.c_str());
    if (attributes == INVALID_FILE_ATTRIBUTES) {
        const auto error = GetLastError();
        if (error == ERROR_FILE_NOT_FOUND || error == ERROR_PATH_NOT_FOUND)
            return fs::file_type::not_found;
        throw std::system_error(error, std::system_category(), "Cannot inspect export path");
    }
    if (attributes & FILE_ATTRIBUTE_REPARSE_POINT)
        return fs::file_type::symlink;
    return attributes & FILE_ATTRIBUTE_DIRECTORY ? fs::file_type::directory : fs::file_type::regular;
#else
    return fs::symlink_status(path).type();
#endif
}
void regularPath(const fs::path& path) {
    if (exportPathType(path) != fs::file_type::regular)
        throw std::runtime_error("Export target is not a regular file or is a symbolic link");
}
using File = std::unique_ptr<FILE, decltype(&fclose)>;
File openFile(const fs::path& path) {
    regularPath(path);
#ifdef _WIN32
    // Inspect the leaf itself even if a link is substituted after regularPath.
    const auto handle = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                    nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (handle == INVALID_HANDLE_VALUE)
        throw std::system_error(GetLastError(), std::system_category(), "Cannot open selected export target");
    const auto descriptor = _open_osfhandle(reinterpret_cast<intptr_t>(handle), _O_RDONLY | _O_BINARY);
    if (descriptor == -1) {
        const auto error = errno;
        CloseHandle(handle);
        throw std::system_error(error, std::generic_category(), "Cannot read selected export target handle");
    }
    File file(_fdopen(descriptor, "rb"), fclose);
    if (!file) {
        const auto error = errno;
        _close(descriptor);
        throw std::system_error(error, std::generic_category(), "Cannot read selected export target stream");
    }
#else
    File file(g_fopen(Util::toGFilename(path).c_str(), "rb"), fclose);
    if (!file)
        throw std::system_error(errno, std::generic_category(), "Cannot read selected export target");
#endif
    return file;
}
}  // namespace
xoj::ExportFileIdentity xoj::inspectExportFile(const fs::path& path) {
    auto file = openFile(path);
    const auto before = stamp(file.get());
    auto checksum =
            std::unique_ptr<GChecksum, decltype(&g_checksum_free)>(g_checksum_new(G_CHECKSUM_SHA256), g_checksum_free);
    std::array<unsigned char, 65536> block{};
    while (const auto count = fread(block.data(), 1, block.size(), file.get()))
        g_checksum_update(checksum.get(), block.data(), static_cast<gssize>(count));
    if (ferror(file.get()) || before != stamp(file.get()))
        throw std::runtime_error("Export target changed during inspection");
    auto named = openFile(path);
    if (before != stamp(named.get()))
        throw std::runtime_error("Export target was replaced during inspection");
    return {before.device, before.inode, before.bytes, g_checksum_get_string(checksum.get())};
}
xoj::ExportDestination xoj::ExportDestination::capture(const fs::path& path) {
    ExportDestination selection{fs::absolute(path), std::nullopt, false};
    if (exportPathType(selection.path) != fs::file_type::not_found)
        selection.existing = inspectExportFile(selection.path);
    return selection;
}
void xoj::ExportDestination::validateCurrent() const {
    if (existing) {
        if (!overwriteConfirmed)
            throw std::runtime_error("Replacement was not confirmed for the selected file");
        if (inspectExportFile(path) != *existing)
            throw std::runtime_error("The confirmed export target changed; choose the destination again");
    } else if (exportPathType(path) != fs::file_type::not_found) {
        throw std::runtime_error("The selected new filename is now occupied; its file was retained");
    }
}
void xoj::moveExportFileNoReplace(const fs::path& source, const fs::path& destination) {
#ifdef _WIN32
    if (!MoveFileExW(source.c_str(), destination.c_str(), MOVEFILE_WRITE_THROUGH))
        throw std::system_error(GetLastError(), std::system_category(), "Cannot move export file without replacement");
#elif defined(__APPLE__)
    if (renamex_np(source.c_str(), destination.c_str(), RENAME_EXCL) != 0)
        throw std::system_error(errno, std::generic_category(), "Cannot move export file without replacement");
#elif defined(__linux__) && defined(SYS_renameat2)
    if (syscall(SYS_renameat2, AT_FDCWD, source.c_str(), AT_FDCWD, destination.c_str(), 1 /* RENAME_NOREPLACE */) != 0)
        throw std::system_error(errno, std::generic_category(), "Cannot move export file without replacement");
#else
    throw std::runtime_error("Atomic no-replace file move is unavailable on this platform");
#endif
}
