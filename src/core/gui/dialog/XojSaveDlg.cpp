#include "XojSaveDlg.h"

#include <optional>
#include <thread>

#include "control/settings/Settings.h"
#include "util/PathUtil.h"            // for fromGFile, toGFile
#include "util/PopupWindowWrapper.h"  // for PopupWindowWrapper
#include "util/Util.h"
#include "util/XojMsgBox.h"
#include "util/gtk4_helper.h"         // for gtk_file_chooser_set_current_folder
#include "util/i18n.h"                // for _
#include "util/raii/GObjectSPtr.h"    // for GObjectSPtr
#include "util/raii/GtkWindowUPtr.h"  // for GtkWindowUPtr

#include "FileChooserFiltersHelper.h"

static GtkWindow* makeWindow(Settings* settings, fs::path suggestedPath, const char* windowTitle,
                             const char* buttonLabel) {
    GtkWidget* dialog = gtk_file_chooser_dialog_new(windowTitle, nullptr, GTK_FILE_CHOOSER_ACTION_SAVE, _("_Cancel"),
                                                    GTK_RESPONSE_CANCEL, buttonLabel, GTK_RESPONSE_OK, nullptr);

    if (!suggestedPath.empty()) {
        gtk_file_chooser_set_current_folder(GTK_FILE_CHOOSER(dialog), Util::toGFile(suggestedPath.parent_path()).get(),
                                            nullptr);
        gtk_file_chooser_set_current_name(GTK_FILE_CHOOSER(dialog),
                                          Util::toGFilename(suggestedPath.filename()).c_str());
    }
    if (settings) {
        gtk_file_chooser_add_shortcut_folder(GTK_FILE_CHOOSER(dialog), Util::toGFile(settings->getLastOpenPath()).get(),
                                             nullptr);
    }

    return GTK_WINDOW(dialog);
}

xoj::SaveExportDialog::SaveExportDialog(Settings* settings, fs::path suggestedPath, const char* windowTitle,
                                        const char* buttonLabel,
                                        std::function<bool(fs::path&, const char* filterName)> pathValidation,
                                        std::function<void(std::optional<fs::path>)> callback):
        SaveExportDialog(settings, std::move(suggestedPath), windowTitle, buttonLabel, std::move(pathValidation),
                         [cb = std::move(callback)](std::optional<ExportDestination> destination) {
                             cb(destination ? std::optional<fs::path>(destination->path) : std::nullopt);
                         }) {
    needsExportConsent = false;
}

xoj::SaveExportDialog::SaveExportDialog(Settings* settings, fs::path suggestedPath, const char* windowTitle,
                                        const char* buttonLabel,
                                        std::function<bool(fs::path&, const char* filterName)> pathValidation,
                                        std::function<void(std::optional<ExportDestination>)> callback):
        inspection(std::make_shared<InspectionState>(InspectionState{this})),
        window(makeWindow(settings, std::move(suggestedPath), windowTitle, buttonLabel)),
        callback(std::move(callback)),
        pathValidation(std::move(pathValidation)) {
    this->signalId = g_signal_connect(
            window.get(), "response", G_CALLBACK(+[](GtkDialog* win, int response, gpointer data) {
                auto* self = static_cast<SaveExportDialog*>(data);
                auto* fc = GTK_FILE_CHOOSER(win);
                if (response == GTK_RESPONSE_OK) {
                    if (self->inspectionPending)
                        return;
                    auto file = Util::fromGFile(
                            xoj::util::GObjectSPtr<GFile>(gtk_file_chooser_get_file(fc), xoj::util::adopt).get());

                    if (self->pathValidation(file, gtk_file_filter_get_name(gtk_file_chooser_get_filter(fc)))) {
                        if (self->needsExportConsent && file.extension() == ".pdf") {
                            self->inspectDestination(std::move(file));
                        } else {
                            // Non-PDF save callers retain their existing path-only contract.
                            XojMsgBox::replaceFileQuestion(
                                    GTK_WINDOW(win), std::move(file),
                                    [state = self->inspection](std::optional<fs::path> path) {
                                        if (state->owner)
                                            state->owner->close(
                                                    path ? std::optional<ExportDestination>(
                                                                   ExportDestination{*path, std::nullopt, false}) :
                                                           std::nullopt);
                                    });
                        }
                    }  // else the dialog stays on until a suitable destination is found or cancel is hit.
                } else {
                    self->close(std::nullopt);
                }
            }),
            this);
}

xoj::SaveExportDialog::~SaveExportDialog() { inspection->owner = nullptr; }

void xoj::SaveExportDialog::inspectDestination(fs::path path) {
    inspectionPending = true;
    gtk_dialog_set_response_sensitive(GTK_DIALOG(window.get()), GTK_RESPONSE_OK, false);
    // SHA-256 can involve a large existing PDF. Do not block GTK while obtaining consent evidence.
    std::thread([state = inspection, path = std::move(path)] {
        std::optional<ExportDestination> destination;
        std::string error;
        try {
            destination = ExportDestination::capture(path);
        } catch (const std::exception& e) {
            error = e.what();
        }
        Util::execInUiThread([state, destination = std::move(destination), error = std::move(error)]() mutable {
            auto* self = state->owner;
            if (!self)
                return;
            if (destination) {
                self->confirmDestination(std::move(*destination));
            } else {
                self->inspectionPending = false;
                gtk_dialog_set_response_sensitive(GTK_DIALOG(self->window.get()), GTK_RESPONSE_OK, true);
                XojMsgBox::showErrorToUser(self->window.get(), error);
            }
        });
    }).detach();
}

void xoj::SaveExportDialog::confirmDestination(ExportDestination destination) {
    if (!destination.existing) {
        close(std::move(destination));
        return;
    }
    // Do not recheck existence and bypass this question if the inspected file disappeared.
    const auto utf8 = destination.path.u8string();
    const auto message = std::string(utf8.begin(), utf8.end()) + "\n" +
                         _("The existing file will be retained in a recovery folder. If it changes before export, "
                           "InkQuay will stop and preserve the files.");
    XojMsgBox::askQuestion(window.get(), _("Replace the selected file?"), message,
                           {{_("Cancel"), GTK_RESPONSE_CANCEL}, {_("Replace"), GTK_RESPONSE_OK}},
                           [state = inspection, destination = std::move(destination)](int response) mutable {
                               auto* self = state->owner;
                               if (!self)
                                   return;
                               if (response == GTK_RESPONSE_OK) {
                                   destination.overwriteConfirmed = true;
                                   self->close(std::move(destination));
                               } else {
                                   self->inspectionPending = false;
                                   gtk_dialog_set_response_sensitive(GTK_DIALOG(self->window.get()), GTK_RESPONSE_OK,
                                                                     true);
                               }
                           });
}

void xoj::SaveExportDialog::close(std::optional<ExportDestination> destination) {
    // We need to call gtk_window_close() before invoking the callback, because if the callback pops up another dialog,
    // the first one won't close...
    // But since gtk_window_close() triggers the destruction of *this, we first move the callback
    auto cb = std::move(this->callback);

    // Closing the window causes another "response" signal, which we want to ignore
    g_signal_handler_disconnect(window.get(), signalId);
    gtk_window_close(window.get());  // Destroys *this. Don't do anything after this call

    cb(std::move(destination));
}

static bool xoppPathValidation(fs::path& p, const char*) {
    Util::clearExtensions(p);
    p += ".xopp";
    return true;
}

void xoj::SaveExportDialog::showSaveFileDialog(GtkWindow* parent, Settings* settings, fs::path suggestedPath,
                                               std::function<void(std::optional<fs::path>)> callback) {
    auto popup = xoj::popup::PopupWindowWrapper<SaveExportDialog>(settings, std::move(suggestedPath), _("Save File"),
                                                                  _("Save"), xoppPathValidation, std::move(callback));

    auto* fc = GTK_FILE_CHOOSER(popup.getPopup()->getWindow());
    xoj::addFilterXopp(fc);

    popup.show(parent);
}
