use crate::helpers::greet;

/// A point on the plane.
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    /// The origin point.
    pub fn origin() -> Point {
        Point { x: 0.0, y: 0.0 }
    }

    /// Euclidean norm.
    pub fn norm(&self) -> f64 {
        let _ = greet(0.0);
        (self.x * self.x + self.y * self.y).sqrt()
    }
}
