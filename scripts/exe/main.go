// CORBELscore.exe: one file to share. It carries the whole program (the
// Electron runtime and the app) as a zip. The first run unpacks it to
// %LOCALAPPDATA%\CORBELscore\app-<version> (a few seconds, with a small
// "Setting up" window); every run after that starts straight away. Nothing
// is installed system-wide and no administrator rights are needed.
package main

import (
	"archive/zip"
	"bytes"
	_ "embed"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

//go:embed payload.zip
var payload []byte

// Set at build time: a short hash of the payload, so a new build unpacks fresh.
var version = "dev"

func appExe() string {
	if runtime.GOOS == "windows" {
		return "CORBELscore.exe"
	}
	return "corbelscore"
}

func baseDir() (string, error) {
	if d := os.Getenv("CORBEL_HOME"); d != "" { // tests and portable use
		return d, nil
	}
	if runtime.GOOS == "windows" {
		if d := os.Getenv("LOCALAPPDATA"); d != "" {
			return filepath.Join(d, "CORBELscore"), nil
		}
	}
	d, err := os.UserCacheDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(d, "CORBELscore"), nil
}

// unpack writes the payload into dir, refusing any path that would land outside it.
func unpack(dir string) error {
	zr, err := zip.NewReader(bytes.NewReader(payload), int64(len(payload)))
	if err != nil {
		return err
	}
	root := filepath.Clean(dir) + string(os.PathSeparator)
	for _, f := range zr.File {
		target := filepath.Join(dir, filepath.FromSlash(f.Name))
		if !strings.HasPrefix(target, root) {
			return fmt.Errorf("bad path in package: %s", f.Name)
		}
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		mode := f.Mode().Perm()
		if mode == 0 {
			mode = 0o644
		}
		rc, err := f.Open()
		if err != nil {
			return err
		}
		out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, mode)
		if err != nil {
			rc.Close()
			return err
		}
		_, err = io.Copy(out, rc)
		rc.Close()
		if cerr := out.Close(); err == nil {
			err = cerr
		}
		if err != nil {
			return err
		}
	}
	return nil
}

func prepare() (string, error) {
	base, err := baseDir()
	if err != nil {
		return "", err
	}
	dir := filepath.Join(base, "app-"+version)
	exe := filepath.Join(dir, appExe())
	if _, err := os.Stat(filepath.Join(dir, ".ready")); err == nil {
		return exe, nil
	}
	closeSplash := showSplash("Setting up CORBELscore…\nThis happens once.")
	defer closeSplash()
	if err := os.MkdirAll(base, 0o755); err != nil {
		return "", err
	}
	tmp, err := os.MkdirTemp(base, "unpacking-")
	if err != nil {
		return "", err
	}
	if err := unpack(tmp); err != nil {
		os.RemoveAll(tmp)
		return "", err
	}
	if err := os.WriteFile(filepath.Join(tmp, ".ready"), []byte(version+"\n"), 0o644); err != nil {
		os.RemoveAll(tmp)
		return "", err
	}
	os.RemoveAll(dir) // a half-finished earlier attempt
	if err := os.Rename(tmp, dir); err != nil {
		os.RemoveAll(tmp)
		if _, statErr := os.Stat(filepath.Join(dir, ".ready")); statErr != nil { // not another copy of us finishing first
			return "", err
		}
	}
	// Older versions are no longer needed; anything still in use is simply left.
	if old, _ := filepath.Glob(filepath.Join(base, "app-*")); old != nil {
		for _, o := range old {
			if o != dir {
				os.RemoveAll(o)
			}
		}
	}
	if left, _ := filepath.Glob(filepath.Join(base, "unpacking-*")); left != nil {
		for _, o := range left {
			os.RemoveAll(o)
		}
	}
	return exe, nil
}

func main() {
	exe, err := prepare()
	if err == nil {
		cmd := exec.Command(exe, os.Args[1:]...)
		cmd.Dir = filepath.Dir(exe)
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		err = cmd.Start()
		if err == nil && os.Getenv("CORBEL_WAIT") != "" { // tests: wait and pass the exit code on
			err = cmd.Wait()
			var ee *exec.ExitError
			if errors.As(err, &ee) {
				os.Exit(ee.ExitCode())
			}
		}
	}
	if err != nil {
		fail("CORBELscore could not start.\n\n" + err.Error())
		os.Exit(1)
	}
}
