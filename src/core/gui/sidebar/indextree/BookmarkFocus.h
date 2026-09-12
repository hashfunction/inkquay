// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#pragma once
#include <gtk/gtk.h>

namespace xoj::gui {
inline void focusBookmarkTree(GtkTreeView* tree) {
    // Model refresh also selects bookmarks in an inactive sidebar. Giving that
    // unmapped tree focus can swallow window shortcuts before GTK accelerators.
    auto* widget = GTK_WIDGET(tree);
    if (gtk_widget_get_mapped(widget)) {
        gtk_widget_grab_focus(widget);
    }
}
}
