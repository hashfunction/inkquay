// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#include "InkQuayBackgroundView.h"

#include <algorithm>

#include "model/BackgroundConfig.h"
#include "util/Color.h"
using namespace xoj::view;
InkQuayBackgroundView::InkQuayBackgroundView(double w, double h, Color color, const BackgroundConfig& config,
                                             int layout):
        OneColorBackgroundView(w, h, color, config, 0.65, Color(95, 125, 132), Color(168, 194, 199)), layout(layout) {}
void InkQuayBackgroundView::draw(cairo_t* cr) const {
    PlainBackgroundView::draw(cr);
    cairo_save(cr);
    Util::cairo_set_source_rgbi(cr, foregroundColor);
    cairo_set_line_width(cr, lineWidth);
    // Coordinates scale with the page, so all four templates work with user-selected paper sizes.
    cairo_scale(cr, pageWidth / 600.0, pageHeight / 800.0);
    auto line = [&](double x, double y, double endX, double endY) {
        cairo_move_to(cr, x, y);
        cairo_line_to(cr, endX, endY);
    };
    auto label = [&](double x, double y, const char* text) {
        cairo_move_to(cr, x, y);
        cairo_show_text(cr, text);
    };
    cairo_select_font_face(cr, "Sans", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr, 10);
    if (layout == 1) {
        label(36, 36, "Meeting / Date");
        line(36, 50, 564, 50);
        label(36, 72, "Attendees / Purpose");
        line(36, 104, 564, 104);
        label(36, 128, "Discussion");
        for (int y = 152; y < 552; y += 24) line(36, y, 564, y);
        label(36, 580, "Decisions");
        line(36, 604, 564, 604);
        line(36, 628, 564, 628);
        label(36, 664, "Action / Owner / Due");
        for (int y = 688; y <= 760; y += 24) line(36, y, 564, y);
        line(398, 672, 398, 760);
        line(494, 672, 494, 760);
    } else if (layout == 2) {
        label(36, 36, "Topic / Date");
        line(36, 56, 564, 56);
        label(36, 80, "Cues");
        label(184, 80, "Notes");
        line(166, 56, 166, 648);
        for (int y = 104; y < 648; y += 24) line(184, y, 564, y);
        line(36, 648, 564, 648);
        label(36, 674, "Summary");
        for (int y = 698; y <= 746; y += 24) line(36, y, 564, y);
    } else if (layout == 3) {
        label(36, 34, "Storyboard / Project");
        for (int row = 0; row < 3; ++row)
            for (int col = 0; col < 2; ++col) {
                double x = 36 + col * 276, y = 64 + row * 240;
                cairo_rectangle(cr, x, y, 252, 141.75);
                line(x, y + 168, x + 252, y + 168);
                line(x, y + 192, x + 252, y + 192);
            }
    } else {
        label(36, 36, "Practice / Instrument / Tempo");
        for (int staff = 0; staff < 8; ++staff) {
            double y = 76 + staff * 84;
            for (int n = 0; n < 5; ++n) line(54, y + n * 7, 564, y + n * 7);
            line(54, y, 54, y + 28);
            line(564, y, 564, y + 28);
        }
    }
    cairo_stroke(cr);
    cairo_restore(cr);
}
