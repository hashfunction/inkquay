#include "PdfExportJob.h"

#include <memory>  // for unique_ptr, allocator
#include <shared_mutex>
#include <stdexcept>
#include <string>   // for string
#include <utility>  // for move

#include "control/Control.h"               // for Control
#include "control/jobs/BaseExportJob.h"    // for BaseExportJob
#include "model/Document.h"                // for Document
#include "pdf/base/XojPdfExport.h"         // for XojPdfExport
#include "pdf/base/XojPdfExportFactory.h"  // for XojPdfExportFactory
#include "util/PathUtil.h"                 // for clearExtensions
#include "util/i18n.h"                     // for _

PdfExportJob::PdfExportJob(Control* control): BaseExportJob(control, _("PDF Export")) {}

PdfExportJob::~PdfExportJob() = default;

void PdfExportJob::addFilterToDialog(GtkFileChooser* dialog) {
    addFileFilterToDialog(dialog, _("PDF files"), "application/pdf");
}

void PdfExportJob::setExtensionFromFilter(fs::path& file, const char* /*filterName*/) const {
    // Remove any pre-existing extension and adds .pdf
    Util::clearExtensions(file, ".pdf");
    file += ".pdf";
}

void PdfExportJob::run() {
    try {
        Document* doc = control->getDocument();
        std::shared_lock lock(*doc);
        auto expected = PdfExportVerifier::capture(doc->getPageCount(), doc->getFilepath(), doc->getPdfFilepath());
        std::unique_ptr<XojPdfExport> pdfe = XojPdfExportFactory::createExport(doc, control);
        lock.unlock();
        pdfVerification =
                PdfExportVerifier::exportChecked(exportDestination.value(), expected, [&](const fs::path& staged) {
                    if (!pdfe->createPdf(staged, false))
                        throw std::runtime_error(pdfe->getLastError());
                });
    } catch (const std::exception& error) {
        errorMsg = error.what();
    }
    callAfterRun();
}
