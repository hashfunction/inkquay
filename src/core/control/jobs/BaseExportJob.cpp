#include "BaseExportJob.h"

#include <utility>  // for move

#include <glib.h>  // for g_warning

#include "control/Control.h"            // for Control
#include "control/jobs/BlockingJob.h"   // for BlockingJob
#include "control/settings/Settings.h"  // for Settings
#include "gui/MainWindow.h"             // for MainWindow
#include "gui/dialog/XojSaveDlg.h"
#include "model/Document.h"           // for Document, Document::PDF
#include "util/PathUtil.h"            // for clearExtensions
#include "util/PopupWindowWrapper.h"  // for PopupWindowWrapper
#include "util/XojMsgBox.h"           // for XojMsgBox
#include "util/glib_casts.h"          // for wrap_for_g_callback_v
#include "util/i18n.h"                // for _, FS, _F

BaseExportJob::BaseExportJob(Control* control, const std::string& name): BlockingJob(control, name) {}

BaseExportJob::~BaseExportJob() = default;

void BaseExportJob::addFileFilterToDialog(GtkFileChooser* dialog, const std::string& name, const std::string& mime) {
    GtkFileFilter* filter = gtk_file_filter_new();
    gtk_file_filter_set_name(filter, name.c_str());
    gtk_file_filter_add_mime_type(filter, mime.c_str());
    gtk_file_chooser_add_filter(dialog, filter);
}

auto BaseExportJob::checkOverwriteBackgroundPDF(fs::path const& file) const -> bool {
    try {
        auto* document = control->getDocument();
        PdfExportExpectation expected;
        expected.sourceDocument = document->getFilepath();
        expected.backgroundPdf = document->getPdfFilepath();
        PdfExportVerifier::protectOutput(file, expected);
    } catch (const std::exception& error) {
        XojMsgBox::showErrorToUser(control->getGtkWindow(), error.what());
        return false;
    }
    return true;
}

void BaseExportJob::showFileChooser(std::function<void()> onFileSelected, std::function<void()> onCancel) {
    Settings* settings = control->getSettings();
    Document* doc = control->getDocument();
    doc->lock_shared();
    fs::path suggestedPath = doc->createSaveFoldername(settings->getLastSavePath());
    suggestedPath /=
            doc->createSaveFilename(Document::PDF, settings->getDefaultSaveName(), settings->getDefaultPdfExportName());
    doc->unlock_shared();

    auto pathValidation = [job = this](fs::path& p, const char* filterName) {
        job->setExtensionFromFilter(p, filterName);
        return job->testAndSetFilepath(p);
    };

    auto callback = [settings, onFileSelected = std::move(onFileSelected),
                     onCancel = std::move(onCancel)](std::optional<fs::path> p) {
        if (p && !p->empty()) {
            settings->setLastSavePath(p->parent_path());
            onFileSelected();
        } else {
            onCancel();
        }
    };

    auto popup = xoj::popup::PopupWindowWrapper<xoj::SaveExportDialog>(control->getSettings(), std::move(suggestedPath),
                                                                       _("Export File"), _("Export"),
                                                                       std::move(pathValidation), std::move(callback));

    auto* fc = GTK_FILE_CHOOSER(popup.getPopup()->getWindow());
    addFilterToDialog(fc);

    popup.show(GTK_WINDOW(this->control->getWindow()->getWindow()));
}

auto BaseExportJob::testAndSetFilepath(const fs::path& file) -> bool {
    try {
        if (!file.empty() && fs::is_directory(file.parent_path()) && checkOverwriteBackgroundPDF(file)) {
            this->filepath = file;
            return true;
        }
    } catch (const fs::filesystem_error& e) {
        std::string msg = FS(_F("Failed to resolve path with the following error:\n{1}") % e.what());
        XojMsgBox::showErrorToUser(control->getGtkWindow(), msg);
    }
    return false;
}

void BaseExportJob::afterRun() {
    if (pdfVerification) {
        const auto& result = *pdfVerification;
        const bool failed = result.status == PdfExportVerification::Status::Failed ||
                            result.status == PdfExportVerification::Status::Cancelled;
        std::string message = (failed ? "PDF checks failed" : "PDF checks completed") + std::string(" (expected ") +
                              std::to_string(result.expectedPages) + ", actual " + std::to_string(result.actualPages) +
                              " pages).\nOutput: " + result.output.string();
        if (!result.error.empty())
            message += "\n" + result.error;
        message += result.report.empty() ? "\nReport unavailable." : "\nReport: " + result.report.string();
        for (const auto& warning: result.warnings) message += "\n" + warning;
        if (failed)
            message += "\nExport was not published. Review any retained diagnostic output and retry with a different "
                       "filename.";
        XojMsgBox::showMessageToUser(
                control->getGtkWindow(), message,
                failed ? GTK_MESSAGE_ERROR :
                         (result.status == PdfExportVerification::Status::Warning ? GTK_MESSAGE_WARNING :
                                                                                    GTK_MESSAGE_INFO));
        return;
    }
    if (!this->errorMsg.empty()) {
        XojMsgBox::showErrorToUser(control->getGtkWindow(), this->errorMsg);
    }
}
