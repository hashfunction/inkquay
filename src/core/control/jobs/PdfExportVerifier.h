// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#pragma once
#include <functional>
#include <map>
#include <string>
#include <vector>

#include "util/ElementRange.h"
#include "util/ExportDestination.h"

#include "filesystem.h"
class Document;
struct PdfExportExpectation {
    size_t pageCount = 0;
    fs::path sourceDocument, backgroundPdf;
    std::map<fs::path, std::string> protectedFiles;
};
struct PdfExportVerification {
    enum class Status { Passed, Warning, Failed, Cancelled };
    Status status = Status::Failed;
    size_t expectedPages = 0, actualPages = 0;
    uintmax_t outputBytes = 0;
    bool published = false;
    fs::path output, report;
    std::vector<fs::path> recoveryFiles;
    std::vector<std::string> warnings;
    std::string error;
};
class PdfExportVerifier {
public:
    static PdfExportExpectation captureForDocument(const Document& document, const PageRangeVector& range,
                                                   bool progressive);
    static PdfExportExpectation capture(size_t pages, fs::path source, fs::path background);
    static void protectOutput(const fs::path& output, const PdfExportExpectation& expected);
    static PdfExportVerification verify(const fs::path& output, const PdfExportExpectation& expected);
    static PdfExportVerification exportChecked(
            const fs::path& output, const PdfExportExpectation& expected,
            const std::function<void(const fs::path&)>& exporter,
            const std::function<bool()>& cancelled = [] { return false; });
    static PdfExportVerification exportChecked(
            const xoj::ExportDestination& destination, const PdfExportExpectation& expected,
            const std::function<void(const fs::path&)>& exporter,
            const std::function<bool()>& cancelled = [] { return false; });
    static void writeReportAtomic(const fs::path& path, const PdfExportVerification& result,
                                  const PdfExportExpectation& expected);
    static std::string jsonString(const std::string& value);
};
