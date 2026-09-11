#include "ExportHelper.h"

#include <algorithm>  // for max
#include <memory>     // for unique_ptr, allocator
#include <string>     // for string

#include <gio/gio.h>  // for g_file_new_for_commandlin...
#include <glib.h>     // for g_message, g_error

#include "control/jobs/ImageExport.h"  // for ImageExport, EXPORT_GRAPH...
#include "control/jobs/PdfExportVerifier.h"
#include "control/jobs/ProgressListener.h"  // for DummyProgressListener
#include "model/Document.h"                 // for Document
#include "pdf/base/XojPdfExport.h"          // for XojPdfExport
#include "pdf/base/XojPdfExportFactory.h"   // for XojPdfExportFactory
#include "util/ElementRange.h"              // for parse, PageRangeVector
#include "util/i18n.h"                      // for _
#include "util/raii/GObjectSPtr.h"          // for GObjectSPtr

#include "filesystem.h"  // for operator==, path

namespace ExportHelper {

auto exportImg(Document* doc, fs::path output, const char* range, const char* layerRange, int pngDpi, int pngWidth,
               int pngHeight, ExportBackgroundType exportBackground) -> int {

    ExportGraphicsFormat format = EXPORT_GRAPHICS_PNG;

    if (output.extension() == ".svg") {
        format = EXPORT_GRAPHICS_SVG;
    }

    PageRangeVector exportRange;
    if (range) {
        exportRange = ElementRange::parse(range, doc->getPageCount());
    } else {
        exportRange.emplace_back(0, doc->getPageCount() - 1);
    }

    DummyProgressListener progress;

    ImageExport imgExport(doc, std::move(output), format, exportBackground, exportRange);

    if (format == EXPORT_GRAPHICS_PNG) {
        if (pngDpi > 0) {
            imgExport.setQualityParameter(EXPORT_QUALITY_DPI, pngDpi);
        } else if (pngWidth > 0) {
            imgExport.setQualityParameter(EXPORT_QUALITY_WIDTH, pngWidth);
        } else if (pngHeight > 0) {
            imgExport.setQualityParameter(EXPORT_QUALITY_HEIGHT, pngHeight);
        }
    }

    imgExport.setLayerRange(layerRange);

    imgExport.exportGraphics(&progress);

    std::string errorMsg = imgExport.getLastErrorMsg();
    if (!errorMsg.empty()) {
        g_message("Error exporting image: %s\n", errorMsg.c_str());
        return -3;
    }

    g_message("%s", _("Image file successfully created"));

    return 0;  // no error
}

auto exportPdf(Document* doc, const fs::path& output, const char* range, const char* layerRange,
               ExportBackgroundType exportBackground, bool progressiveMode, ExportBackend backend) -> int {
    std::unique_ptr<XojPdfExport> pdfe = XojPdfExportFactory::createExport(doc, nullptr, backend);
    pdfe->setExportBackground(exportBackground);

    try {
        if (doc->getPageCount() == 0)
            throw std::runtime_error("No pages to export");
        const PageRangeVector selected =
                range ? ElementRange::parse(range, doc->getPageCount()) : PageRangeVector{{0, doc->getPageCount() - 1}};
        const auto expected = PdfExportVerifier::captureForDocument(*doc, selected, progressiveMode);
        pdfe->setLayerRange(layerRange);
        auto result = PdfExportVerifier::exportChecked(output, expected, [&](const fs::path& staged) {
            if (!pdfe->createPdf(staged, selected, progressiveMode))
                throw std::runtime_error(pdfe->getLastError());
        });
        g_message("PDF checks: %zu/%zu pages. Output: %s. Report: %s", result.actualPages, result.expectedPages,
                  result.output.string().c_str(), result.report.string().c_str());
        for (const auto& warning: result.warnings) g_message("%s", warning.c_str());
        if (result.status == PdfExportVerification::Status::Failed ||
            result.status == PdfExportVerification::Status::Cancelled) {
            g_message("%s", result.error.c_str());
            return -3;
        }
    } catch (const std::exception& error) {
        g_message("%s", error.what());
        return -3;
    }

    return 0;  // no error
}

}  // namespace ExportHelper
