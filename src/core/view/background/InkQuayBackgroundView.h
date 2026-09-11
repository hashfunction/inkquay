// Copyright 2026 Trieflow LLC. GPL-2.0-or-later.
#pragma once
#include "OneColorBackgroundView.h"
namespace xoj::view {
// iq=1..4 augments a standard ruling format, retaining a readable fallback in other .xopp readers.
class InkQuayBackgroundView final: public OneColorBackgroundView {
public:
    InkQuayBackgroundView(double width, double height, Color color, const BackgroundConfig& config, int layout);
    void draw(cairo_t* cr) const override;

private:
    int layout;
};
}  // namespace xoj::view
