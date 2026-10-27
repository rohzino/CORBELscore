"""Build CORBELscore.exe: one file to share.

    python3 scripts/exe/build.py [--electron <electron-vX-win32-x64.zip>] [--target windows|linux]

Needs Go (any recent version) and the Electron runtime zip from
https://github.com/electron/electron/releases (the version in CORBELscore.bat;
its SHA-256 is checked). Writes dist/CORBELscore.exe (or dist/corbelscore for
--target linux, used to test the launcher).

What it does:
1. Unpacks the Electron runtime, renames electron.exe to CORBELscore.exe and
   gives it CORBELscore's icon and version text (mkrsrc.py --patch).
2. Puts the app in resources/app (package.json, LICENSE, app/).
3. Zips that folder into the launcher (main.go embeds it) and builds the
   launcher with the icon, a manifest and version text (mkrsrc.py).
"""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
EV = "44.9.3"
SHA = {"win32": "41a1ffa0541cb0f2c9b9fe920dd2cef1793ad0ea2ada1a9582958880f4d1b23c"}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--electron", help="the Electron runtime zip for the target")
    ap.add_argument("--target", default="windows", choices=["windows", "linux"])
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args()
    plat = "win32" if a.target == "windows" else "linux"
    ez = pathlib.Path(a.electron or f"electron-v{EV}-{plat}-x64.zip")
    if not ez.exists():
        sys.exit(f"Missing {ez}. Download it from https://github.com/electron/electron/releases/tag/v{EV}")
    if plat in SHA and sha256(ez) != SHA[plat]:
        sys.exit(f"{ez} does not match the expected SHA-256.")
    pkg = json.loads((ROOT / "package.json").read_text())
    ver = pkg["version"]                                      # 2.0.0-alpha.4
    nums = ".".join((ver.split("-")[0].split(".") + ["0"] * 3)[:3]) + "." + (ver.split(".")[-1] if "-" in ver else "0")
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        stage = pathlib.Path(tmp) / "CORBELscore"
        with zipfile.ZipFile(ez) as z:
            z.extractall(stage)
        if plat == "win32":
            subprocess.run([sys.executable, str(HERE / "mkrsrc.py"), str(ROOT / "app/assets/icon.ico"), str(stage / "CORBELscore.exe"),
                            "--patch", str(stage / "electron.exe"), "--version", nums, "--description", "CORBELscore",
                            "--copyright", "AGPL-3.0. Built on TeleScore by the JumpShot team."], check=True)
            (stage / "electron.exe").unlink()
        else:
            (stage / "electron").rename(stage / "corbelscore")
            for f in stage.rglob("*"):         # zip loses the execute bit; put it back on the programs
                if f.name in ("corbelscore", "chrome_crashpad_handler", "chrome-sandbox") or f.suffix == ".so":
                    f.chmod(0o755)
        (stage / "resources" / "default_app.asar").unlink(missing_ok=True)
        app = stage / "resources" / "app"
        app.mkdir(parents=True)
        shutil.copy2(ROOT / "package.json", app / "package.json")
        shutil.copy2(ROOT / "LICENSE", app / "LICENSE")
        shutil.copytree(ROOT / "app", app / "app", ignore=shutil.ignore_patterns("*.map"))

        payload = HERE / "payload.zip"
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in sorted(stage.rglob("*")):
                if f.is_file():
                    info = zipfile.ZipInfo.from_file(f, f.relative_to(stage).as_posix())
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with open(f, "rb") as src:
                        z.writestr(info, src.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        tag = sha256(payload)[:12]
        syso = HERE / "rsrc_windows_amd64.syso"
        try:
            env = {**os.environ, "CGO_ENABLED": "0", "GOARCH": "amd64"}
            if plat == "win32":
                subprocess.run([sys.executable, str(HERE / "mkrsrc.py"), str(ROOT / "app/assets/icon.ico"), str(syso), "--version", nums,
                                "--description", "CORBELscore", "--copyright", "AGPL-3.0. Built on TeleScore by the JumpShot team."], check=True)
                env["GOOS"] = "windows"
                target = out / "CORBELscore.exe"
                flags = f"-H windowsgui -s -w -X main.version={ver}-{tag}"
            else:
                env["GOOS"] = "linux"
                target = out / "corbelscore"
                flags = f"-s -w -X main.version={ver}-{tag}"
            subprocess.run(["go", "build", "-trimpath", "-ldflags", flags, "-o", str(target), "."], cwd=HERE, env=env, check=True)
        finally:
            payload.unlink(missing_ok=True)
            syso.unlink(missing_ok=True)
    print(f"{target}  {target.stat().st_size / 1e6:.0f} MB  version {ver}-{tag}")


if __name__ == "__main__":
    main()
