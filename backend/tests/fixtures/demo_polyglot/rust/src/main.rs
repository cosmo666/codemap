mod helpers;
mod util;

use crate::util::geometry::Point;

/// Entry point for the demo binary.
fn main() {
    let p = Point::origin();
    println!("{}", helpers::greet(p.norm()));
}
