# PyInstaller build:  pyinstaller TeleScore.spec   ->  dist/TeleScore/
# Works on Windows, macOS and Linux (build on each platform).
import os

block_cipher = None
here = os.path.abspath(".")

a = Analysis(
    ["telescore/__main__.py"],
    pathex=[here],
    datas=[("telescore/assets", "telescore/assets"), ("LICENSE", "."), ("docs/schema", "docs/schema")],
    hiddenimports=["PyQt6.QtMultimedia"],
    excludes=["tkinter", "numpy"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TeleScore", console=False,
          icon="telescore/assets/icon.ico")
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="TeleScore")
