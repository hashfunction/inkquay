// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include "gui/inputdevices/InputDiagnostics.h"
#include "gui/sidebar/indextree/BookmarkFocus.h"
#include "GtkTest.h"

namespace {
struct ExportKeys { unsigned actions = 0; bool handled = false; };
void settle() {
    for (int i = 0; i < 40; ++i) { g_main_context_iteration(nullptr, false); g_usleep(1000); }
}
}

class BookmarkFocusTest: public GtkTest {
    void runTest(GtkApplication* app) override {
        auto* window = GTK_WINDOW(gtk_application_window_new(app));
        auto* contents = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
        auto* canvas = gtk_drawing_area_new();
        auto* scroll = gtk_scrolled_window_new(nullptr, nullptr);
        auto* tree = GTK_TREE_VIEW(gtk_tree_view_new());
        gtk_widget_set_can_focus(canvas, true);
        gtk_container_add(GTK_CONTAINER(window), contents);
        gtk_box_pack_start(GTK_BOX(contents), scroll, false, false, 0);
        gtk_box_pack_start(GTK_BOX(contents), canvas, true, true, 0);
        gtk_container_add(GTK_CONTAINER(scroll), GTK_WIDGET(tree));
        auto* model = gtk_list_store_new(1, G_TYPE_STRING);
        gtk_tree_view_set_model(tree, GTK_TREE_MODEL(model));
        gtk_tree_view_insert_column_with_attributes(tree, -1, "Bookmark", gtk_cell_renderer_text_new(), "text", 0, nullptr);
        GtkTreeIter row;
        gtk_list_store_append(model, &row);
        gtk_list_store_set(model, &row, 0, "First page", -1);

        ExportKeys keys;
        g_signal_connect(window, "key-press-event", G_CALLBACK(+[](GtkWidget* w, GdkEventKey* e, gpointer p) -> gboolean {
            auto& value = *static_cast<ExportKeys*>(p);
            value.handled = InputDiagnostics::propagate(GTK_WINDOW(w), e);
            return value.handled;
        }), &keys);
        auto* action = g_simple_action_new("export-as-pdf", nullptr);
        g_signal_connect(action, "activate", G_CALLBACK(+[](GSimpleAction*, GVariant*, gpointer p) {
            ++static_cast<ExportKeys*>(p)->actions;
        }), &keys);
        g_action_map_add_action(G_ACTION_MAP(window), G_ACTION(action));
        const char* accelerators[] = {"<Control><Alt>e", nullptr};
        gtk_application_set_accels_for_action(app, "win.export-as-pdf", accelerators);
        // The inactive sidebar parent is hidden, while its child remains visible,
        // exactly the Sidebar::updateVisibleTabs topology. It has never realized.
        gtk_widget_show(GTK_WIDGET(tree));
        gtk_widget_show(canvas); gtk_widget_show(contents); gtk_widget_show(GTK_WIDGET(window));
        gtk_widget_grab_focus(canvas); settle();
        ASSERT_EQ(gtk_window_get_focus(window), canvas);
        ASSERT_FALSE(gtk_widget_get_mapped(GTK_WIDGET(tree)));
        ASSERT_FALSE(gtk_widget_get_realized(GTK_WIDGET(tree)));
        ASSERT_TRUE(gtk_widget_get_visible(GTK_WIDGET(tree)));
        auto deliver = [&] {
            auto* event = gdk_event_new(GDK_KEY_PRESS);
            event->key.window = GDK_WINDOW(g_object_ref(gtk_widget_get_window(GTK_WIDGET(window))));
            event->key.keyval = GDK_KEY_e;
            event->key.state = GdkModifierType(GDK_CONTROL_MASK | GDK_MOD1_MASK);
            GdkKeymapKey* map = nullptr; gint count = 0;
            ASSERT_TRUE(gdk_keymap_get_entries_for_keyval(gdk_keymap_get_for_display(gtk_widget_get_display(canvas)), GDK_KEY_e, &map, &count));
            ASSERT_GT(count, 0);
            event->key.hardware_keycode = static_cast<guint16>(map[0].keycode);
            event->key.group = static_cast<guint8>(map[0].group); g_free(map);
            gdk_event_set_device(event, gdk_seat_get_keyboard(gdk_display_get_default_seat(gtk_widget_get_display(canvas))));
            gtk_main_do_event(event); gdk_event_free(event);
        };
        // Invoke the actual production focus boundary, not a copied predicate.
        // The original unconditional grab focuses the unrealized tree and causes
        // GTK to consume the normal export shortcut before its action activates.
        xoj::gui::focusBookmarkTree(tree);
        EXPECT_EQ(gtk_window_get_focus(window), canvas);
        deliver(); EXPECT_FALSE(keys.handled); EXPECT_EQ(keys.actions, 1u);

        // Visible bookmark selection still takes normal focus and keeps the row.
        gtk_widget_show(scroll); settle();
        ASSERT_TRUE(gtk_widget_get_mapped(GTK_WIDGET(tree)));
        gtk_tree_selection_select_iter(gtk_tree_view_get_selection(tree), &row);
        xoj::gui::focusBookmarkTree(tree);
        EXPECT_EQ(gtk_window_get_focus(window), GTK_WIDGET(tree));
        EXPECT_TRUE(gtk_tree_selection_iter_is_selected(gtk_tree_view_get_selection(tree), &row));
        deliver(); EXPECT_FALSE(keys.handled); EXPECT_EQ(keys.actions, 2u);

        // Switching away after realization must also preserve canvas focus; a
        // realized-only or visible-only guard would still steal focus here.
        gtk_widget_hide(scroll); gtk_widget_grab_focus(canvas); settle();
        ASSERT_TRUE(gtk_widget_get_realized(GTK_WIDGET(tree)));
        ASSERT_FALSE(gtk_widget_get_mapped(GTK_WIDGET(tree)));
        xoj::gui::focusBookmarkTree(tree);
        EXPECT_EQ(gtk_window_get_focus(window), canvas);
        EXPECT_TRUE(gtk_tree_selection_iter_is_selected(gtk_tree_view_get_selection(tree), &row));
        deliver(); EXPECT_FALSE(keys.handled); EXPECT_EQ(keys.actions, 3u);
        g_object_unref(action); g_object_unref(model);
        gtk_widget_destroy(GTK_WIDGET(window));
    }
};
TEST_F(BookmarkFocusTest, HiddenBookmarkRefreshPreservesNormalExportShortcut) {}
