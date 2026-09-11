// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include <fstream>
#include <functional>
#include <memory>

#include "control/jobs/PdfExportVerifier.h"
#include "gui/dialog/XojSaveDlg.h"
#include "util/PathUtil.h"
#include "util/PopupWindowWrapper.h"
#include "util/raii/GObjectSPtr.h"

#include "GtkTest.h"

namespace {
bool waitFor(const std::function<bool()>& ready) {
    const auto deadline = g_get_monotonic_time() + 5000000;
    while (!ready() && g_get_monotonic_time() < deadline) {
        // Non-blocking iterations retain the deadline even if a GTK callback never arrives.
        g_main_context_iteration(nullptr, false);
        g_usleep(1000);
    }
    return ready();
}
GtkDialog* replacementQuestion(GtkWindow* parent) {
    GList* windows = gtk_window_list_toplevels();
    GtkDialog* result = nullptr;
    for (auto* w = windows; w; w = w->next) {
        if (GTK_IS_MESSAGE_DIALOG(w->data) && gtk_window_get_transient_for(GTK_WINDOW(w->data)) == parent) {
            result = GTK_DIALOG(w->data);
            break;
        }
    }
    g_list_free(windows);
    return result;
}
struct Reply {
    bool called = false;
    std::optional<xoj::ExportDestination> destination;
};
}  // namespace

class PdfDestinationConsentTest: public GtkTest {
    void runTest(GtkApplication*) override {
        gchar* temporary = g_dir_make_tmp("inkquay-consent-dialog-XXXXXX", nullptr);
        const fs::path directory(temporary);
        g_free(temporary);
        for (bool existing: {false, true}) {
            const auto output = directory / (existing ? "existing.pdf" : "new.pdf");
            if (existing)
                std::ofstream(output) << "approved bytes";
            const auto before = xoj::ExportDestination::capture(output);
            auto reply = std::make_shared<Reply>();
            auto popup = xoj::popup::PopupWindowWrapper<xoj::SaveExportDialog>(
                    nullptr, output, "PDF consent test", "Export", [](fs::path&, const char*) { return true; },
                    [reply](std::optional<xoj::ExportDestination> value) {
                        reply->called = true;
                        reply->destination = std::move(value);
                    });
            xoj::util::GObjectSPtr<GtkWindow> window(popup.getPopup()->getWindow(), xoj::util::ref);
            auto* filter = gtk_file_filter_new();
            gtk_file_filter_set_name(filter, "PDF");
            gtk_file_filter_add_pattern(filter, "*.pdf");
            gtk_file_chooser_add_filter(GTK_FILE_CHOOSER(window.get()), filter);
            popup.show(nullptr);
            const bool selected = waitFor([&] {
                xoj::util::GObjectSPtr<GFile> file(gtk_file_chooser_get_file(GTK_FILE_CHOOSER(window.get())),
                                                   xoj::util::adopt);
                return file && Util::fromGFile(file.get()) == output;
            });
            EXPECT_TRUE(selected);
            if (selected)
                gtk_dialog_response(GTK_DIALOG(window.get()), GTK_RESPONSE_OK);
            if (existing && selected) {
                const bool questioned = waitFor([&] { return replacementQuestion(window.get()) != nullptr; });
                EXPECT_TRUE(questioned);
                EXPECT_FALSE(reply->called);
                if (questioned) {
                    // Change the target while the actual GTK question is open. Consent must
                    // describe the inspected file, never recapture this unapproved replacement.
                    fs::rename(output, directory / "original.pdf");
                    std::ofstream(output) << "different owner";
                    gtk_dialog_response(replacementQuestion(window.get()), GTK_RESPONSE_OK);
                }
            }
            EXPECT_TRUE(waitFor([&] { return reply->called; }));
            if (reply->destination) {
                EXPECT_EQ(reply->destination->existing, before.existing);
                EXPECT_EQ(reply->destination->overwriteConfirmed, existing);
                if (!existing)
                    std::ofstream(output) << "late owner";
                bool exported = false;
                const auto result = PdfExportVerifier::exportChecked(*reply->destination, {},
                                                                     [&](const fs::path&) { exported = true; });
                EXPECT_FALSE(exported);
                EXPECT_FALSE(result.published);
                EXPECT_EQ(result.status, PdfExportVerification::Status::Failed);
            } else {
                ADD_FAILURE() << "Chooser did not return its destination consent";
            }
            if (!reply->called)
                gtk_window_close(window.get());
        }
        fs::remove_all(directory);
    }
};
TEST_F(PdfDestinationConsentTest, CarriesNewNameAndConfirmedFileSnapshotsToTheWorker) {}
