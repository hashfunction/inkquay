// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include "InputDiagnostics.h"

#include <cerrno>
#include <fcntl.h>
#include <sstream>
#include <stdexcept>
#include <glib/gstdio.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#else
#include <unistd.h>
#endif

InputDiagnostics* InputDiagnostics::active = nullptr;
namespace {
constexpr unsigned MAX_RECORDS = 512;
constexpr size_t MAX_BYTES = 1024 * 1024;
std::string typeName(gpointer object) {
    if (!object) return "none";
    const char* type = G_OBJECT_TYPE_NAME(object);
    std::string value;
    for (unsigned i=0; type[i] && i<80; ++i) {
        char c = type[i];
        if (!g_ascii_isalnum(c) && c != '_') return "unknown";
        value += c;
    }
    return value;
}
}
InputDiagnostics::InputDiagnostics(const std::filesystem::path& path) {
    namespace fs = std::filesystem;
    if (active || !path.is_absolute() || path.filename().empty() || path != path.lexically_normal())
        throw std::runtime_error("Input diagnostics requires a fresh absolute output file");
    std::error_code error;
    auto parent = fs::canonical(path.parent_path(), error);
    if (error || parent != path.parent_path() || !fs::is_directory(parent))
        throw std::runtime_error("Input diagnostics output parent must exist without redirection");
    const auto encoded = path.u8string();
    int flags = O_CREAT | O_EXCL | O_WRONLY;
#ifdef O_BINARY
    flags |= O_BINARY;
#endif
#ifdef O_CLOEXEC
    flags |= O_CLOEXEC;
#endif
#ifdef O_NOFOLLOW
    flags |= O_NOFOLLOW;
#endif
    int fd = g_open(reinterpret_cast<const char*>(encoded.c_str()), flags, 0600);
    if (fd < 0) throw std::runtime_error("Cannot exclusively create input diagnostics output");
    output = fdopen(fd, "wb");
    if (!output) {
#ifdef _WIN32
        _close(fd);
#else
        close(fd);
#endif
        throw std::runtime_error("Cannot open input diagnostics output stream");
    }
    active = this;
    record(Phase::Started);
}
InputDiagnostics::~InputDiagnostics() {
    if (timer) g_source_remove(timer);
    if (snooper) gtk_key_snooper_remove(snooper);
#ifdef _WIN32
    if (window) gdk_window_remove_filter(nullptr, nativeFilter, this);
#endif
    record(Phase::Stopped);
    for (GObject* object: {G_OBJECT(window), G_OBJECT(openAction), G_OBJECT(exportAction)}) {
        if (object) { g_signal_handlers_disconnect_by_data(object, this); g_object_unref(object); }
    }
    if (active == this) active = nullptr;
    if (output) fclose(output);
}
void InputDiagnostics::attach(GtkWindow* value) {
    if (window || !GTK_IS_WINDOW(value)) throw std::runtime_error("Invalid diagnostic GTK window");
    window = GTK_WINDOW(g_object_ref(value));
    auto getAction = [&](const char* name) -> GAction* {
        auto* action = g_action_map_lookup_action(G_ACTION_MAP(value), name);
        return action ? G_ACTION(g_object_ref(action)) : nullptr;
    };
    openAction = getAction("open"); exportAction = getAction("export-as-pdf");
    for (auto* action: {openAction, exportAction}) {
        if (!action) continue;
        g_signal_connect(action, "notify::enabled", G_CALLBACK(+[](GObject* a, GParamSpec*, gpointer p) {
            auto* self = static_cast<InputDiagnostics*>(p);
            self->record(a == G_OBJECT(self->openAction) ? Phase::OpenEnabled : Phase::ExportEnabled);
        }), this);
        g_signal_connect(action, "activate", G_CALLBACK(+[](GSimpleAction* a, GVariant*, gpointer p) {
            auto* self = static_cast<InputDiagnostics*>(p);
            self->record(G_ACTION(a) == self->openAction ? Phase::OpenActivate : Phase::ExportActivate);
        }), this);
    }
    g_signal_connect_after(window, "set-focus", G_CALLBACK(+[](GtkWindow*, GtkWidget*, gpointer p) {
        static_cast<InputDiagnostics*>(p)->record(Phase::Focus);
    }), this);
    g_signal_connect_after(window, "grab-notify", G_CALLBACK(+[](GtkWidget*, gboolean, gpointer p) {
        static_cast<InputDiagnostics*>(p)->record(Phase::Grab);
    }), this);
    snooper = gtk_key_snooper_install(snoop, this);
#ifdef _WIN32
    gdk_window_add_filter(nullptr, nativeFilter, this);
#endif
    timer = g_timeout_add(1000, heartbeat, this);
    record(Phase::Attached);
}
bool InputDiagnostics::relevant(guint key, guint state) {
    if (key == GDK_KEY_Control_L || key == GDK_KEY_Control_R || key == GDK_KEY_Alt_L || key == GDK_KEY_Alt_R)
        return true;
    return ((key == GDK_KEY_e || key == GDK_KEY_E || key == GDK_KEY_o || key == GDK_KEY_O) &&
            (state & GDK_CONTROL_MASK)) || ((key == GDK_KEY_f || key == GDK_KEY_F) && (state & GDK_MOD1_MASK));
}
gboolean InputDiagnostics::propagate(GtkWindow* value, GdkEventKey* event) {
    // Dormant path performs no diagnostic inspection, allocation or output.
    if (!active) return gtk_window_propagate_key_event(value, event);
    const bool log = active->window == value && relevant(event->keyval, event->state | active->gtkModifiers);
    if (log) active->record(Phase::Before, event);
    const auto handled = gtk_window_propagate_key_event(value, event); // Exactly the original single call.
    if (log) active->record(Phase::After, event, nullptr, handled);
    return handled;
}
void InputDiagnostics::fileLoaded(GtkWindow* value) {
    if (active && active->window == value) active->record(Phase::FileLoaded);
}
gint InputDiagnostics::snoop(GtkWidget* target, GdkEventKey* key, gpointer p) {
    auto* self = static_cast<InputDiagnostics*>(p);
    const guint modifier = (key->keyval == GDK_KEY_Control_L || key->keyval == GDK_KEY_Control_R) ? GDK_CONTROL_MASK :
                           (key->keyval == GDK_KEY_Alt_L || key->keyval == GDK_KEY_Alt_R) ? GDK_MOD1_MASK : 0;
    if (key->type == GDK_KEY_PRESS) self->gtkModifiers |= modifier;
    // This observed down/up sequence affects only filtering. Retain an E/O/F
    // whose raw modifier mask is wrong; record() still writes the original mask.
    if (relevant(key->keyval, key->state | self->gtkModifiers)) self->record(Phase::GtkKey, key, target);
    if (key->type == GDK_KEY_RELEASE) self->gtkModifiers &= ~modifier;
    return FALSE; // Never consume or modify an event.
}
gboolean InputDiagnostics::heartbeat(gpointer p) {
    auto* self = static_cast<InputDiagnostics*>(p);
    self->record(Phase::Heartbeat);
    if (self->stopped) { self->timer = 0; return G_SOURCE_REMOVE; }
    return G_SOURCE_CONTINUE;
}
GdkFilterReturn InputDiagnostics::nativeFilter(GdkXEvent* native, GdkEvent*, gpointer p) {
#ifdef _WIN32
    const auto* message = static_cast<const MSG*>(native);
    if (message->message == WM_KEYDOWN || message->message == WM_KEYUP ||
        message->message == WM_SYSKEYDOWN || message->message == WM_SYSKEYUP) {
        auto* self = static_cast<InputDiagnostics*>(p);
        const guint code = static_cast<guint>(message->wParam);
        const guint modifier = (code == VK_CONTROL || code == VK_LCONTROL || code == VK_RCONTROL) ? GDK_CONTROL_MASK :
                               (code == VK_MENU || code == VK_LMENU || code == VK_RMENU) ? GDK_MOD1_MASK : 0;
        const bool down = message->message == WM_KEYDOWN || message->message == WM_SYSKEYDOWN;
        if (down) self->nativeModifiers |= modifier;
        const guint state = ((GetKeyState(VK_CONTROL) & 0x8000) ? GDK_CONTROL_MASK : 0) |
                            ((GetKeyState(VK_MENU) & 0x8000) ? GDK_MOD1_MASK : 0);
        if (code == VK_CONTROL || code == VK_LCONTROL || code == VK_RCONTROL || code == VK_MENU ||
            code == VK_LMENU || code == VK_RMENU || ((code == 'E' || code == 'O') && ((state | self->nativeModifiers) & GDK_CONTROL_MASK)) ||
            (code == 'F' && ((state | self->nativeModifiers) & GDK_MOD1_MASK)))
            self->record(Phase::NativeKey, nullptr, nullptr, -1, message->message, code, state);
        if (!down) self->nativeModifiers &= ~modifier;
    }
#endif
    return GDK_FILTER_CONTINUE;
}
void InputDiagnostics::record(Phase phase, GdkEventKey* key, GtkWidget* target, int handled,
                              guint nativeMessage, guint nativeCode, guint nativeState) noexcept {
    if (stopped) return;
    try {
        static const char* phases[] = {"started", "attached", "gtk-key", "propagate-before", "propagate-after",
            "focus", "grab", "open-enabled", "export-enabled", "open-activate", "export-activate", "file-loaded",
            "heartbeat", "native-key", "stopped", "truncated"};
        if (count >= MAX_RECORDS-1 || bytes >= MAX_BYTES-4096) phase = Phase::Truncated;
        std::ostringstream line;
        line << "{\"schema_version\":1,\"diagnostic_only\":true,\"sequence\":" << count+1
             << ",\"process_id\":" <<
#ifdef _WIN32
                GetCurrentProcessId()
#else
                getpid()
#endif
             << ",\"monotonic_us\":" << g_get_monotonic_time() << ",\"phase\":\"" << phases[static_cast<int>(phase)] << '"';
        if (phase != Phase::Truncated) {
            auto* focus = window ? gtk_window_get_focus(window) : nullptr;
            auto* group = window ? gtk_window_get_group(window) : nullptr;
            auto* grab = group ? gtk_window_group_get_current_grab(group) : nullptr;
            auto* device = key ? gdk_event_get_device(reinterpret_cast<GdkEvent*>(key)) : nullptr;
            auto* deviceGrab = group && device ? gtk_window_group_get_current_device_grab(group, device) : nullptr;
            auto boolean = [&](const char* name, bool b) { line << ",\"" << name << "\":" << (b ? "true" : "false"); };
            line << ",\"focus_type\":\"" << typeName(focus) << "\",\"grab_type\":\"" << typeName(grab)
                 << "\",\"device_grab_type\":\"" << typeName(deviceGrab) << "\",\"target_type\":\"" << typeName(target) << '"';
            boolean("focus_sensitive", focus && gtk_widget_is_sensitive(focus));
            boolean("focus_in_main", focus && gtk_widget_get_toplevel(focus) == GTK_WIDGET(window));
            boolean("focus_has_focus", focus && gtk_widget_has_focus(focus));
            boolean("grab_in_main", grab && gtk_widget_get_toplevel(grab) == GTK_WIDGET(window));
            boolean("grab_visible", grab && gtk_widget_get_visible(grab));
            boolean("grab_mapped", grab && gtk_widget_get_mapped(grab));
            boolean("grab_sensitive", grab && gtk_widget_is_sensitive(grab));
            boolean("device_grab_in_main", deviceGrab && gtk_widget_get_toplevel(deviceGrab) == GTK_WIDGET(window));
            boolean("target_in_main", target && gtk_widget_get_toplevel(target) == GTK_WIDGET(window));
            auto* eventWidget = key ? gtk_get_event_widget(reinterpret_cast<GdkEvent*>(key)) : nullptr;
            line << ",\"event_widget_type\":\"" << typeName(eventWidget) << '\"';
            boolean("event_in_main", eventWidget && gtk_widget_get_toplevel(eventWidget) == GTK_WIDGET(window));
            boolean("window_active", window && gtk_window_is_active(window));
            boolean("toplevel_focus", window && gtk_window_has_toplevel_focus(window));
            boolean("open_present", openAction != nullptr); boolean("export_present", exportAction != nullptr);
            boolean("open_enabled", openAction && g_action_get_enabled(openAction));
            boolean("export_enabled", exportAction && g_action_get_enabled(exportAction));
            if (key) line << ",\"event_type\":" << key->type << ",\"keyval\":" << key->keyval
                          << ",\"hardware_keycode\":" << key->hardware_keycode << ",\"state\":" << key->state;
            if (handled >= 0) boolean("handled", handled != 0);
            if (nativeMessage) line << ",\"native_message\":" << nativeMessage << ",\"native_code\":" << nativeCode
                                    << ",\"native_state\":" << nativeState;
        }
        line << "}\n";
        const auto text = line.str();
        if (text.size() > 4096 || bytes + text.size() > MAX_BYTES) { stopped = true; return; }
        ++count; bytes += text.size();
        if (fwrite(text.data(), 1, text.size(), output) != text.size() || fflush(output) != 0 || phase == Phase::Truncated)
            stopped = true;
    } catch (...) { stopped = true; } // A logging failure never alters input or the primary workflow failure.
}
