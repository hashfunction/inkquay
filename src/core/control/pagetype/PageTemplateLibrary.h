// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#pragma once
#include <optional>
#include <string>
#include <vector>

#include "filesystem.h"

struct PageTemplatePreset {
    std::string id, name, serializedTemplate;
    bool builtIn = false;
};

class PageTemplateLibrary {
public:
    PageTemplateLibrary(fs::path userFile, fs::path builtInFile);
    void load();
    const std::vector<PageTemplatePreset>& presets() const { return entries; }
    const PageTemplatePreset* find(const std::string& id) const;
    void saveUserPreset(PageTemplatePreset preset);
    bool renameUserPreset(const std::string& id, const std::string& name);
    bool removeUserPreset(const std::string& id);

private:
    void persist(std::vector<PageTemplatePreset> next);
    fs::path userFile, builtInFile;
    std::vector<PageTemplatePreset> entries;
    std::optional<std::string> loadedBytes;
    bool writable = false;
};
