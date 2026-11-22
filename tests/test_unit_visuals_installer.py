"""The player-facing installer: its login refresh entry and how it reports problems."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import unit_visuals_installer as installer  # noqa: E402


def test_login_refresh_runs_the_exe_hidden_and_skips_quietly_once_it_is_gone(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    exe = Path("C:/SteamLibrary/steamapps/workshop/content/1295660/123/zk-unit-visuals.exe")
    script = installer.add_login_refresh(exe)
    text = script.read_text()
    assert script.parent == installer.startup_dir()
    assert str(exe) in text and "--refresh" in text
    assert "FileExists" in text and ", 0, False" in text
    installer.remove_login_refresh()
    assert not script.exists()


def test_a_foreign_override_is_reported_without_a_traceback(monkeypatch, capsys):
    import unit_scale

    def refuse(_sizes):
        raise unit_scale.ForeignOverride("StandardAsset.blp already exists")

    monkeypatch.setattr(unit_scale, "install", refuse)
    assert installer.main(["install"]) == 1
    assert "StandardAsset.blp already exists" in capsys.readouterr().out


def test_files_locked_by_the_running_game_ask_the_player_to_close_it(monkeypatch, capsys):
    import unit_scale

    def locked(_sizes):
        raise PermissionError("StandardAsset.2.blp is in use")

    monkeypatch.setattr(unit_scale, "install", locked)
    assert installer.main(["install"]) == 1
    assert "Close Civilization VII" in capsys.readouterr().out
