// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include <fstream>

#include <glib.h>
#include <gtest/gtest.h>

#include "control/pagetype/PageTemplateLibrary.h"
#include "control/settings/PageTemplateSettings.h"

class PageTemplateLibraryTest: public ::testing::Test {
protected:
    fs::path dir;
    void SetUp() override {
        char* path = g_dir_make_tmp("inkquay-library-XXXXXX", nullptr);
        dir = path;
        g_free(path);
        std::ofstream(dir / "builtins.ini") << "[graph]\nname=Graph\nformat=graph\n";
    }
    void TearDown() override { fs::remove_all(dir); }
    std::string valid() {
        PageTemplateSettings model;
        model.setCopyLastPageSettings(false);
        return model.toString();
    }
};
TEST_F(PageTemplateLibraryTest, RoundTripsUnicodeAndProtectsBuiltins) {
    PageTemplateLibrary lib(dir / "user.ini", dir / "builtins.ini");
    lib.load();
    lib.saveUserPreset({"meeting", "Réunion 方格", valid(), false});
    PageTemplateLibrary loaded(dir / "user.ini", dir / "builtins.ini");
    loaded.load();
    ASSERT_EQ(loaded.presets().size(), 2U);
    EXPECT_EQ(loaded.presets().back().name, "Réunion 方格");
    EXPECT_EQ(loaded.presets().back().serializedTemplate, valid());
    EXPECT_FALSE(loaded.removeUserPreset("graph"));
    EXPECT_FALSE(loaded.renameUserPreset("graph", "Changed"));
    EXPECT_TRUE(loaded.renameUserPreset("meeting", "Review"));
    EXPECT_TRUE(loaded.removeUserPreset("meeting"));
}
TEST_F(PageTemplateLibraryTest, RejectsDuplicatesInvalidTemplatesAndBlankNames) {
    PageTemplateLibrary lib(dir / "user.ini", dir / "builtins.ini");
    lib.load();
    EXPECT_THROW(lib.saveUserPreset({"bad", "   ", valid(), false}), std::exception);
    EXPECT_THROW(lib.saveUserPreset({"bad", "graph", valid(), false}), std::exception);
    EXPECT_THROW(lib.saveUserPreset({"bad", "Bad", "xoj/template\nsize=nanx-1\n", false}), std::exception);
    EXPECT_THROW(lib.saveUserPreset({"bad", "Bad", "not a template", false}), std::exception);
    EXPECT_THROW(lib.saveUserPreset({"bad", std::string("Bad\0Name", 8), valid(), false}), std::exception);
    EXPECT_THROW(lib.saveUserPreset({"bad", "Bad\x01Name", valid(), false}), std::exception);
    lib.saveUserPreset({"one", "One", valid(), false});
    EXPECT_THROW(lib.saveUserPreset({"one", "Two", valid(), false}), std::exception);
    EXPECT_THROW(lib.saveUserPreset({"two", "ONE", valid(), false}), std::exception);
}
TEST_F(PageTemplateLibraryTest, FailedLoadLocksMutationsUntilExplicitRecovery) {
    std::ofstream(dir / "user.ini") << "[library]\nversion=99\n";
    PageTemplateLibrary lib(dir / "user.ini", dir / "builtins.ini");
    EXPECT_THROW(lib.load(), std::exception);
    EXPECT_THROW(lib.saveUserPreset({"new", "New", valid(), false}), std::exception);
    EXPECT_THROW(lib.removeUserPreset("new"), std::exception);
    std::ifstream f(dir / "user.ini");
    std::string text((std::istreambuf_iterator<char>(f)), {});
    EXPECT_EQ(text, "[library]\nversion=99\n");
    f.close();
    fs::remove(dir / "user.ini");
    lib.load();
    EXPECT_NO_THROW(lib.saveUserPreset({"new", "New", valid(), false}));
}
TEST_F(PageTemplateLibraryTest, DetectsExternalChangesWithoutLosingEitherCollection) {
    PageTemplateLibrary first(dir / "user.ini", dir / "builtins.ini");
    first.load();
    PageTemplateLibrary second(dir / "user.ini", dir / "builtins.ini");
    second.load();
    first.saveUserPreset({"one", "One", valid(), false});
    EXPECT_THROW(second.saveUserPreset({"two", "Two", valid(), false}), std::exception);
    second.load();
    EXPECT_EQ(second.presets().back().id, "one");
}
