# R.E.D ZKidz: Unit Visuals

Smaller units in larger numbers, so the map looks like armies instead of giant figurines.

- Infantry and cavalry are drawn at 85% size, with full squads. Cavalry show 6 riders.
- Tanks, Landships, Chariots and every artillery unit show 3 vehicles in an arrowhead formation inside one hex.
- Planes fly in threes.
- Ships stay one hull each, sized by class: big warships grow, small boats stay close to their original size.

## Install

Civilization VII only loads unit art from its own Overrides folder, and Steam Workshop items can't contain installers, so this mod is installed from here.

1. Download `zk-unit-visuals-installer-v*.zip` from the [latest release](https://github.com/theangeloumali/civ7-unit-visuals/releases/latest).
2. Unzip it somewhere it can stay, for example `Documents`.
3. Close the game and double-click `install.bat`. If Windows says it protected your PC, click **More info**, then **Run anyway**.
4. Start the game.

After a game patch the visuals rebuild themselves the next time you log in to Windows, as long as the unzipped folder is still there.

## Uninstall

Run `uninstall.bat` before you delete the unzipped folder. It removes only the files the installer wrote, so other mods' overrides stay.

## What the installer does

It reads your game's own art files and writes patched copies to `%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VII\Overrides\Local`. Your game installation is never changed. Visual only: no gameplay change, safe for any save, works with DLC units.

## Source

Python 3, standard library only.

| Path                              | What it is                                                                                            |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `tools/unit_visuals_installer.py` | The installer program: `install`, `uninstall`, `--refresh`                                            |
| `tools/unit_scale.py`             | Scales units, adds figures and swaps formations; writes the overrides and the manifest uninstall uses |
| `tools/blp_package.py`            | Reads and edits Civ VII `.blp` art packages                                                           |
| `tools/civ7_paths.py`             | Finds the game through Steam on any drive                                                             |
| `tools/unit_sizes.json`           | Every size, figure count and formation setting ([mapping](docs/unit-visuals-mapping.md))              |
| `tools/build_installer.py`        | Builds the exe and the release zip (run with Windows Python; installs PyInstaller)                    |
| `release/zk-unit-visuals/`        | The `.bat` files and README that ship in the zip                                                      |

Run the tests with `python -m pytest tests`; on Windows they need the game installed, because the tools locate it on import. Run from source on Windows with `python tools\unit_visuals_installer.py install`.
