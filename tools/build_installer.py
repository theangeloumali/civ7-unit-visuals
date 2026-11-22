#!/usr/bin/env python3
"""Builds the installer zip for the GitHub release. Run with Windows Python: python tools\\build_installer.py

The Workshop uploader rejects executables and scripts, so the exe and .bat files ship from GitHub instead.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = "1.0.0"
TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
STAGING = REPO / "release" / "zk-unit-visuals"
BUILD = REPO / ".cache" / "installer-build"
ZIP = REPO / ".cache" / f"zk-unit-visuals-installer-v{VERSION}.zip"


def main():
    if sys.platform != "win32":
        sys.exit("run this with Windows Python: the installer must be built as a Windows program")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pyinstaller"], check=True)
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm", "--name", "zk-unit-visuals",
            "--paths", str(TOOLS), "--hidden-import", "unit_scale",
            "--add-data", f"{TOOLS / 'unit_sizes.json'}{os.pathsep}.",
            "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
            str(TOOLS / "unit_visuals_installer.py"),
        ],
        check=True,
    )
    shutil.copy2(BUILD / "dist" / "zk-unit-visuals.exe", STAGING)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(STAGING.iterdir()):
            archive.write(item, f"ZKidz Unit Visuals/{item.name}")
    print(f"built {ZIP}")


if __name__ == "__main__":
    main()
