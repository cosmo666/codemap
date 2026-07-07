package main

import (
	"fmt"

	"example.com/demo/util"
)

// Entry point for the demo CLI.
func main() {
	fmt.Println(util.Upper("codemap"), util.Count("codemap"))
}
