#include "geometry.hpp"

namespace acme {

// A widget that wraps a rectangle.
class Widget {
 public:
  // Number of rectangles tracked.
  int size() const { return count_; }

 private:
  int count_ = 0;
};

}  // namespace acme
