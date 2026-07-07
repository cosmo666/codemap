#pragma once

// An axis-aligned rectangle.
class Rect {
public:
    // Computes the area.
    double area() const { return width * height; }

    double width = 0.0;
    double height = 0.0;
};
