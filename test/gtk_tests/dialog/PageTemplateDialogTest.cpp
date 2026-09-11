// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include "control/pagetype/PageTemplateLibrary.h"
#include "control/pagetype/PageTypeHandler.h"
#include "control/settings/Settings.h"
#include "gui/GladeSearchpath.h"
#include "gui/dialog/PageTemplateDialog.h"

#include "GtkTest.h"
#include "config-test.h"

static GtkWidget* named(GtkWidget* widget, const char* id) {
    if (GTK_IS_BUILDABLE(widget) && g_strcmp0(gtk_buildable_get_name(GTK_BUILDABLE(widget)), id) == 0)
        return widget;
    if (!GTK_IS_CONTAINER(widget))
        return nullptr;
    GList* children = gtk_container_get_children(GTK_CONTAINER(widget));
    GtkWidget* result = nullptr;
    for (auto* child = children; child && !result; child = child->next) result = named(GTK_WIDGET(child->data), id);
    g_list_free(children);
    return result;
}
class PageTemplateDialogTest: public GtkTest {
    void runTest(GtkApplication*) override {
        gchar* temporary = g_dir_make_tmp("inkquay-dialog-XXXXXX", nullptr);
        fs::path dir(temporary);
        g_free(temporary);
        fs::copy_file(fs::path(PROJECT_SOURCE_DIR) / "resources-templates/pagetemplates.ini.in",
                      dir / "pagetemplates.ini");
        GladeSearchpath paths;
        paths.addSearchDirectory(fs::path(GET_UI_FOLDER));
        paths.addSearchDirectory(dir);
        Settings settings(dir / "settings.xml");
        PageTemplateSettings model;
        settings.setPageTemplate(model.toString());
        PageTypeHandler types(&paths);
        PageTemplateLibrary library(dir / "library.ini", dir / "pagetemplates.ini");
        library.load();
        const auto before = settings.getPageTemplate();
        {
            xoj::popup::PageTemplateDialog dialog(&paths, &settings, nullptr, &types, &library);
            auto* selector = named(GTK_WIDGET(dialog.getWindow()), "presetSelector");
            ASSERT_NE(selector, nullptr);
            gtk_combo_box_set_active_id(GTK_COMBO_BOX(selector), "inkquayCornell");
            EXPECT_EQ(settings.getPageTemplate(), before);
            EXPECT_FALSE(gtk_widget_get_sensitive(named(GTK_WIDGET(dialog.getWindow()), "presetDelete")));
            gtk_button_clicked(GTK_BUTTON(named(GTK_WIDGET(dialog.getWindow()), "btCancel")));
            EXPECT_EQ(settings.getPageTemplate(), before);
        }
        {
            xoj::popup::PageTemplateDialog dialog(&paths, &settings, nullptr, &types, &library);
            gtk_combo_box_set_active_id(GTK_COMBO_BOX(named(GTK_WIDGET(dialog.getWindow()), "presetSelector")),
                                        "inkquayCornell");
            gtk_button_clicked(GTK_BUTTON(named(GTK_WIDGET(dialog.getWindow()), "btOk")));
            EXPECT_EQ(settings.getPageTemplate(), library.find("inkquayCornell")->serializedTemplate);
        }
        fs::remove_all(dir);
    }
};
TEST_F(PageTemplateDialogTest, ApplyingPresetUpdatesDefaultOnlyAfterOk) {}
