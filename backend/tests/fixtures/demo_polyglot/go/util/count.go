package util

// Count returns the rune length of s.
func Count(s string) int {
	return len([]rune(s))
}
