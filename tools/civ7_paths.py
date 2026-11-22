"""Where Civ VII and its user folder are: found through Steam on a player's PC, fixed /mnt/c paths under WSL."""
import os
import re
import subprocess
import sys
from pathlib import Path

APP_ID = "1295660"
GAME_FOLDER = "Sid Meier's Civilization VII"
ON_WINDOWS = sys.platform == "win32"
WSL_STEAM = Path("/mnt/c/Program Files (x86)/Steam")
WSL_USER_DIR = Path("/mnt/c/Users/Angelo/AppData/Local/Firaxis Games") / GAME_FOLDER


class GameNotFound(RuntimeError):
    pass


def steam_libraries(steam_dir):
    """Steam's own folder plus every library libraryfolders.vdf lists (paths there double their backslashes)."""
    steam_dir = Path(steam_dir)
    listing = steam_dir / "steamapps" / "libraryfolders.vdf"
    libraries = [steam_dir]
    if listing.exists():
        found = re.findall(r'"path"\s+"([^"]+)"', listing.read_text(errors="ignore"))
        libraries += [Path(path.replace("\\\\", "\\")) for path in found]
    return libraries


def find_game_dir(steam_dir):
    for library in steam_libraries(steam_dir):
        if (library / "steamapps" / f"appmanifest_{APP_ID}.acf").exists():
            return library / "steamapps" / "common" / GAME_FOLDER
    return None


def windows_steam_dir():
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
        return Path(winreg.QueryValueEx(key, "SteamPath")[0])


def game_dir():
    if not ON_WINDOWS:
        return WSL_STEAM / "steamapps" / "common" / GAME_FOLDER
    steam = windows_steam_dir()
    found = find_game_dir(steam)
    if found is None:
        searched = ", ".join(str(library) for library in steam_libraries(steam))
        raise GameNotFound(f"Civilization VII is not installed in any Steam library ({searched})")
    return found


def user_dir():
    if ON_WINDOWS:
        return Path(os.environ["LOCALAPPDATA"]) / "Firaxis Games" / GAME_FOLDER
    return WSL_USER_DIR


def windows_path(path):
    """Converts the parent only: wslpath follows a junction, which would aim rmdir at the junction's target."""
    if ON_WINDOWS:
        return str(path)
    parent = subprocess.run(["wslpath", "-w", str(path.parent)], capture_output=True, text=True, check=True).stdout.strip()
    return f"{parent}\\{path.name}"


def run_cmd(*args):
    # cmd.exe refuses a UNC working directory, so under WSL it always starts from a drive path.
    subprocess.run(["cmd.exe", "/c", *args], cwd=None if ON_WINDOWS else "/mnt/c", capture_output=True, check=True)


def make_junction(link, target):
    run_cmd("mklink", "/J", windows_path(link), windows_path(target))


def remove_junction(link):
    """Removes the link only; a recursive delete through a junction would wipe its target."""
    if ON_WINDOWS:
        os.rmdir(link)
    else:
        run_cmd("rmdir", windows_path(link))
