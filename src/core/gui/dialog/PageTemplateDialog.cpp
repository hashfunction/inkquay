#include "PageTemplateDialog.h"

#include <cmath>
#include <cstdio>    // for sprintf
#include <ctime>     // for localtime, strftime, time
#include <fstream>   // for ofstream, basic_ostream
#include <memory>    // for allocator, unique_ptr
#include <optional>  // for optional
#include <stdexcept>
#include <string>  // for string, operator<<

#include <gdk/gdk.h>      // for GdkRGBA
#include <glib-object.h>  // for G_CALLBACK, g_signal_c...

#include "control/pagetype/PageTemplateLibrary.h"
#include "control/pagetype/PageTypeHandler.h"  // for PageTypeInfo, PageType...
#include "control/settings/Settings.h"         // for Settings
#include "gui/Builder.h"                       // for Builder
#include "gui/dialog/XojOpenDlg.h"             // for XojOpenDlg
#include "gui/menus/popoverMenus/PageTypeSelectionPopoverGridOnly.h"
#include "gui/toolbarMenubar/ToolMenuHandler.h"
#include "model/FormatDefinitions.h"  // for FormatUnits, XOJ_UNITS
#include "model/PageType.h"           // for PageType
#include "util/Color.h"               // for GdkRGBA_to_argb, rgb_t...
#include "util/PathUtil.h"            // for fromGFile, readString
#include "util/PopupWindowWrapper.h"  // for PopupWindowWrapper
#include "util/XojMsgBox.h"           // for XojMsgBox
#include "util/i18n.h"                // for _
#include "util/serdesstream.h"        // for serdes_stream

#include "FormatDialog.h"  // for FormatDialog
#include "filesystem.h"    // for path

class GladeSearchpath;

constexpr auto UI_FILE = "pageTemplate.glade";
constexpr auto UI_DIALOG_NAME = "templateDialog";

using namespace xoj::popup;

PageTemplateDialog::PageTemplateDialog(GladeSearchpath* gladeSearchPath, Settings* settings, ToolMenuHandler* toolmenu,
                                       PageTypeHandler* types, PageTemplateLibrary* library):
        gladeSearchPath(gladeSearchPath),
        settings(settings),
        toolMenuHandler(toolmenu),
        types(types),
        library(library) {
    model.parse(settings->getPageTemplate());

    Builder builder(gladeSearchPath, UI_FILE);
    window.reset(GTK_WINDOW(builder.get(UI_DIALOG_NAME)));

    presetSelector = GTK_COMBO_BOX_TEXT(builder.get("presetSelector"));
    presetName = GTK_ENTRY(builder.get("presetName"));
    presetError = GTK_LABEL(builder.get("presetError"));
    presetActions = builder.get("presetActions");
    presetRename = builder.get("presetRename");
    presetDelete = builder.get("presetDelete");
    g_signal_connect_swapped(builder.get("presetRetry"), "clicked",
                             G_CALLBACK(+[](PageTemplateDialog* self) { self->reloadPresets(); }), this);
    for (auto [id, action]: {std::pair{"presetSave", 0}, {"presetRename", 1}, {"presetDelete", 2}}) {
        g_object_set_data(G_OBJECT(builder.get(id)), "inkquay-action", GINT_TO_POINTER(action));
        g_signal_connect(builder.get(id), "clicked", G_CALLBACK(+[](GtkButton* button, gpointer data) {
                             static_cast<PageTemplateDialog*>(data)->managePreset(
                                     GPOINTER_TO_INT(g_object_get_data(G_OBJECT(button), "inkquay-action")));
                         }),
                         this);
    }
    g_signal_connect_swapped(presetSelector, "changed", G_CALLBACK(+[](PageTemplateDialog* self) {
                                 const char* id = gtk_combo_box_get_active_id(GTK_COMBO_BOX(self->presetSelector));
                                 const auto* preset = id ? self->library->find(id) : nullptr;
                                 gtk_widget_set_sensitive(self->presetRename, preset && !preset->builtIn);
                                 gtk_widget_set_sensitive(self->presetDelete, preset && !preset->builtIn);
                                 if (preset) {
                                     self->model.parse(preset->serializedTemplate);
                                     gtk_entry_set_text(self->presetName, preset->name.c_str());
                                     self->updateDataFromModel();
                                 }
                             }),
                             this);

    // Needs to be initialized after this->window
    pageTypeSelectionMenu = std::make_unique<PageTypeSelectionPopoverGridOnly>(types, settings, this);
    gtk_menu_button_set_popup(GTK_MENU_BUTTON(builder.get("btBackgroundDropdown")),
                              pageTypeSelectionMenu->getPopover());

    pageSizeLabel = GTK_LABEL(builder.get("lbPageSize"));
    backgroundTypeLabel = GTK_LABEL(builder.get("lbBackgroundType"));
    backgroundColorChooser = GTK_COLOR_CHOOSER(builder.get("cbBackgroundButton"));
    copyLastPageButton = GTK_TOGGLE_BUTTON(builder.get("cbCopyLastPage"));
    copyLastPageSizeButton = GTK_TOGGLE_BUTTON(builder.get("cbCopyLastPageSize"));


    g_signal_connect_swapped(builder.get("btChangePaperSize"), "clicked",
                             G_CALLBACK(+[](PageTemplateDialog* self) { self->showPageSizeDialog(); }), this);

    g_signal_connect_swapped(builder.get("btLoad"), "clicked",
                             G_CALLBACK(+[](PageTemplateDialog* self) { self->loadFromFile(); }), this);

    g_signal_connect_swapped(builder.get("btSave"), "clicked",
                             G_CALLBACK(+[](PageTemplateDialog* self) { self->saveToFile(); }), this);

    g_signal_connect_swapped(builder.get("btCancel"), "clicked", G_CALLBACK(gtk_window_close), this->getWindow());
    g_signal_connect_swapped(
            builder.get("btOk"), "clicked", G_CALLBACK(+[](PageTemplateDialog* self) {
                self->saveToModel();
                self->settings->setPageTemplate(self->model.toString());
                self->saved = true;
                if (self->toolMenuHandler) {
                    self->toolMenuHandler->setDefaultNewPageType(self->model.getPageInsertType());
                    self->toolMenuHandler->setDefaultNewPaperSize(
                            self->model.isCopyLastPageSize() ? std::nullopt : std::optional(PaperSize(self->model)));
                }
                gtk_window_close(self->getWindow());
            }),
            this);

    updateDataFromModel();
    reloadPresets();
}

PageTemplateDialog::~PageTemplateDialog() = default;

void PageTemplateDialog::updateDataFromModel() {
    GdkRGBA color = Util::rgb_to_GdkRGBA(model.getBackgroundColor());
    gtk_color_chooser_set_rgba(backgroundColorChooser, &color);

    updatePageSize();

    pageTypeSelectionMenu->setSelectedPT(model.getBackgroundType());
    if (const auto* info = types->getInfoOn(model.getBackgroundType()))
        changeCurrentPageBackground(info);
    else
        gtk_label_set_text(backgroundTypeLabel, "Custom template");

    gtk_toggle_button_set_active(copyLastPageButton, model.isCopyLastPageSettings());
    gtk_toggle_button_set_active(copyLastPageSizeButton, model.isCopyLastPageSize());
}

void PageTemplateDialog::changeCurrentPageBackground(const PageTypeInfo* info) {
    model.setBackgroundType(info->page);

    gtk_label_set_text(backgroundTypeLabel, info->name.c_str());
}

void PageTemplateDialog::saveToModel() {
    model.setCopyLastPageSettings(gtk_toggle_button_get_active(copyLastPageButton));
    model.setCopyLastPageSize(gtk_toggle_button_get_active(copyLastPageSizeButton));

    GdkRGBA color;
    gtk_color_chooser_get_rgba(backgroundColorChooser, &color);
    model.setBackgroundColor(Util::GdkRGBA_to_argb(color));
}

void PageTemplateDialog::saveToFile() {
    saveToModel();

    GtkWidget* dialog =
            gtk_file_chooser_dialog_new(_("Save File"), this->getWindow(), GTK_FILE_CHOOSER_ACTION_SAVE, _("_Cancel"),
                                        GTK_RESPONSE_CANCEL, _("_Save"), GTK_RESPONSE_OK, nullptr);

    GtkFileFilter* filterXoj = gtk_file_filter_new();
    gtk_file_filter_set_name(filterXoj, _("InkQuay template"));
    gtk_file_filter_add_mime_type(filterXoj, "application/x-xopt");
    gtk_file_chooser_add_filter(GTK_FILE_CHOOSER(dialog), filterXoj);

    if (!settings->getLastSavePath().empty()) {
        gtk_file_chooser_set_current_folder(GTK_FILE_CHOOSER(dialog), Util::toGFile(settings->getLastSavePath()).get(),
                                            nullptr);
    }

    time_t curtime = time(nullptr);
    char stime[128];
    strftime(stime, sizeof(stime), "%F-Template-%H-%M.xopt", localtime(&curtime));
    fs::path saveFilename = stime;  // There may be an issue here, if the C and C++ locales do not use the same encoding

    gtk_file_chooser_set_current_name(GTK_FILE_CHOOSER(dialog), Util::toGFilename(saveFilename).c_str());

    class FileDlg final {
    public:
        FileDlg(GtkDialog* dialog, PageTemplateDialog* parent): window(GTK_WINDOW(dialog)), parent(parent) {
            this->signalId = g_signal_connect(
                    dialog, "response", G_CALLBACK((+[](GtkDialog* dialog, int response, gpointer data) {
                        FileDlg* self = static_cast<FileDlg*>(data);
                        if (response == GTK_RESPONSE_OK) {
                            auto file = Util::fromGFile(
                                    xoj::util::GObjectSPtr<GFile>(gtk_file_chooser_get_file(GTK_FILE_CHOOSER(dialog)),
                                                                  xoj::util::adopt)
                                            .get());

                            auto saveTemplate = [self, dialog](const fs::path& file) {
                                // Closing the window causes another "response" signal, which we want to ignore
                                g_signal_handler_disconnect(dialog, self->signalId);
                                gtk_window_close(GTK_WINDOW(dialog));
                                self->parent->settings->setLastSavePath(file.parent_path());

                                auto out = serdes_stream<std::ofstream>(file);
                                out << self->parent->model.toString();
                            };
                            XojMsgBox::replaceFileQuestion(GTK_WINDOW(dialog), std::move(file),
                                                           std::move(saveTemplate));
                        } else {
                            // Closing the window causes another "response" signal, which we want to ignore
                            g_signal_handler_disconnect(dialog, self->signalId);
                            gtk_window_close(GTK_WINDOW(dialog));  // Deletes self, don't do anything after this
                        }
                    })),
                    this);
        }
        ~FileDlg() = default;

        inline GtkWindow* getWindow() const { return window.get(); }

    private:
        xoj::util::GtkWindowUPtr window;
        PageTemplateDialog* parent;
        gulong signalId;
    };

    auto popup = xoj::popup::PopupWindowWrapper<FileDlg>(GTK_DIALOG(dialog), this);
    popup.show(GTK_WINDOW(this->getWindow()));
}

void PageTemplateDialog::loadFromFile() {
    xoj::OpenDlg::showOpenTemplateDialog(this->getWindow(), settings, [this](fs::path path) {
        auto contents = Util::readString(path);
        if (!contents.has_value()) {
            return;
        }
        try {
            PageTemplateSettings candidate;
            if (!candidate.parse(*contents) || !std::isfinite(candidate.getPageWidth()) ||
                !std::isfinite(candidate.getPageHeight()) || candidate.getPageWidth() <= 0 ||
                candidate.getPageHeight() <= 0)
                throw std::runtime_error("Invalid page template. The current page settings were retained.");
            model = candidate;
            updateDataFromModel();
        } catch (const std::exception& error) {
            XojMsgBox::showErrorToUser(this->getWindow(), error.what());
        }
    });
}

void PageTemplateDialog::updatePageSize() {
    const FormatUnits* formatUnit = &XOJ_UNITS[settings->getSizeUnitIndex()];

    char buffer[64];
    sprintf(buffer, "%0.2lf", model.getPageWidth() / formatUnit->scale);
    std::string pageSize = buffer;
    pageSize += formatUnit->name;
    pageSize += " x ";

    sprintf(buffer, "%0.2lf", model.getPageHeight() / formatUnit->scale);
    pageSize += buffer;
    pageSize += formatUnit->name;

    gtk_label_set_text(pageSizeLabel, pageSize.c_str());
}

void PageTemplateDialog::showPageSizeDialog() {
    auto popup = xoj::popup::PopupWindowWrapper<xoj::popup::FormatDialog>(gladeSearchPath, settings,
                                                                          model.getPageWidth(), model.getPageHeight(),
                                                                          [dlg = this](double width, double height) {
                                                                              dlg->model.setPageWidth(width);
                                                                              dlg->model.setPageHeight(height);

                                                                              dlg->updatePageSize();
                                                                          });
    popup.show(this->getWindow());
}

/**
 * The dialog was confirmed / saved
 */
auto PageTemplateDialog::isSaved() const -> bool { return saved; }

void PageTemplateDialog::refreshPresets(const std::string& selected) {
    gtk_combo_box_text_remove_all(presetSelector);
    gtk_combo_box_text_append(presetSelector, "", "Current settings");
    for (const auto& preset: library->presets())
        gtk_combo_box_text_append(presetSelector, preset.id.c_str(), preset.name.c_str());
    gtk_combo_box_set_active_id(GTK_COMBO_BOX(presetSelector), selected.c_str());
}
void PageTemplateDialog::reloadPresets() {
    try {
        library->load();
        refreshPresets();
        gtk_widget_set_sensitive(presetActions, true);
        gtk_label_set_text(presetError, "");
    } catch (const std::exception& error) {
        gtk_widget_set_sensitive(presetActions, false);
        std::string message = std::string(error.what()) + "\nRestore page-template-library.ini from your backup, then "
                                                          "Retry loading. Saved templates have not been replaced.";
        gtk_label_set_text(presetError, message.c_str());
    }
}
void PageTemplateDialog::managePreset(int action) {
    try {
        std::string name = gtk_entry_get_text(presetName);
        const char* selected = gtk_combo_box_get_active_id(GTK_COMBO_BOX(presetSelector));
        std::string id = selected ? selected : "";
        if (action == 0) {
            saveToModel();
            gchar* unique = g_uuid_string_random();
            id = unique;
            g_free(unique);
            library->saveUserPreset({id, name, model.toString(), false});
        } else if (action == 1)
            library->renameUserPreset(id, name);
        else {
            library->removeUserPreset(id);
            id.clear();
        }
        refreshPresets(id);
        gtk_label_set_text(presetError, "");
    } catch (const std::exception& error) {
        gtk_label_set_text(presetError, error.what());
    }
}
