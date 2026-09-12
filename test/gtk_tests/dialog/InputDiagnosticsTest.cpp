// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include <algorithm>
#include <memory>
#include <utility>
#include <vector>
#include <filesystem>
#ifdef _WIN32
#include <windows.h>
#include <gdk/gdkwin32.h>
#endif
#include <fstream>
#include <string>

#include "gui/inputdevices/InputDiagnostics.h"
#include "GtkTest.h"

namespace {
std::string read(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(stream), {}};
}
struct Keys { bool consume = false; int child = 0; int activated = 0; };
#ifdef _WIN32
unsigned maximumCounter(const std::string& text, const std::string& field) {
    const auto prefix = "\"" + field + "\":";
    unsigned result = 0;
    for (size_t pos=0; (pos=text.find(prefix, pos)) != std::string::npos; pos += prefix.size())
        result = std::max(result, static_cast<unsigned>(std::stoul(text.substr(pos+prefix.size()))));
    return result;
}
#endif
}
class InputDiagnosticsTest: public GtkTest {
    void runTest(GtkApplication* app) override {
        namespace fs = std::filesystem;
        gchar* temporary = g_dir_make_tmp("scriblark-input-test-XXXXXX", nullptr);
        const auto directory = fs::canonical(temporary); g_free(temporary);
        const auto path = directory / "trace.jsonl";
        auto* window = GTK_WINDOW(gtk_application_window_new(app));
        gtk_window_set_title(window, "PRIVATE DOCUMENT PATH");
        auto* child = gtk_drawing_area_new();
        gtk_widget_set_can_focus(child, true);
        gtk_widget_set_name(child, "PRIVATE WIDGET TEXT");
        gtk_container_add(GTK_CONTAINER(window), child);
        Keys keys;
        g_signal_connect(child, "key-press-event", G_CALLBACK(+[](GtkWidget*, GdkEventKey*, gpointer p) -> gboolean {
            auto& k = *static_cast<Keys*>(p); ++k.child; return k.consume;
        }), &keys);
        g_signal_connect(window, "key-press-event", G_CALLBACK(+[](GtkWidget* w, GdkEventKey* e, gpointer) -> gboolean {
            return InputDiagnostics::propagate(GTK_WINDOW(w), e);
        }), nullptr);
        auto* action = g_simple_action_new("export-as-pdf", nullptr);
        g_signal_connect(action, "activate", G_CALLBACK(+[](GSimpleAction*, GVariant*, gpointer p) {
            ++static_cast<Keys*>(p)->activated;
        }), &keys);
        g_action_map_add_action(G_ACTION_MAP(window), G_ACTION(action));
        auto* open = g_simple_action_new("open", nullptr);
        g_action_map_add_action(G_ACTION_MAP(window), G_ACTION(open));
        const char* accels[] = {"<Control><Alt>e", nullptr};
        gtk_application_set_accels_for_action(app, "win.export-as-pdf", accels);
        gtk_widget_show_all(GTK_WIDGET(window));
        gtk_widget_grab_focus(child);
        for (int i=0; i<50; ++i) { g_main_context_iteration(nullptr, false); g_usleep(1000); }
        ASSERT_EQ(gtk_window_get_focus(window), child);
        auto deliver = [&] {
            GdkEvent* event = gdk_event_new(GDK_KEY_PRESS);
            event->key.window = GDK_WINDOW(g_object_ref(gtk_widget_get_window(GTK_WIDGET(window))));
            event->key.keyval = GDK_KEY_e;
            event->key.state = GdkModifierType(GDK_CONTROL_MASK | GDK_MOD1_MASK);
            event->key.string = g_strdup("PRIVATE TYPED TEXT");
            event->key.length = 18;
            GdkKeymapKey* map = nullptr; gint count = 0;
            ASSERT_TRUE(gdk_keymap_get_entries_for_keyval(gdk_keymap_get_for_display(gtk_widget_get_display(child)), GDK_KEY_e, &map, &count));
            event->key.hardware_keycode = static_cast<guint16>(map[0].keycode); event->key.group = static_cast<guint8>(map[0].group); g_free(map);
            gdk_event_set_device(event, gdk_seat_get_keyboard(gdk_display_get_default_seat(gtk_widget_get_display(child))));
            gtk_main_do_event(event);
            gdk_event_free(event);
        };
        // Actual focused child and GTK's default accelerator retain the same effects in both modes.
        for (bool enabled: {false, true}) {
            std::unique_ptr<InputDiagnostics> trace;
            if (enabled) { trace = std::make_unique<InputDiagnostics>(path); trace->attach(window); }
            if (enabled) {
                // The actual failed Windows trace exhausted 512 rows on filename
                // modifier transitions before either export. Exercise a real GTK
                // entry in another modal window, then retain both actual actions.
                auto* chooser = GTK_WINDOW(gtk_window_new(GTK_WINDOW_TOPLEVEL));
                gtk_window_set_transient_for(chooser, window);
                gtk_window_set_modal(chooser, true);
                auto* entry = gtk_entry_new();
                gtk_container_add(GTK_CONTAINER(chooser), entry);
                gtk_widget_show_all(GTK_WIDGET(chooser));
                gtk_widget_grab_focus(entry);
                ASSERT_EQ(gtk_window_get_focus(chooser), entry);
                for (int i=0; i<300; ++i) {
                    for (auto kind: {GDK_KEY_PRESS, GDK_KEY_RELEASE}) {
                        auto* event = gdk_event_new(kind);
                        event->key.window = GDK_WINDOW(g_object_ref(gtk_widget_get_window(GTK_WIDGET(chooser))));
                        event->key.keyval = GDK_KEY_Control_L;
                        event->key.state = kind == GDK_KEY_PRESS ? 0 : GDK_CONTROL_MASK;
                        gdk_event_set_device(event, gdk_seat_get_keyboard(gdk_display_get_default_seat(gtk_widget_get_display(entry))));
                        gtk_main_do_event(event); gdk_event_free(event);
                    }
                }
                gtk_widget_destroy(GTK_WIDGET(chooser));
                gtk_window_present(window); gtk_widget_grab_focus(child);
                keys = {false, 0, 0}; deliver(); deliver();
                EXPECT_EQ(keys.child, 2);
                EXPECT_EQ(keys.activated, 2);
                const auto afterFlood = read(path);
                EXPECT_EQ(afterFlood.find("\"phase\":\"truncated\""), std::string::npos);
                EXPECT_NE(afterFlood.find("\"phase\":\"modifier-suppressed\""), std::string::npos);
                EXPECT_NE(afterFlood.find("\"omitted_gtk_press\":296"), std::string::npos);
                EXPECT_NE(afterFlood.find("\"omitted_gtk_release\":296"), std::string::npos);
                EXPECT_NE(afterFlood.find("\"observed_gtk_modifiers\":0"), std::string::npos);
                const auto firstAction = afterFlood.find("\"phase\":\"export-activate\"");
                ASSERT_NE(firstAction, std::string::npos);
                EXPECT_NE(afterFlood.find("\"phase\":\"export-activate\"", firstAction + 1), std::string::npos);
                // Exercise the two production propagation budgets as well; the
                // child still receives every event and consumes exactly once.
                keys = {true, 0, 0};
                for (int i=0; i<300; ++i) {
                    for (auto kind: {GDK_KEY_PRESS, GDK_KEY_RELEASE}) {
                        auto* event = gdk_event_new(kind);
                        event->key.window = GDK_WINDOW(g_object_ref(gtk_widget_get_window(GTK_WIDGET(window))));
                        event->key.keyval = GDK_KEY_Control_L;
                        event->key.state = kind == GDK_KEY_PRESS ? 0 : GDK_CONTROL_MASK;
                        gdk_event_set_device(event, gdk_seat_get_keyboard(gdk_display_get_default_seat(gtk_widget_get_display(child))));
                        if (kind == GDK_KEY_PRESS) EXPECT_TRUE(InputDiagnostics::propagate(window, &event->key));
                        else InputDiagnostics::propagate(window, &event->key);
                        gdk_event_free(event);
                    }
                }
                EXPECT_EQ(keys.child, 300);
                keys = {false, 0, 0}; deliver(); deliver();
                EXPECT_EQ(keys.activated, 2);
                const auto afterPropagationFlood = read(path);
                EXPECT_EQ(afterPropagationFlood.find("\"phase\":\"truncated\""), std::string::npos);
                EXPECT_NE(afterPropagationFlood.find("\"omitted_before_press\":296"), std::string::npos);
                EXPECT_NE(afterPropagationFlood.find("\"omitted_after_press\":296"), std::string::npos);
            }
            for (bool consume: {true, false}) {
                keys = {consume, 0, 0}; deliver();
                EXPECT_EQ(keys.child, 1);
                EXPECT_EQ(keys.activated, consume ? 0 : 1);
            }
#ifdef _WIN32
            if (enabled) {
                // Real native input into our own GTK window also crosses the production GDK filter.
                gtk_window_present(window);
                HWND handle = static_cast<HWND>(gdk_win32_window_get_handle(gtk_widget_get_window(GTK_WIDGET(window))));
                SetForegroundWindow(handle);
                const auto deadline = g_get_monotonic_time() + 3000000;
                while (GetForegroundWindow() != handle && g_get_monotonic_time() < deadline) {
                    g_main_context_iteration(nullptr, false); g_usleep(1000);
                }
                ASSERT_EQ(GetForegroundWindow(), handle);
                gtk_widget_grab_focus(child);
                auto sendOwned = [&](std::vector<INPUT>& inputs) {
                    ASSERT_EQ(GetForegroundWindow(), handle);
                    ASSERT_EQ(gtk_window_get_focus(window), child);
                    ASSERT_EQ(GetAsyncKeyState(VK_CONTROL) & 0x8000, 0);
                    ASSERT_EQ(GetAsyncKeyState(VK_MENU) & 0x8000, 0);
                    const UINT inserted = SendInput(static_cast<UINT>(inputs.size()), inputs.data(), sizeof(INPUT));
                    if (inserted != inputs.size()) {
                        // A failed fixture releases only its unmatched inserted downs.
                        std::vector<WORD> held;
                        for (UINT i=0; i<inserted && i<inputs.size(); ++i) {
                            const auto code = inputs[i].ki.wVk;
                            if (!(inputs[i].ki.dwFlags & KEYEVENTF_KEYUP)) held.push_back(code);
                            else held.erase(std::remove(held.begin(), held.end(), code), held.end());
                        }
                        for (auto it=held.rbegin(); it!=held.rend(); ++it) {
                            INPUT release{}; release.type=INPUT_KEYBOARD; release.ki.wVk=*it; release.ki.dwFlags=KEYEVENTF_KEYUP;
                            SendInput(1, &release, sizeof(INPUT));
                        }
                    }
                    ASSERT_EQ(inserted, inputs.size());
                };
                keys = {true, 0, 0};
                std::vector<INPUT> modifierFlood(600);
                for (unsigned i=0; i<modifierFlood.size(); ++i) {
                    modifierFlood[i].type=INPUT_KEYBOARD; modifierFlood[i].ki.wVk=VK_CONTROL;
                    modifierFlood[i].ki.dwFlags=i%2 ? KEYEVENTF_KEYUP : 0;
                }
                sendOwned(modifierFlood);
                ASSERT_FALSE(HasFatalFailure());
                const auto floodDeadline = g_get_monotonic_time() + 3000000;
                while ((keys.child < 300 || (GetAsyncKeyState(VK_CONTROL) & 0x8000)) && g_get_monotonic_time() < floodDeadline) {
                    g_main_context_iteration(nullptr, false); g_usleep(1000);
                }
                ASSERT_EQ(keys.child, 300);
                keys = {false, 0, 0};
                std::vector<INPUT> exports(12);
                const WORD codes[] = {VK_CONTROL, VK_MENU, 'E', 'E', VK_MENU, VK_CONTROL};
                for (unsigned i=0; i<exports.size(); ++i) {
                    exports[i].type=INPUT_KEYBOARD; exports[i].ki.wVk=codes[i%6];
                    exports[i].ki.dwFlags=i%6>=3 ? KEYEVENTF_KEYUP : 0;
                }
                sendOwned(exports);
                ASSERT_FALSE(HasFatalFailure());
                const auto exportDeadline = g_get_monotonic_time() + 3000000;
                while ((keys.activated < 2 || (GetAsyncKeyState(VK_CONTROL) & 0x8000) || (GetAsyncKeyState(VK_MENU) & 0x8000)) && g_get_monotonic_time() < exportDeadline) {
                    g_main_context_iteration(nullptr, false); g_usleep(1000);
                }
                EXPECT_EQ(keys.activated, 2);
                const auto nativeFlood = read(path);
                EXPECT_EQ(nativeFlood.find("\"phase\":\"truncated\""), std::string::npos);
                EXPECT_NE(nativeFlood.find("\"modifier_stream\":\"native-key\""), std::string::npos);
                EXPECT_GE(maximumCounter(nativeFlood, "omitted_native_press"), 296U);
                EXPECT_GE(maximumCounter(nativeFlood, "omitted_native_release"), 296U);
            }
#endif
            if (!enabled) EXPECT_FALSE(fs::exists(path));
            else {
                g_simple_action_set_enabled(action, false);
                InputDiagnostics::fileLoaded(window);
                // Observe an actual GTK key sequence whose E event lost its raw
                // modifier mask. Diagnostic filtering must not conceal that evidence.
                keys.consume=true;
                for (auto [code, kind]: {std::pair{GDK_KEY_Control_L, GDK_KEY_PRESS},
                                        std::pair{GDK_KEY_e, GDK_KEY_PRESS},
                                        std::pair{GDK_KEY_Control_L, GDK_KEY_RELEASE}}) {
                    GdkEvent* lost = gdk_event_new(kind);
                    lost->key.window = GDK_WINDOW(g_object_ref(gtk_widget_get_window(GTK_WIDGET(window))));
                    lost->key.keyval=code; lost->key.state=GdkModifierType(0);
                    gdk_event_set_device(lost, gdk_seat_get_keyboard(gdk_display_get_default_seat(gtk_widget_get_display(child))));
                    gtk_main_do_event(lost);gdk_event_free(lost);
                }
                EXPECT_NE(read(path).find("\"keyval\":101,\"hardware_keycode\":0,\"state\":0"), std::string::npos);
                GdkEventKey irrelevant{}; irrelevant.type=GDK_KEY_PRESS; irrelevant.keyval=GDK_KEY_z;
                const auto beforeUnrelated = read(path);
                InputDiagnostics::propagate(window, &irrelevant);
                EXPECT_EQ(read(path), beforeUnrelated);
                const auto before = g_get_monotonic_time();
                while (g_get_monotonic_time()-before < 1100000) { g_main_context_iteration(nullptr, false); g_usleep(1000); }
            }
        }
        const auto text = read(path);
        EXPECT_NE(text.find("\"phase\":\"gtk-key\""), std::string::npos);
        EXPECT_NE(text.find("\"phase\":\"propagate-after\""), std::string::npos);
        EXPECT_NE(text.find("\"handled\":true"), std::string::npos);
        EXPECT_NE(text.find("\"handled\":false"), std::string::npos);
        EXPECT_NE(text.find("\"phase\":\"export-activate\""), std::string::npos);
        EXPECT_NE(text.find("\"phase\":\"file-loaded\""), std::string::npos);
        EXPECT_NE(text.find("\"phase\":\"heartbeat\""), std::string::npos);
        EXPECT_NE(text.find("GtkDrawingArea"), std::string::npos);
        EXPECT_EQ(text.find("PRIVATE"), std::string::npos);
#ifdef _WIN32
        EXPECT_NE(text.find("\"phase\":\"native-key\""), std::string::npos);
#endif
        EXPECT_THROW(InputDiagnostics duplicate(path), std::runtime_error);
        EXPECT_EQ(read(path), text);
        EXPECT_THROW(InputDiagnostics directoryOutput(directory), std::runtime_error);
        EXPECT_THROW(InputDiagnostics relative("relative.jsonl"), std::runtime_error);
        EXPECT_THROW(InputDiagnostics absent(directory / "absent" / "trace.jsonl"), std::runtime_error);
#ifndef _WIN32
        fs::create_directory_symlink(directory, directory / "redirect");
        EXPECT_THROW(InputDiagnostics redirected(directory / "redirect" / "new.jsonl"), std::runtime_error);
        fs::create_symlink(path, directory / "existing-link.jsonl");
        EXPECT_THROW(InputDiagnostics linked(directory / "existing-link.jsonl"), std::runtime_error);
        EXPECT_EQ(read(path), text);
#endif
        // Optional test-only retained bytes allow the actual PowerShell reader to replay the native writer.
        if (const char* retained = g_getenv("SCRIBLARK_INPUT_TEST_RECORD")) {
            fs::copy_file(path, fs::path(retained), fs::copy_options::none);
        }
        {
            InputDiagnostics cap(directory / "bounded.jsonl"); cap.attach(window);
            for (int i=0; i<600; ++i) InputDiagnostics::fileLoaded(window);
        }
        auto bounded = read(directory / "bounded.jsonl");
        EXPECT_EQ(std::count(bounded.begin(), bounded.end(), '\n'), 512);
        EXPECT_LE(bounded.size(), 1048576U);
        EXPECT_NE(bounded.rfind("\"phase\":\"truncated\""), std::string::npos);
        EXPECT_EQ(bounded.find("PRIVATE"), std::string::npos);
        gtk_widget_destroy(GTK_WIDGET(window));
        g_object_unref(action); g_object_unref(open);
        fs::remove_all(directory);
    }
};
TEST_F(InputDiagnosticsTest, ObservesActualGtkWithoutChangingKeyHandling) {}
