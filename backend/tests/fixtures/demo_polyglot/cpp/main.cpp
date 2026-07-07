#include "geometry.hpp"

// Free helper that doubles an area.
double doubled(const Rect& r) { return 2.0 * r.area(); }

int main() {
    Rect r;
    return static_cast<int>(doubled(r));
}
