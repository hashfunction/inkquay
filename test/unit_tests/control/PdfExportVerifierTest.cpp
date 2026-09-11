// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include <fstream>

#include <cairo-pdf.h>
#include <glib.h>
#include <gtest/gtest.h>

#include "control/jobs/PdfExportVerifier.h"
class PdfExportVerifierTest: public ::testing::Test {
protected:
    fs::path dir;
    void SetUp() override {
        char* p = g_dir_make_tmp("inkquay-pdf-XXXXXX", nullptr);
        dir = p;
        g_free(p);
        std::ofstream(dir / "source.xopp") << "original source";
        pdf(dir / "background.pdf", 3);
    }
    void TearDown() override { fs::remove_all(dir); }
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
    auto second = PdfExportVerifier::exportChecked(
            first.output, expectation(), [&](const fs::path& p) { pdf(p, 3); }, [] { return false; }, true);
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
    fs::create_directory_symlink(dir, dir / "directory");
    EXPECT_EQ(PdfExportVerifier::exportChecked(dir / "directory" / "background.pdf", expected, writer).status,
              PdfExportVerification::Status::Failed);
    EXPECT_FALSE(called);
}
TEST_F(PdfExportVerifierTest, PreservesExistingOutputOnFailureCancellationAndTargetRace) {
    auto out = dir / "out.pdf";
    std::ofstream(out) << "old";
    auto failed = PdfExportVerifier::exportChecked(
            out, expectation(), [](const fs::path&) { throw std::runtime_error("writer failed"); },
            [] { return false; }, true);
    EXPECT_EQ(failed.status, PdfExportVerification::Status::Failed);
    auto cancelled = PdfExportVerifier::exportChecked(
            out, expectation(), [&](const fs::path& p) { pdf(p, 3); }, [] { return true; }, true);
    EXPECT_EQ(cancelled.status, PdfExportVerification::Status::Cancelled);
    auto race = PdfExportVerifier::exportChecked(
            out, expectation(),
            [&](const fs::path& p) {
                pdf(p, 3);
                std::ofstream(out) << "other writer";
            },
            [] { return false; }, true);
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
