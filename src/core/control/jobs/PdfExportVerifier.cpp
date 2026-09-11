// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include "PdfExportVerifier.h"

#include <array>
#include <cmath>
#include <fstream>
#include <optional>
#include <sstream>
#include <stdexcept>

#include <glib.h>
#include <glib/gstdio.h>

#include "model/Document.h"
#include "model/XojPage.h"
#include "pdf/base/XojPdfDocument.h"
#include "util/PathUtil.h"
namespace {
std::string uuid() {
    gchar* value = g_uuid_string_random();
    std::string result(value);
    g_free(value);
    return result;
}
std::string sha256(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file || !fs::is_regular_file(path))
        throw std::runtime_error("Cannot read protected file: " + path.string());
    auto* checksum = g_checksum_new(G_CHECKSUM_SHA256);
    std::array<char, 65536> block;
    while (file) {
        file.read(block.data(), block.size());
        g_checksum_update(checksum, reinterpret_cast<const guchar*>(block.data()), file.gcount());
    }
    if (!file.eof()) {
        g_checksum_free(checksum);
        throw std::runtime_error("File read failed: " + path.string());
    }
    std::string result(g_checksum_get_string(checksum));
    g_checksum_free(checksum);
    return result;
}
void checkProtected(const PdfExportExpectation& expected) {
    for (const auto& [path, hash]: expected.protectedFiles)
        if (sha256(path) != hash)
            throw std::runtime_error("Protected source/background changed: " + path.string());
}
const char* statusName(PdfExportVerification::Status status) {
    switch (status) {
        case PdfExportVerification::Status::Passed:
            return "passed";
        case PdfExportVerification::Status::Warning:
            return "warning";
        case PdfExportVerification::Status::Cancelled:
            return "cancelled";
        default:
            return "failed";
    }
}
}  // namespace
PdfExportExpectation PdfExportVerifier::capture(size_t pages, fs::path source, fs::path background) {
    PdfExportExpectation expected{pages, std::move(source), std::move(background), {}};
    for (const auto& path: {expected.sourceDocument, expected.backgroundPdf})
        if (!path.empty() && fs::exists(path))
            expected.protectedFiles.emplace(path, sha256(path));
    return expected;
}
void PdfExportVerifier::protectOutput(const fs::path& output, const PdfExportExpectation& expected) {
    for (const auto& path: {expected.sourceDocument, expected.backgroundPdf}) {
        if (path.empty())
            continue;
        if (fs::weakly_canonical(output) == fs::weakly_canonical(path) ||
            (fs::exists(output) && fs::exists(path) && fs::equivalent(output, path)))
            throw std::runtime_error("Export destination would replace the source document or background PDF");
    }
}
PdfExportVerification PdfExportVerifier::verify(const fs::path& output, const PdfExportExpectation& expected) {
    PdfExportVerification result;
    result.expectedPages = expected.pageCount;
    result.output = output;
    try {
        protectOutput(output, expected);
        checkProtected(expected);
        if (!fs::is_regular_file(output) || (result.outputBytes = fs::file_size(output)) == 0)
            throw std::runtime_error("PDF export produced no readable bytes");
        XojPdfDocument document;
        GError* error = nullptr;
        if (!document.load(output, "", &error)) {
            std::string message = error ? error->message : "Cannot reopen exported PDF";
            if (error)
                g_error_free(error);
            throw std::runtime_error(message);
        }
        result.actualPages = document.getPageCount();
        if (result.actualPages != expected.pageCount || result.actualPages == 0)
            throw std::runtime_error("Exported PDF page count does not match the requested document");
        for (size_t i = 0; i < result.actualPages; ++i) {
            auto page = document.getPage(i);
            if (!page || !std::isfinite(page->getWidth()) || !std::isfinite(page->getHeight()) ||
                page->getWidth() <= 0 || page->getHeight() <= 0)
                throw std::runtime_error("Exported PDF contains an invalid page size");
        }
        result.status = PdfExportVerification::Status::Passed;
        result.warnings.emplace_back("Checks cover PDF structure, page count, positive page sizes and unchanged "
                                     "protected files; visual fidelity and accessibility were not checked.");
        if ((!expected.sourceDocument.empty() && !expected.protectedFiles.contains(expected.sourceDocument)) ||
            (!expected.backgroundPdf.empty() && !expected.protectedFiles.contains(expected.backgroundPdf))) {
            result.status = PdfExportVerification::Status::Warning;
            result.warnings.emplace_back("A source/background path was not present on disk at export start; its bytes "
                                         "could not be verified.");
        }
    } catch (const std::exception& error) {
        result.error = error.what();
        result.status = PdfExportVerification::Status::Failed;
    }
    return result;
}
std::string PdfExportVerifier::jsonString(const std::string& value) {
    std::string result = "\"";
    const char* digits = "0123456789abcdef";
    for (unsigned char c: value) {
        switch (c) {
            case '"':
                result += "\\\"";
                break;
            case '\\':
                result += "\\\\";
                break;
            case '\n':
                result += "\\n";
                break;
            case '\r':
                result += "\\r";
                break;
            case '\t':
                result += "\\t";
                break;
            default:
                if (c < 32) {
                    result += "\\u00";
                    result += digits[c >> 4];
                    result += digits[c & 15];
                } else
                    result += static_cast<char>(c);
        }
    }
    return result + '"';
}
void PdfExportVerifier::writeReportAtomic(const fs::path& path, const PdfExportVerification& result,
                                          const PdfExportExpectation& expected) {
    auto quotedPath = [](const fs::path& p) {
        auto utf8 = p.u8string();
        return jsonString(std::string(utf8.begin(), utf8.end()));
    };
    std::ostringstream json;
    json << "{\n  \"version\": 1,\n  \"status\": " << jsonString(statusName(result.status))
         << ",\n  \"output\": " << quotedPath(result.output) << ",\n  \"expectedPages\": " << result.expectedPages
         << ",\n  \"actualPages\": " << result.actualPages << ",\n  \"outputBytes\": " << result.outputBytes
         << ",\n  \"error\": " << jsonString(result.error) << ",\n  \"warnings\": [";
    for (size_t i = 0; i < result.warnings.size(); ++i) {
        if (i)
            json << ',';
        json << jsonString(result.warnings[i]);
    }
    json << "],\n  \"protectedFiles\": [";
    bool first = true;
    for (const auto& [file, hash]: expected.protectedFiles) {
        if (!first)
            json << ',';
        first = false;
        json << "{\"path\":" << quotedPath(file) << ",\"sha256Before\":" << jsonString(hash) << '}';
    }
    json << "],\n  \"recoveryFiles\": [";
    for (size_t i = 0; i < result.recoveryFiles.size(); ++i) {
        if (i)
            json << ',';
        json << quotedPath(result.recoveryFiles[i]);
    }
    json << "],\n  \"published\": " << (result.published ? "true" : "false") << "\n}\n";
    fs::path temp = path;
    temp += ".tmp-" + uuid();
    try {
        GError* error = nullptr;
        auto bytes = json.str();
        if (!g_file_set_contents_full(Util::toGFilename(temp).c_str(), bytes.data(), static_cast<gssize>(bytes.size()),
                                      G_FILE_SET_CONTENTS_DURABLE, 0600, &error)) {
            std::string message(error->message);
            g_error_free(error);
            throw std::runtime_error(message);
        }
        fs::create_hard_link(temp, path);
        fs::remove(temp);
    } catch (...) {
        std::error_code ignored;
        fs::remove(temp, ignored);
        throw;
    }
}
PdfExportVerification PdfExportVerifier::exportChecked(const fs::path& output, const PdfExportExpectation& expected,
                                                       const std::function<void(const fs::path&)>& exporter,
                                                       const std::function<bool()>& cancelled) {
    // CLI/new-file callers never implicitly approve a current destination.
    return exportChecked(xoj::ExportDestination{fs::absolute(output), std::nullopt, false}, expected, exporter,
                         cancelled);
}
PdfExportVerification PdfExportVerifier::exportChecked(const xoj::ExportDestination& destination,
                                                       const PdfExportExpectation& expected,
                                                       const std::function<void(const fs::path&)>& exporter,
                                                       const std::function<bool()>& cancelled) {
    const auto& output = destination.path;
    PdfExportVerification result;
    result.output = output;
    result.expectedPages = expected.pageCount;
    fs::path directory, staged, displaced;
    bool displacedTarget = false;
    try {
        protectOutput(output, expected);
        checkProtected(expected);
        destination.validateCurrent();
        if (cancelled()) {
            result.status = PdfExportVerification::Status::Cancelled;
            result.error = "PDF export cancelled before writing";
        } else {
            directory = output.parent_path() / (".inkquay-export-" + uuid());
            if (!fs::create_directory(directory))
                throw std::runtime_error("Cannot create PDF export staging directory");
            staged = directory / "export.pdf";
            exporter(staged);
            result = verify(staged, expected);
            if (cancelled()) {
                result.status = PdfExportVerification::Status::Cancelled;
                result.error = "PDF export cancelled; original destination retained";
            }
            if (result.status == PdfExportVerification::Status::Passed ||
                result.status == PdfExportVerification::Status::Warning) {
                protectOutput(output, expected);
                checkProtected(expected);
                destination.validateCurrent();
                if (destination.existing) {
                    // Move the actual named target aside without replacing anything. Validate
                    // that moved file against chooser-time consent before publishing new bytes.
                    displaced = directory / "previous-output.pdf";
                    xoj::moveExportFileNoReplace(output, displaced);
                    displacedTarget = true;
                    if (xoj::inspectExportFile(displaced) != *destination.existing)
                        throw std::runtime_error("The approved destination was replaced before publication");
                    if (cancelled()) {
                        result.status = PdfExportVerification::Status::Cancelled;
                        throw std::runtime_error("PDF export cancelled before publication");
                    }
                }
                fs::create_hard_link(staged, output);  // Atomic no-replace, including a late competing owner.
                result.output = output;
                result.published = true;
                std::error_code cleanupError;
                fs::remove(staged, cleanupError);
                if (!cleanupError && displaced.empty())
                    fs::remove(directory, cleanupError);
                if (cleanupError) {
                    result.status = PdfExportVerification::Status::Warning;
                    result.warnings.emplace_back(
                            "PDF published, but its empty staging directory could not be removed.");
                }
            }
        }
    } catch (const std::exception& error) {
        if (result.status != PdfExportVerification::Status::Cancelled)
            result.status = PdfExportVerification::Status::Failed;
        result.error = error.what();
        if (displacedTarget) {
            try {
                xoj::moveExportFileNoReplace(displaced, output);
                displacedTarget = false;
            } catch (const std::exception& restoreError) {
                result.warnings.emplace_back(
                        std::string("Previous destination could not be restored without replacing another file: ") +
                        restoreError.what());
            }
        }
    }
    if (displacedTarget) {
        result.recoveryFiles.push_back(displaced);
        result.warnings.emplace_back("Previous destination retained for recovery: " + displaced.string());
    }
    if (!result.published && !staged.empty() && fs::exists(staged)) {
        result.output = staged;
        result.warnings.emplace_back("Unpublished export retained at the reported output path for diagnosis.");
    } else if (!directory.empty()) {
        std::error_code ignored;
        fs::remove(directory, ignored);
    }
    auto report = output;
    report += "." + uuid() + ".inkquay-report.json";
    try {
        writeReportAtomic(report, result, expected);
        result.report = report;
    } catch (const std::exception& error) {
        result.warnings.emplace_back(std::string("Report could not be saved: ") + error.what());
        if (result.status == PdfExportVerification::Status::Passed)
            result.status = PdfExportVerification::Status::Warning;
    }
    return result;
}

PdfExportExpectation PdfExportVerifier::captureForDocument(const Document& document, const PageRangeVector& range,
                                                           bool progressive) {
    size_t count = 0;
    for (const auto& part: range) {
        if (part.first > part.last || part.last >= document.getPageCount())
            throw std::runtime_error("Invalid PDF export page range");
        for (size_t i = part.first; i <= part.last; ++i)
            count += progressive ? document.getPage(i)->getLayers().size() : 1;
    }
    return capture(count, document.getFilepath(), document.getPdfFilepath());
}
