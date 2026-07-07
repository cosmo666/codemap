package util

import "strings"

// Upper returns s upper-cased.
func Upper(s string) string {
	return strings.ToUpper(s)
}

// Labeler renders labels.
type Labeler struct {
	Prefix string
}

// Label renders one label.
func (l Labeler) Label(s string) string {
	return l.Prefix + s
}
