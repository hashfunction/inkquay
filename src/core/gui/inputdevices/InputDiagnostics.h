// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#pragma once

#include <cstdio>
#include <filesystem>
#include <gtk/gtk.h>

// Explicitly enabled, observational GTK3 trace. Never changes input or activation.
class InputDiagnostics {
public:
    explicit InputDiagnostics(const std::filesystem::path& output);
    ~InputDiagnostics();
    InputDiagnostics(const InputDiagnostics&) = delete;
    InputDiagnostics& operator=(const InputDiagnostics&) = delete;
    void attach(GtkWindow* window);
    static gboolean propagate(GtkWindow* window, GdkEventKey* event);
    static void fileLoaded(GtkWindow* window);

private:
    enum class Phase { Started, Attached, GtkKey, Before, After, Focus, Grab, OpenEnabled, ExportEnabled,
                       OpenActivate, ExportActivate, FileLoaded, Heartbeat, NativeKey, Stopped, Truncated };
    void record(Phase phase, GdkEventKey* key = nullptr, GtkWidget* target = nullptr, int handled = -1,
                guint nativeMessage = 0, guint nativeCode = 0, guint nativeState = 0) noexcept;
    static bool relevant(guint key, guint state);
    static gint snoop(GtkWidget*, GdkEventKey*, gpointer);
    static GdkFilterReturn nativeFilter(GdkXEvent*, GdkEvent*, gpointer);
    static gboolean heartbeat(gpointer);
    FILE* output = nullptr;
    GtkWindow* window = nullptr;
    GAction* openAction = nullptr;
    GAction* exportAction = nullptr;
    guint snooper = 0;
    guint timer = 0;
    guint gtkModifiers = 0;
    guint nativeModifiers = 0;
    unsigned count = 0;
    size_t bytes = 0;
    bool stopped = false;
    static InputDiagnostics* active;
};
