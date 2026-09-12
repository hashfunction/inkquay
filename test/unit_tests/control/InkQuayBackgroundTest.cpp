// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include <array>
#include <barrier>
#include <stdexcept>
#include <thread>

#include <cairo.h>
#include <glib.h>
#include <gtest/gtest.h>
#include <pango/pangocairo.h>

#include "model/PageType.h"
#include "model/Text.h"
#include "util/Color.h"
#include "util/raii/CairoWrappers.h"
#include "view/TextView.h"
#include "view/background/BackgroundView.h"
TEST(InkQuayBackgroundTest, OriginalLayoutsRenderDistinctNonemptyVectorPatterns) {
    std::vector<std::string> hashes;
    for (int layout = 0; layout <= 4; ++layout) {
        auto* surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 600, 800);
        auto* cr = cairo_create(surface);
        PageType type(PageTypeFormat::Lined);
        type.config = "iq=" + std::to_string(layout);
        auto background = xoj::view::BackgroundView::createRuled(600, 800, Colors::white, type);
        background->draw(cr);
        cairo_surface_flush(surface);
        if (const char* evidence = g_getenv("INKQUAY_TEMPLATE_EVIDENCE_DIR")) {
            auto path = std::string(evidence) + "/layout-" + std::to_string(layout) + ".png";
            EXPECT_EQ(cairo_surface_write_to_png(surface, path.c_str()), CAIRO_STATUS_SUCCESS);
        }
        gchar* hash = g_compute_checksum_for_data(G_CHECKSUM_SHA256, cairo_image_surface_get_data(surface),
                                                  static_cast<gsize>(cairo_image_surface_get_stride(surface)) * 800);
        hashes.emplace_back(hash);
        g_free(hash);
        cairo_destroy(cr);
        cairo_surface_destroy(surface);
    }
    for (size_t i = 0; i < hashes.size(); ++i)
        for (size_t j = i + 1; j < hashes.size(); ++j) EXPECT_NE(hashes[i], hashes[j]);
}


namespace {
// The Windows application sets PANGOCAIRO_BACKEND=fc before creating any UI.
// Use the same backend per test thread without changing process environment.
class FontConfigContext {
public:
    FontConfigContext(): previous(pango_cairo_font_map_get_default()) {
        g_object_ref(previous);
        auto* map = pango_cairo_font_map_new_for_font_type(CAIRO_FONT_TYPE_FT);
        if (!map)
            throw std::runtime_error("The production FontConfig backend is unavailable");
        pango_cairo_font_map_set_default(PANGO_CAIRO_FONT_MAP(map));
        g_object_unref(map);
    }
    ~FontConfigContext() {
        pango_cairo_font_map_set_default(PANGO_CAIRO_FONT_MAP(previous));
        g_object_unref(previous);
    }

private:
    PangoFontMap* previous;
};

std::string imageHash(cairo_surface_t* surface) {
    cairo_surface_flush(surface);
    auto* hash = g_compute_checksum_for_data(G_CHECKSUM_SHA256, cairo_image_surface_get_data(surface),
                                             static_cast<gsize>(cairo_image_surface_get_stride(surface)) *
                                                     static_cast<gsize>(cairo_image_surface_get_height(surface)));
    std::string result(hash);
    g_free(hash);
    return result;
}

void drawTemplate(cairo_t* cr, int layout, double scale) {
    cairo_scale(cr, scale, scale);
    PageType type(PageTypeFormat::Lined);
    type.config = "iq=" + std::to_string(layout);
    auto background = xoj::view::BackgroundView::createRuled(600, 800, Colors::white, type);
    background->draw(cr);
}

std::string templateHash(int layout, double scale) {
    xoj::util::CairoSurfaceSPtr surface(cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 600, 800), xoj::util::adopt);
    xoj::util::CairoSPtr cr(cairo_create(surface.get()), xoj::util::adopt);
    drawTemplate(cr.get(), layout, scale);
    EXPECT_EQ(cairo_status(cr.get()), CAIRO_STATUS_SUCCESS);
    return imageHash(surface.get());
}
}  // namespace

TEST(InkQuayBackgroundTest, LabelsMatchDocumentTextFontAndBaseline) {
    FontConfigContext fonts;
    const std::array<const char*, 4> labels = {"Meeting / Date", "Topic / Date", "Storyboard / Project",
                                               "Practice / Instrument / Tempo"};
    for (double scale: {0.5, 1.0, 1.5}) {
        SCOPED_TRACE(scale);
        for (int layout = 1; layout <= 4; ++layout) {
            SCOPED_TRACE(layout);
            xoj::util::CairoSurfaceSPtr actual(cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 900, 1200),
                                               xoj::util::adopt);
            xoj::util::CairoSurfaceSPtr reference(cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 900, 1200),
                                                  xoj::util::adopt);
            xoj::util::CairoSPtr cr(cairo_create(actual.get()), xoj::util::adopt);
            xoj::util::CairoSPtr expected(cairo_create(reference.get()), xoj::util::adopt);
            drawTemplate(cr.get(), layout, scale);
            cairo_set_source_rgb(expected.get(), 1, 1, 1);
            cairo_paint(expected.get());
            cairo_scale(expected.get(), scale, scale);
            Text text;
            text.setFont(XojFont("Sans", 10));
            text.setText(labels[static_cast<size_t>(layout - 1)]);
            text.setColor(Color(95, 125, 132));
            auto metrics = xoj::view::TextView::initPango(expected.get(), &text);
            pango_layout_set_text(metrics.get(), text.getText().c_str(), -1);
            text.setX(36);
            text.setY((layout == 3 ? 34 : 36) -
                      static_cast<double>(pango_layout_get_baseline(metrics.get())) / PANGO_SCALE);
            xoj::view::TextView(&text).draw(xoj::view::Context::createDefault(expected.get()));
            cairo_surface_flush(actual.get());
            cairo_surface_flush(reference.get());
            auto* a = cairo_image_surface_get_data(actual.get());
            auto* b = cairo_image_surface_get_data(reference.get());
            int differing = 0, ink = 0;
            for (int y = static_cast<int>(18 * scale); y < static_cast<int>(44 * scale); ++y) {
                for (int x = static_cast<int>(32 * scale) * 4; x < static_cast<int>(320 * scale) * 4; ++x) {
                    size_t offset =
                            static_cast<size_t>(y) * static_cast<size_t>(cairo_image_surface_get_stride(actual.get())) +
                            static_cast<size_t>(x);
                    differing += a[offset] != b[offset];
                    ink += b[offset] != 255;
                }
            }
            EXPECT_GT(ink, 100) << "A blank label cannot satisfy the font regression";
            EXPECT_EQ(differing, 0)
                    << "Template labels must use the same native font rendering and baseline as document text";
            // Cornell's vertical cue rule remains continuous below the label area.
            if (layout == 2)
                EXPECT_NE(a[static_cast<int>(120 * scale) * cairo_image_surface_get_stride(actual.get()) +
                            static_cast<int>(166 * scale) * 4],
                          255);
        }
    }
}

TEST(InkQuayBackgroundTest, ConcurrentTemplateRenderingMatchesSerialWhileUiDrawsText) {
    constexpr int count = 24;
    std::array<std::array<std::string, count>, 2> rendered;
    std::barrier start(3);
    auto render = [&](int worker) {
        FontConfigContext fonts;
        for (int i = 0; i < count; ++i) {
            start.arrive_and_wait();
            // Cold, distinct scaled fonts exercise the actual glyph backend,
            // including the first Cornell insertion seen in the Windows crash.
            rendered[static_cast<size_t>(worker)][static_cast<size_t>(i)] =
                    templateHash(1 + (i + worker) % 4, 0.55 + 0.009 * (i * 2 + worker));
        }
    };
    std::thread first(render, 0), second(render, 1);
    for (int i = 0; i < count; ++i) {
        xoj::util::CairoSurfaceSPtr surface(cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 120, 80), xoj::util::adopt);
        xoj::util::CairoSPtr cr(cairo_create(surface.get()), xoj::util::adopt);
        start.arrive_and_wait();
        // Same toy-font path and starting size as the actual sidebar stack.
        cairo_select_font_face(cr.get(), "Sans", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
        cairo_set_font_size(cr.get(), 16.0 + i * 0.017);
        auto number = std::to_string(i + 1);
        cairo_text_extents_t extents;
        cairo_text_extents(cr.get(), number.c_str(), &extents);
        cairo_move_to(cr.get(), 20, 30);
        cairo_show_text(cr.get(), number.c_str());
        EXPECT_EQ(cairo_status(cr.get()), CAIRO_STATUS_SUCCESS);
    }
    first.join();
    second.join();
    FontConfigContext fonts;
    for (int worker = 0; worker < 2; ++worker)
        for (int i = 0; i < count; ++i)
            EXPECT_EQ(rendered[static_cast<size_t>(worker)][static_cast<size_t>(i)],
                      templateHash(1 + (i + worker) % 4, 0.55 + 0.009 * (i * 2 + worker)));
}
