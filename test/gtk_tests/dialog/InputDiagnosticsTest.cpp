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
                keys = {false, 0, 0};
                INPUT inputs[6]{};
                const WORD codes[] = {VK_CONTROL, VK_MENU, 'E', 'E', VK_MENU, VK_CONTROL};
                for (int i=0; i<6; ++i) { inputs[i].type=INPUT_KEYBOARD; inputs[i].ki.wVk=codes[i]; inputs[i].ki.dwFlags=i>=3 ? KEYEVENTF_KEYUP : 0; }
                ASSERT_EQ(GetAsyncKeyState(VK_CONTROL) & 0x8000, 0);
                ASSERT_EQ(GetAsyncKeyState(VK_MENU) & 0x8000, 0);
                const UINT inserted = SendInput(6, inputs, sizeof(INPUT));
                if (inserted != 6) {
                    // A failed fixture must release only its unmatched inserted key-downs.
                    std::vector<WORD> held;
                    for (UINT i=0; i<inserted && i<6; ++i) {
                        if (i<3) held.push_back(codes[i]);
                        else held.erase(std::remove(held.begin(), held.end(), codes[i]), held.end());
                    }
                    for (auto it=held.rbegin(); it!=held.rend(); ++it) {
                        INPUT release{}; release.type=INPUT_KEYBOARD; release.ki.wVk=*it; release.ki.dwFlags=KEYEVENTF_KEYUP;
                        SendInput(1, &release, sizeof(INPUT));
                    }
                }
                ASSERT_EQ(inserted, 6U);
                while (keys.activated == 0 && g_get_monotonic_time() < deadline) {
                    g_main_context_iteration(nullptr, false); g_usleep(1000);
                }
                EXPECT_EQ(keys.activated, 1);
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
