#!/usr/bin/env python3
"""ZKidz Unit Visuals installer: patches this PC's own Civ VII art packages into the game's Overrides folder.

The game loads unit art only from there, never from a mod folder, so the Workshop item ships this program.
"""
import argparse
import os
import sys
from pathlib import Path

from civ7_paths import GameNotFound

REFRESH_SCRIPT = "zk-unit-visuals-refresh.vbs"


def startup_dir():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def add_login_refresh(exe):
    """Rebuilds after a game patch at each login, hidden; does nothing once the item is unsubscribed."""
    script = startup_dir() / REFRESH_SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        'Set files = CreateObject("Scripting.FileSystemObject")\r\n'
        f'exe = "{exe}"\r\n'
        'If files.FileExists(exe) Then CreateObject("WScript.Shell").Run """" & exe & """ --refresh", 0, False\r\n'
    )
    return script


def remove_login_refresh():
    (startup_dir() / REFRESH_SCRIPT).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=["install", "uninstall"], default="install")
    parser.add_argument("--refresh", action="store_true", help="install only if the game was patched since the last install")
    args = parser.parse_args(argv)
    try:
        # Finding the game happens on import, so a missing install is reported before any work starts.
        import unit_scale
    except GameNotFound as error:
        print(f"Could not install: {error}")
        return 1
    try:
        if args.action == "uninstall":
            unit_scale.uninstall()
            remove_login_refresh()
            print("ZKidz Unit Visuals removed. The game uses its original unit art again.")
            return 0
        build = unit_scale.steam_build_id()
        if args.refresh and not unit_scale.refresh_needed(unit_scale.MANIFEST, build):
            return 0
        print(f"Patching unit art for game build {build}. This takes a minute or two...")
        unit_scale.install(unit_scale.load_sizes())
        if getattr(sys, "frozen", False):
            add_login_refresh(Path(sys.executable))
        print("Done. Start Civilization VII to see the new unit visuals.")
        return 0
    except unit_scale.ForeignOverride as error:
        print(f"Could not install: {error}")
        return 1
    except OSError as error:
        # The running game holds its art packages open.
        print(f"Could not {args.action}: {error}. Close Civilization VII and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
