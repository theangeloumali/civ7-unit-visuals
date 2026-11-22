"""Finding Civ VII on a player's PC: the Steam library that holds its app manifest, on any drive."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from civ7_paths import GAME_FOLDER, find_game_dir  # noqa: E402

LIBRARY_FOLDERS = """"libraryfolders"
{
	"0"
	{
		"path"		"STEAM"
	}
	"1"
	{
		"path"		"GAMES"
	}
}
"""


def make_library(root, with_game):
    (root / "steamapps").mkdir(parents=True)
    if with_game:
        (root / "steamapps" / "appmanifest_1295660.acf").write_text('"AppState" {}')
    return root


def test_game_is_found_in_a_second_library_listed_by_steam(tmp_path):
    steam = make_library(tmp_path / "Steam", with_game=False)
    games = make_library(tmp_path / "Games", with_game=True)
    # Steam writes Windows paths with doubled backslashes; on Linux the path has none to escape.
    listing = LIBRARY_FOLDERS.replace("STEAM", str(steam)).replace("GAMES", str(games).replace("\\", "\\\\"))
    (steam / "steamapps" / "libraryfolders.vdf").write_text(listing)
    assert find_game_dir(steam) == games / "steamapps" / "common" / GAME_FOLDER


def test_no_library_with_the_game_finds_nothing(tmp_path):
    steam = make_library(tmp_path / "Steam", with_game=False)
    assert find_game_dir(steam) is None
