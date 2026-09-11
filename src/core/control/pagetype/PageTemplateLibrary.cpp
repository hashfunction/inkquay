// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include "PageTemplateLibrary.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <memory>
#include <set>
#include <stdexcept>

#include <glib.h>

#include "control/pagetype/PageTypeHandler.h"
#include "control/settings/PageTemplateSettings.h"
#include "util/PathUtil.h"

namespace {
using KeyFile = std::unique_ptr<GKeyFile, decltype(&g_key_file_free)>;
std::optional<std::string> read(const fs::path& path) {
    if (!fs::exists(path))
        return std::nullopt;
    std::ifstream file(path, std::ios::binary);
    if (!file)
        throw std::runtime_error("Cannot read template library: " + path.string());
    std::string text((std::istreambuf_iterator<char>(file)), {});
    if (file.bad())
        throw std::runtime_error("Cannot finish reading template library");
    return text;
}
std::string field(GKeyFile* key, const char* group, const char* name, bool required = true) {
    gchar* value = g_key_file_get_string(key, group, name, nullptr);
    if (!value) {
        if (required)
            throw std::runtime_error("Template library is missing a required field");
        return {};
    }
    std::string result(value);
    g_free(value);
    return result;
}
std::string nameKey(const std::string& input) {
    if (!g_utf8_validate(input.c_str(), static_cast<gssize>(input.size()), nullptr))
        throw std::runtime_error("Template name must be valid UTF-8");
    for (const char* character = input.c_str(); *character; character = g_utf8_next_char(character))
        if (g_unichar_iscntrl(g_utf8_get_char(character)))
            throw std::runtime_error("Template name must not contain control characters");
    gchar* value = g_strdup(input.c_str());
    g_strstrip(value);
    std::string trimmed(value);
    g_free(value);
    if (trimmed.empty() || trimmed.size() > 240 || trimmed != input ||
        trimmed.find_first_of("\r\n\t") != std::string::npos)
        throw std::runtime_error("Use a nonempty template name without leading/trailing spaces or control characters");
    gchar* folded = g_utf8_casefold(input.c_str(), -1);
    gchar* normalized = g_utf8_normalize(folded, -1, G_NORMALIZE_ALL_COMPOSE);
    std::string result(normalized);
    g_free(normalized);
    g_free(folded);
    return result;
}
void validate(const std::vector<PageTemplatePreset>& entries) {
    std::set<std::string> ids, names;
    for (const auto& preset: entries) {
        if (preset.id.empty() || preset.id == "library" || preset.id.size() > 100 ||
            preset.id.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_") !=
                    std::string::npos ||
            !ids.insert(preset.id).second)
            throw std::runtime_error("Template IDs must be unique letters, numbers, hyphens or underscores");
        if (!names.insert(nameKey(preset.name)).second)
            throw std::runtime_error("Template names must be unique");
        PageTemplateSettings parsed;
        if (!parsed.parse(preset.serializedTemplate) || parsed.toString() != preset.serializedTemplate ||
            !std::isfinite(parsed.getPageWidth()) || !std::isfinite(parsed.getPageHeight()) ||
            parsed.getPageWidth() <= 0 || parsed.getPageHeight() <= 0 || parsed.getPageWidth() > 20000 ||
            parsed.getPageHeight() > 20000 || parsed.getBackgroundType().isSpecial())
            throw std::runtime_error("Template is invalid or cannot be safely round-tripped");
    }
}
}  // namespace
PageTemplateLibrary::PageTemplateLibrary(fs::path user, fs::path builtIn):
        userFile(std::move(user)), builtInFile(std::move(builtIn)) {}
const PageTemplatePreset* PageTemplateLibrary::find(const std::string& id) const {
    auto it = std::find_if(entries.begin(), entries.end(), [&](const auto& p) { return p.id == id; });
    return it == entries.end() ? nullptr : &*it;
}
void PageTemplateLibrary::load() {
    writable = false;
    std::vector<PageTemplatePreset> next;
    std::optional<std::string> userBytes;
    auto loadFile = [&](const fs::path& path, bool builtIn) {
        auto bytes = read(path);
        if (!builtIn)
            userBytes = bytes;
        if (!bytes) {
            if (builtIn)
                throw std::runtime_error("Built-in template library is missing");
            return;
        }
        KeyFile key(g_key_file_new(), g_key_file_free);
        GError* error = nullptr;
        if (!g_key_file_load_from_data(key.get(), bytes->data(), bytes->size(), G_KEY_FILE_NONE, &error)) {
            std::string message(error->message);
            g_error_free(error);
            throw std::runtime_error(message);
        }
        if (!builtIn && g_key_file_get_integer(key.get(), "library", "version", nullptr) != 1)
            throw std::runtime_error("Unsupported template library version");
        gsize count;
        gchar** groups = g_key_file_get_groups(key.get(), &count);
        std::vector<std::string> groupNames;
        for (gsize i = 0; i < count; ++i) groupNames.emplace_back(groups[i]);
        g_strfreev(groups);
        for (const auto& group: groupNames) {
            if (group == "library")
                continue;
            PageTemplatePreset preset{group, field(key.get(), group.c_str(), "name"), {}, builtIn};
            if (builtIn) {
                PageTemplateSettings model;
                model.setCopyLastPageSettings(false);
                auto format = field(key.get(), group.c_str(), "format");
                PageType type(PageTypeHandler::getPageTypeFormatForString(format));
                if (PageTypeHandler::getStringForPageTypeFormat(type.format) != format)
                    throw std::runtime_error("Unknown built-in template format");
                type.config = field(key.get(), group.c_str(), "config", false);
                model.setBackgroundType(type);
                preset.serializedTemplate = model.toString();
            } else
                preset.serializedTemplate = field(key.get(), group.c_str(), "template");
            next.push_back(std::move(preset));
        }
    };
    loadFile(builtInFile, true);
    loadFile(userFile, false);
    validate(next);
    if (read(userFile) != userBytes)
        throw std::runtime_error("Template library changed while loading; retry loading");
    loadedBytes = userBytes;
    entries = std::move(next);
    writable = true;
}
void PageTemplateLibrary::persist(std::vector<PageTemplatePreset> next) {
    if (!writable)
        throw std::runtime_error("Template changes are disabled. Restore the library backup and retry loading.");
    validate(next);
    if (read(userFile) != loadedBytes) {
        writable = false;
        throw std::runtime_error("Template library changed on disk. Retry loading before making changes.");
    }
    KeyFile key(g_key_file_new(), g_key_file_free);
    g_key_file_set_integer(key.get(), "library", "version", 1);
    auto sorted = next;
    std::sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) { return a.id < b.id; });
    for (const auto& preset: sorted)
        if (!preset.builtIn) {
            g_key_file_set_string(key.get(), preset.id.c_str(), "name", preset.name.c_str());
            g_key_file_set_string(key.get(), preset.id.c_str(), "template", preset.serializedTemplate.c_str());
        }
    gsize length;
    gchar* data = g_key_file_to_data(key.get(), &length, nullptr);
    std::string bytes(data, length);
    g_free(data);
    fs::create_directories(userFile.parent_path());
    GError* error = nullptr;
    if (!g_file_set_contents_full(
                Util::toGFilename(userFile).c_str(), bytes.data(), static_cast<gssize>(bytes.size()),
                static_cast<GFileSetContentsFlags>(G_FILE_SET_CONTENTS_CONSISTENT | G_FILE_SET_CONTENTS_DURABLE), 0600,
                &error)) {
        std::string message(error->message);
        g_error_free(error);
        throw std::runtime_error(message);
    }
    loadedBytes = bytes;
    entries = std::move(next);
}
void PageTemplateLibrary::saveUserPreset(PageTemplatePreset preset) {
    if (preset.builtIn)
        throw std::runtime_error("Built-in templates cannot be replaced");
    auto next = entries;
    next.push_back(std::move(preset));
    persist(std::move(next));
}
bool PageTemplateLibrary::renameUserPreset(const std::string& id, const std::string& name) {
    if (!writable)
        throw std::runtime_error("Retry loading the template library before making changes");
    auto next = entries;
    for (auto& p: next)
        if (p.id == id) {
            if (p.builtIn)
                return false;
            p.name = name;
            persist(std::move(next));
            return true;
        }
    return false;
}
bool PageTemplateLibrary::removeUserPreset(const std::string& id) {
    if (!writable)
        throw std::runtime_error("Retry loading the template library before making changes");
    auto next = entries;
    auto it = std::find_if(next.begin(), next.end(), [&](const auto& p) { return p.id == id; });
    if (it == next.end() || it->builtIn)
        return false;
    next.erase(it);
    persist(std::move(next));
    return true;
}
