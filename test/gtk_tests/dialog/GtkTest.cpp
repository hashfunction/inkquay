//
// Created by hermannt on 11.06.23.
//

#include "GtkTest.h"

// Setting up the testing environment
void GtkTest::SetUp() {
    argn = 1;
    argv = new char*[2];
    argv[0] = g_strdup("inkquay_test");
    argv[1] = nullptr;
    app = gtk_application_new("com.trieflow.inkquay.test", G_APPLICATION_NON_UNIQUE);
    g_signal_connect(app, "activate", G_CALLBACK(applicationCallback), this);
    g_application_run(G_APPLICATION(app), argn, argv);
}

void GtkTest::TearDown() {
    // A test must not leave registered windows/application state for another test process.
    while (GList* windows = gtk_application_get_windows(app)) gtk_widget_destroy(GTK_WIDGET(windows->data));
    g_object_unref(app);
    g_free(argv[0]);
    delete[] argv;
}

// This the callback in which the actual test is run
// It needs to be a callback because it requires the GtkApplication to be running already.
void GtkTest::applicationCallback(GtkApplication* app, gpointer userData) {
    auto* test = static_cast<GtkTest*>(userData);

    // run the actual test
    test->runTest(app);

    // Quit the application to avoid waiting indefinitely fo the test to finish
    g_application_quit(G_APPLICATION(app));
}
