//go:build !windows

package main

import (
	"fmt"
	"os"
)

func showSplash(text string) func() {
	fmt.Fprintln(os.Stderr, text)
	return func() {}
}

func fail(text string) { fmt.Fprintln(os.Stderr, text) }
