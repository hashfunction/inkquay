// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#pragma once
#include <cstdint>
#include <optional>
#include <string>

#include "filesystem.h"

namespace xoj {
struct ExportFileIdentity {
    uint64_t device = 0, inode = 0, bytes = 0;
    std::string sha256;
    bool operator==(const ExportFileIdentity&) const = default;
};
// Captured before the replacement question; copied unchanged into the worker.
struct ExportDestination {
    fs::path path;
    std::optional<ExportFileIdentity> existing;
    bool overwriteConfirmed = false;
    static ExportDestination capture(const fs::path& path);
    void validateCurrent() const;
};
ExportFileIdentity inspectExportFile(const fs::path& path);
// Atomic same-volume rename that never replaces an occupied destination.
void moveExportFileNoReplace(const fs::path& source, const fs::path& destination);
}  // namespace xoj
