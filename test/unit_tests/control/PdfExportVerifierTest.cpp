// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include <fstream>
#include <utility>
#include <vector>

#include <cairo-pdf.h>
#include <glib.h>
#include <gtest/gtest.h>

#include "control/jobs/PdfExportVerifier.h"

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif
#include <system_error>

// MinGW's std::filesystem does not implement link creation. Exercise real Windows
// links through the native API; missing host privileges are a test failure.
static void createNativeTestSymlink(const fs::path& target, const fs::path& link, bool directory = false) {
#ifdef _WIN32
    const DWORD flags = directory ? SYMBOLIC_LINK_FLAG_DIRECTORY : 0;
    if (!CreateSymbolicLinkW(link.c_str(), target.c_str(), flags | 0x2)) {
        if (!CreateSymbolicLinkW(link.c_str(), target.c_str(), flags)) {
            throw std::system_error(GetLastError(), std::system_category(), "CreateSymbolicLinkW test fixture");
        }
    }
#else
    if (directory) {
        fs::create_directory_symlink(target, link);
    } else {
        fs::create_symlink(target, link);
    }
#endif
}
class PdfExportVerifierTest: public ::testing::Test {
protected:
    fs::path dir;
    std::vector<std::pair<fs::path, bool>> fixtureLinks;
    void createTestSymlink(const fs::path& target, const fs::path& link, bool directory = false) {
        createNativeTestSymlink(target, link, directory);
        fixtureLinks.emplace_back(link, directory);
    }
    void SetUp() override {
        char* p = g_dir_make_tmp("inkquay-pdf-XXXXXX", nullptr);
        dir = p;
        g_free(p);
        std::ofstream(dir / "source.xopp") << "original source";
        pdf(dir / "background.pdf", 3);
    }
    void TearDown() override {
        // MinGW's filesystem can classify a directory symlink as a directory and
        // recursively follow it. Remove our exact fixture links without traversal.
        for (const auto& [link, directory]: fixtureLinks) {
#ifdef _WIN32
            const bool removed = directory ? RemoveDirectoryW(link.c_str()) : DeleteFileW(link.c_str());
            ASSERT_TRUE(removed) << "Cannot remove fixture link: " << GetLastError();
#else
            ASSERT_TRUE(fs::remove(link));
#endif
        }
        fs::remove_all(dir);
    }
    void pdf(const fs::path& path, int pages) {
        auto* surface = cairo_pdf_surface_create(path.string().c_str(), 600, 800);
        auto* cr = cairo_create(surface);
        for (int i = 0; i < pages; ++i) {
            cairo_move_to(cr, 20, 20);
            cairo_line_to(cr, 100, 100);
            cairo_stroke(cr);
            cairo_show_page(cr);
        }
        cairo_destroy(cr);
        cairo_surface_destroy(surface);
    }
    std::string read(const fs::path& path) {
        std::ifstream file(path, std::ios::binary);
        return {std::istreambuf_iterator<char>(file), {}};
    }
    xoj::ExportDestination approved(const fs::path& path) {
        auto destination = xoj::ExportDestination::capture(path);
        destination.overwriteConfirmed = true;
        return destination;
    }
    PdfExportExpectation expectation() {
        return PdfExportVerifier::capture(3, dir / "source.xopp", dir / "background.pdf");
    }
};
TEST_F(PdfExportVerifierTest, DetectsTruncatedPageSetAndRetainsFaultyOutput) {
    auto expected = expectation();
    auto result =
            PdfExportVerifier::exportChecked(dir / "export.pdf", expected, [&](const fs::path& path) { pdf(path, 2); });
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_EQ(result.expectedPages, 3U);
    EXPECT_EQ(result.actualPages, 2U);
    EXPECT_TRUE(fs::is_regular_file(result.output));
    EXPECT_TRUE(fs::is_regular_file(result.report));
    EXPECT_EQ(PdfExportVerifier::capture(3, dir / "source.xopp", dir / "background.pdf").protectedFiles,
              expected.protectedFiles);
}
TEST_F(PdfExportVerifierTest, ChecksRealPdfAndCreatesDistinctReports) {
    auto first = PdfExportVerifier::exportChecked(dir / "Réunion 方格.pdf", expectation(),
                                                  [&](const fs::path& p) { pdf(p, 3); });
    EXPECT_EQ(first.status, PdfExportVerification::Status::Passed);
    EXPECT_EQ(first.actualPages, 3U);
    EXPECT_GT(first.outputBytes, 0U);
    auto second = PdfExportVerifier::exportChecked(approved(first.output), expectation(),
                                                   [&](const fs::path& p) { pdf(p, 3); });
    EXPECT_EQ(second.status, PdfExportVerification::Status::Passed);
    EXPECT_NE(first.report, second.report);
}
TEST_F(PdfExportVerifierTest, RejectsSourceHardlinkAndAncestorAliasBeforeCallingExporter) {
    auto expected = expectation();
    auto alias = dir / "alias.pdf";
    fs::create_hard_link(dir / "background.pdf", alias);
    bool called = false;
    auto writer = [&](const fs::path&) { called = true; };
    EXPECT_EQ(PdfExportVerifier::exportChecked(alias, expected, writer).status, PdfExportVerification::Status::Failed);
    EXPECT_FALSE(called);
    createTestSymlink(dir, dir / "directory", true);
    EXPECT_EQ(PdfExportVerifier::exportChecked(dir / "directory" / "background.pdf", expected, writer).status,
              PdfExportVerification::Status::Failed);
    EXPECT_FALSE(called);
}
TEST_F(PdfExportVerifierTest, PreservesExistingOutputOnFailureCancellationAndTargetRace) {
    auto out = dir / "out.pdf";
    std::ofstream(out) << "old";
    auto failed = PdfExportVerifier::exportChecked(
            approved(out), expectation(), [](const fs::path&) { throw std::runtime_error("writer failed"); },
            [] { return false; });
    EXPECT_EQ(failed.status, PdfExportVerification::Status::Failed);
    auto cancelled = PdfExportVerifier::exportChecked(
            approved(out), expectation(), [&](const fs::path& p) { pdf(p, 3); }, [] { return true; });
    EXPECT_EQ(cancelled.status, PdfExportVerification::Status::Cancelled);
    auto race = PdfExportVerifier::exportChecked(
            approved(out), expectation(),
            [&](const fs::path& p) {
                pdf(p, 3);
                std::ofstream(out) << "other writer";
            },
            [] { return false; });
    EXPECT_EQ(race.status, PdfExportVerification::Status::Failed);
    std::ifstream f(out);
    std::string contents((std::istreambuf_iterator<char>(f)), {});
    EXPECT_EQ(contents, "other writer");
}
TEST_F(PdfExportVerifierTest, RejectsEmptyInvalidAndChangedProtectedFiles) {
    auto expected = expectation();
    auto out = dir / "empty.pdf";
    { std::ofstream empty(out); }
    EXPECT_EQ(PdfExportVerifier::verify(out, expected).status, PdfExportVerification::Status::Failed);
    std::ofstream(out) << "not PDF";
    EXPECT_EQ(PdfExportVerifier::verify(out, expected).status, PdfExportVerification::Status::Failed);
    pdf(out, 3);
    std::ofstream(dir / "source.xopp") << "changed";
    EXPECT_EQ(PdfExportVerifier::verify(out, expected).status, PdfExportVerification::Status::Failed);
}
TEST_F(PdfExportVerifierTest, EscapesJsonControlCharactersAndUnicode) {
    EXPECT_EQ(PdfExportVerifier::jsonString("é\"\\\n\t\x01"), "\"é\\\"\\\\\\n\\t\\u0001\"");
}

#include "control/ExportHelper.h"
#include "model/Document.h"
#include "model/DocumentHandler.h"
#include "model/XojPage.h"
#include "pdf/base/XojPdfExport.h"
#include "pdf/base/XojPdfExportFactory.h"
TEST_F(PdfExportVerifierTest, UsesRealDocumentExportBackendAndRangeCounts) {
    DocumentHandler handler;
    Document document(&handler);
    document.setFilepath(dir / "source.xopp");
    for (int i = 0; i < 3; ++i) document.addPage(std::make_shared<XojPage>(600, 800));
    auto backend = XojPdfExportFactory::createExport(&document, nullptr);
    auto expected = PdfExportVerifier::captureForDocument(document, PageRangeVector{{0, 2}}, false);
    auto result = PdfExportVerifier::exportChecked(
            dir / "real-backend.pdf", expected, [&](const fs::path& p) { ASSERT_TRUE(backend->createPdf(p, false)); });
    EXPECT_EQ(result.status, PdfExportVerification::Status::Passed);
    EXPECT_EQ(result.actualPages, 3U);
    EXPECT_EQ(PdfExportVerifier::captureForDocument(document, PageRangeVector{{1, 2}}, false).pageCount, 2U);
    EXPECT_EQ(ExportHelper::exportPdf(&document, dir / "range.pdf", "2-3", nullptr, EXPORT_BACKGROUND_ALL, false,
                                      ExportBackend::DEFAULT),
              0);
    EXPECT_EQ(PdfExportVerifier::verify(dir / "range.pdf", PdfExportVerifier::capture(2, dir / "source.xopp", {}))
                      .actualPages,
              2U);
}
TEST_F(PdfExportVerifierTest, ExistingDestinationRequiresExplicitOverwriteAuthorization) {
    const auto output = dir / "existing.pdf";
    pdf(output, 1);
    const auto before = fs::file_size(output);
    bool called = false;
    auto result = PdfExportVerifier::exportChecked(output, expectation(), [&](const fs::path& p) {
        called = true;
        pdf(p, 3);
    });
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_FALSE(called);
    EXPECT_EQ(fs::file_size(output), before);
}

#include "model/Layer.h"
TEST_F(PdfExportVerifierTest, ChecksQpdfBackgroundAndProgressiveLayerExports) {
    DocumentHandler handler;
    Document document(&handler);
    document.setFilepath(dir / "source.xopp");
    ASSERT_TRUE(document.readPdf(dir / "background.pdf", true, false));
    auto before = expectation();
    ASSERT_EQ(ExportHelper::exportPdf(&document, dir / "background-export.pdf", "2-3", nullptr, EXPORT_BACKGROUND_ALL,
                                      false, ExportBackend::QPDF),
              0);
    EXPECT_EQ(PdfExportVerifier::verify(dir / "background-export.pdf",
                                        PdfExportVerifier::capture(2, dir / "source.xopp", dir / "background.pdf"))
                      .actualPages,
              2U);
    struct LayeredFixturePage: XojPage {
        LayeredFixturePage(): XojPage(600, 800) { addLayer(new Layer()); }
    };
    document.addPage(std::make_shared<LayeredFixturePage>());
    ASSERT_EQ(document.getPage(3)->getLayerCount(), 2U);
    EXPECT_EQ(PdfExportVerifier::captureForDocument(document, PageRangeVector{{3, 3}}, true).pageCount, 2U);
    ASSERT_EQ(ExportHelper::exportPdf(&document, dir / "progressive.pdf", "4", nullptr, EXPORT_BACKGROUND_ALL, true,
                                      ExportBackend::DEFAULT),
              0);
    EXPECT_EQ(PdfExportVerifier::verify(dir / "progressive.pdf",
                                        PdfExportVerifier::capture(2, dir / "source.xopp", dir / "background.pdf"))
                      .actualPages,
              2U);
    EXPECT_EQ(expectation().protectedFiles, before.protectedFiles);
}

TEST_F(PdfExportVerifierTest, GuiNewNameMustNotOverwriteFileCreatedBeforeWorkerStarts) {
    const auto output = dir / "new-name.pdf";
    ASSERT_FALSE(fs::exists(output));  // The chooser selected a new name.
    const auto destination = xoj::ExportDestination::capture(output);
    std::ofstream(output) << "late owner";
    auto result = PdfExportVerifier::exportChecked(destination, expectation(), [&](const fs::path& p) { pdf(p, 3); });
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_FALSE(result.published);
    std::ifstream file(output);
    EXPECT_EQ(std::string((std::istreambuf_iterator<char>(file)), {}), "late owner");
}
TEST_F(PdfExportVerifierTest, GuiApprovalMustNotAuthorizeReplacementBeforeWorkerStarts) {
    const auto output = dir / "approved.pdf";
    std::ofstream(output) << "approved owner";
    const auto destination = approved(output);
    // The user approved the file above, then a different file took its name.
    fs::remove(output);
    std::ofstream(output) << "unapproved replacement";
    auto result = PdfExportVerifier::exportChecked(destination, expectation(), [&](const fs::path& p) { pdf(p, 3); });
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_FALSE(result.published);
    std::ifstream file(output);
    EXPECT_EQ(std::string((std::istreambuf_iterator<char>(file)), {}), "unapproved replacement");
}

TEST_F(PdfExportVerifierTest, ConfirmedReplacementPublishesAndReportsRecoverableOriginal) {
    const auto output = dir / "confirmed.pdf";
    std::ofstream(output) << "approved original bytes";
    const auto destination = approved(output);
    const auto result =
            PdfExportVerifier::exportChecked(destination, expectation(), [&](const fs::path& p) { pdf(p, 3); });
    ASSERT_TRUE(result.published) << result.error;
    ASSERT_EQ(result.recoveryFiles.size(), 1U);
    EXPECT_EQ(read(result.recoveryFiles.front()), "approved original bytes");
    EXPECT_EQ(xoj::inspectExportFile(result.recoveryFiles.front()), *destination.existing);
    EXPECT_EQ(PdfExportVerifier::verify(output, expectation()).actualPages, 3U);
    EXPECT_NE(read(result.report).find("\"recoveryFiles\": ["), std::string::npos);
    const auto recoveryUtf8 = result.recoveryFiles.front().u8string();
    EXPECT_NE(read(result.report)
                      .find(PdfExportVerifier::jsonString(std::string(recoveryUtf8.begin(), recoveryUtf8.end()))),
              std::string::npos);
}

TEST_F(PdfExportVerifierTest, SameBytesOnAnotherFileDoNotInheritConsent) {
    const auto output = dir / "confirmed.pdf";
    std::ofstream(output) << "same contents";
    const auto destination = approved(output);
    // Keep the original inode alive, guaranteeing the replacement has a different identity.
    fs::rename(output, dir / "moved.pdf");
    std::ofstream(output) << "same contents";
    bool called = false;
    const auto result =
            PdfExportVerifier::exportChecked(destination, expectation(), [&](const fs::path&) { called = true; });
    EXPECT_FALSE(called);
    EXPECT_FALSE(result.published);
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_EQ(read(output), "same contents");
    EXPECT_EQ(read(dir / "moved.pdf"), "same contents");
}

TEST_F(PdfExportVerifierTest, InspectionWithoutConfirmationCannotReplace) {
    const auto output = dir / "unconfirmed.pdf";
    std::ofstream(output) << "owner";
    const auto destination = xoj::ExportDestination::capture(output);
    bool called = false;
    const auto result =
            PdfExportVerifier::exportChecked(destination, expectation(), [&](const fs::path&) { called = true; });
    EXPECT_FALSE(called);
    EXPECT_FALSE(result.published);
    EXPECT_EQ(read(output), "owner");
}

TEST_F(PdfExportVerifierTest, CancellationAfterDisplacementRestoresApprovedTarget) {
    const auto output = dir / "cancel.pdf";
    std::ofstream(output) << "approved original";
    int cancellationChecks = 0;
    const auto result = PdfExportVerifier::exportChecked(
            approved(output), expectation(), [&](const fs::path& p) { pdf(p, 3); },
            [&] { return ++cancellationChecks == 3; });
    EXPECT_EQ(cancellationChecks, 3);
    EXPECT_EQ(result.status, PdfExportVerification::Status::Cancelled);
    EXPECT_FALSE(result.published);
    EXPECT_EQ(read(output), "approved original");
    EXPECT_TRUE(result.recoveryFiles.empty());
    EXPECT_EQ(PdfExportVerifier::verify(result.output, expectation()).actualPages, 3U);
}

TEST_F(PdfExportVerifierTest, LateOwnerBlocksPublicationAndRollbackWithoutLosingEitherFile) {
    const auto output = dir / "collision.pdf";
    std::ofstream(output) << "approved original";
    int cancellationChecks = 0;
    const auto result = PdfExportVerifier::exportChecked(
            approved(output), expectation(), [&](const fs::path& p) { pdf(p, 3); },
            [&] {
                if (++cancellationChecks == 3) {
                    EXPECT_FALSE(fs::exists(output));  // The approved file has been displaced.
                    std::ofstream(output) << "late concurrent owner";
                }
                return false;
            });
    EXPECT_EQ(cancellationChecks, 3);
    EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
    EXPECT_FALSE(result.published);
    EXPECT_EQ(read(output), "late concurrent owner");
    ASSERT_EQ(result.recoveryFiles.size(), 1U);
    EXPECT_EQ(read(result.recoveryFiles.front()), "approved original");
    EXPECT_EQ(PdfExportVerifier::verify(result.output, expectation()).actualPages, 3U);
    EXPECT_NE(read(result.report).find("\"published\": false"), std::string::npos);
}

TEST_F(PdfExportVerifierTest, ConsentCannotOverrideSourceAndBackgroundProtection) {
    const auto expected = expectation();
    const auto alias = dir / "protected.pdf";
    fs::create_hard_link(dir / "background.pdf", alias);
    bool called = false;
    const auto writer = [&](const fs::path&) { called = true; };
    EXPECT_FALSE(PdfExportVerifier::exportChecked(approved(alias), expected, writer).published);
    EXPECT_FALSE(PdfExportVerifier::exportChecked(approved(dir / "source.xopp"), expected, writer).published);
    createTestSymlink(dir, dir / "ancestor", true);
    EXPECT_FALSE(PdfExportVerifier::exportChecked(approved(dir / "ancestor" / "background.pdf"), expected, writer)
                         .published);
    EXPECT_FALSE(called);
    EXPECT_EQ(expectation().protectedFiles, expected.protectedFiles);
}

TEST_F(PdfExportVerifierTest, NoReplaceMovePreservesOccupiedRecoveryAndDanglingLink) {
    const auto from = dir / "from", to = dir / "to";
    std::ofstream(from) << "from bytes";
    std::ofstream(to) << "to bytes";
    EXPECT_THROW(xoj::moveExportFileNoReplace(from, to), std::system_error);
    EXPECT_EQ(read(from), "from bytes");
    EXPECT_EQ(read(to), "to bytes");
    fs::remove(to);
    createTestSymlink(dir / "missing", to);
    EXPECT_THROW(xoj::moveExportFileNoReplace(from, to), std::system_error);
#ifdef _WIN32
    WIN32_FIND_DATAW info{};
    const auto handle = FindFirstFileW(to.c_str(), &info);
    ASSERT_NE(handle, INVALID_HANDLE_VALUE);
    FindClose(handle);
    EXPECT_TRUE(info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT);
    EXPECT_EQ(info.dwReserved0, IO_REPARSE_TAG_SYMLINK);
#else
    EXPECT_TRUE(fs::is_symlink(to));
#endif
    EXPECT_EQ(read(from), "from bytes");
    EXPECT_THROW(xoj::ExportDestination::capture(to), std::runtime_error);
}

TEST_F(PdfExportVerifierTest, RejectsExistingFileSymlinkWithoutFollowingItsTarget) {
    const auto link = dir / "linked.pdf";
    const auto target = dir / "real.pdf";
    std::ofstream(target) << "retained bytes";
    createTestSymlink(target, link);
    EXPECT_THROW(xoj::ExportDestination::capture(link), std::runtime_error);
    EXPECT_EQ(read(target), "retained bytes");
}
