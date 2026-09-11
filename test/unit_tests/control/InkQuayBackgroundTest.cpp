// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include <cairo.h>
#include <glib.h>
#include <gtest/gtest.h>

#include "model/PageType.h"
#include "util/Color.h"
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
