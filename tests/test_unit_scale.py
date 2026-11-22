"""Unit-scale patcher: finds UniformScale records in a BLP copy and rescales them, never touching the source."""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from unit_scale import find_scale_records, rescaled, uniform_scale_field_id  # noqa: E402

FIELD_ID = 0xDEDF


def scale_record(value, field_id=FIELD_ID):
    return struct.pack("<fII", value, 0, field_id) + b"\x00" * 4


def name_definition(field_id=FIELD_ID):
    """First use of a field: its value record, then the inline name string 0x18 bytes after the id."""
    return struct.pack("<fII", 1.0, 0, field_id) + b"\x00" * 12 + struct.pack("<II", 13, 12) + b"UniformScale\x00"


def blob(*records, field_id=FIELD_ID):
    head = b"CIVBLP" + b"\x00" * 12 + name_definition(field_id)
    # Pad so every 16-byte record starts at 2 mod 8, the alignment unit headers have in real packages.
    head += b"\x00" * ((2 - len(head)) % 8)
    return head + b"".join(records) + b"\x00" * 16


def test_field_id_is_read_from_the_inline_name_definition():
    assert uniform_scale_field_id(blob(field_id=0x156A4)) == 0x156A4


def test_find_scale_records_uses_each_packages_own_field_id():
    data = blob(scale_record(0.75, field_id=0x156A4), scale_record(0.5, field_id=FIELD_ID), field_id=0x156A4)
    values = [struct.unpack_from("<f", data, offset)[0] for offset in find_scale_records(data)]
    assert values == [1.0, 0.75]


def test_find_scale_records_returns_nothing_without_a_name_definition():
    assert find_scale_records(b"CIVBLP" + scale_record(1.0) * 4) == []


def test_find_scale_records_ignores_implausible_values():
    data = blob(scale_record(0.0), scale_record(-1.0), scale_record(1e9))
    assert len(find_scale_records(data)) == 1


def test_rescaled_scales_every_record_and_returns_a_new_buffer():
    original = blob(scale_record(1.0), scale_record(2.0))
    patched = rescaled(original, 0.5)
    assert [struct.unpack_from("<f", patched, offset)[0] for offset in find_scale_records(patched)] == [0.5, 0.5, 1.0]
    assert [struct.unpack_from("<f", original, offset)[0] for offset in find_scale_records(original)] == [1.0, 1.0, 2.0]


def test_remove_override_tree_unlinks_junction_without_deleting_its_target():
    """Real Windows junction on /mnt/c: removal must leave the junction's target files intact."""
    import shutil as shell_tools

    import pytest
    from unit_scale import SHARED_DATA, link_shared_data, remove_override_tree

    if not shell_tools.which("cmd.exe"):
        pytest.skip("needs Windows interop")
    sandbox = Path(__file__).resolve().parent.parent / ".cache" / "junction-test"
    shell_tools.rmtree(sandbox, ignore_errors=True)
    game_blps = sandbox / "game" / "BLPs"
    (game_blps / SHARED_DATA).mkdir(parents=True)
    (game_blps / SHARED_DATA / "BLOB_keep_me").write_text("blob")
    override_blps = sandbox / "Overrides" / "Local" / "Base" / "Platforms" / "Windows" / "BLPs"
    override_blps.mkdir(parents=True)
    link_shared_data(override_blps, game_blps)
    assert (override_blps / SHARED_DATA / "BLOB_keep_me").read_text() == "blob"
    remove_override_tree(sandbox / "Overrides", game_blps)
    assert not (sandbox / "Overrides").exists()
    assert (game_blps / SHARED_DATA / "BLOB_keep_me").read_text() == "blob"
    shell_tools.rmtree(sandbox)


def unit_header(name):
    """A unit asset starts with the FNV-1a hash of its name, aligned 2 mod 8 like the real packages."""
    from unit_scale import fnv1a

    return struct.pack("<I", fnv1a(name)) + b"\x00" * 12


def test_unit_owning_each_scale_record_is_the_nearest_unit_header_before_it():
    from unit_scale import scale_record_owners

    data = blob(unit_header("UNIT_WARRIOR"), scale_record(1.0), unit_header("UNIT_GALLEY"), scale_record(1.0))
    owners = scale_record_owners(data, {"UNIT_WARRIOR", "UNIT_GALLEY"})
    # The name definition's own record sits before any unit header, so it has no owner.
    assert list(owners.values()) == [None, "UNIT_WARRIOR", "UNIT_GALLEY"]


def test_factor_for_prefers_unit_override_then_class_then_default():
    from unit_scale import factor_for

    sizes = {"default": 0.85, "classes": {"naval": 1.0}, "units": {"UNIT_HEAVY_ARTILLERY": 0.6}}
    classes = {"UNIT_GALLEY": "naval", "UNIT_HEAVY_ARTILLERY": "siege", "UNIT_WARRIOR": "infantry"}
    assert factor_for("UNIT_HEAVY_ARTILLERY", sizes, classes) == 0.6
    assert factor_for("UNIT_GALLEY", sizes, classes) == 1.0
    assert factor_for("UNIT_WARRIOR", sizes, classes) == 0.85
    assert factor_for(None, sizes, classes) == 0.85


def test_rescaled_applies_a_per_offset_factor():
    data = blob(scale_record(1.0), scale_record(1.0))
    offsets = find_scale_records(data)
    factors = {offsets[1]: 0.5, offsets[2]: 2.0}
    patched = rescaled(data, lambda offset: factors.get(offset, 1.0))
    assert [struct.unpack_from("<f", patched, offset)[0] for offset in offsets] == [1.0, 0.5, 2.0]


def test_art_only_assets_own_their_records_instead_of_the_unit_before_them():
    import pytest

    from unit_scale import GAME_DIR
    from unit_scale import package_unit_names, scale_record_owners

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.5.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    data = package_file.read_bytes()
    names = package_unit_names(data, {"UNIT_WARRIOR"})
    assert "UNIT_WARRIOR" in names and "UNIT_EMBARK" in names
    assert "UNIT_EMBARK" in set(scale_record_owners(data, names).values())


def test_apply_formation_swaps_repoints_only_units_in_this_package():
    import pytest

    from blp_package import entry_asset_name
    from unit_scale import GAME_DIR
    from unit_scale import apply_formation_swaps

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.2.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    figures = {"formationSwaps": {"UNIT_TANK": "Formation_AirPatrol", "UNIT_NOT_HERE": "Formation_AirPatrol"}}
    patched = apply_formation_swaps(package_file.read_bytes(), figures)
    assert entry_asset_name(patched, "UNIT_TANK", "Formation") == "Formation_AirPatrol"


def test_steam_build_id_is_read_from_the_app_manifest(tmp_path):
    from unit_scale import steam_build_id

    manifest = tmp_path / "appmanifest_1295660.acf"
    manifest.write_text('"AppState"\n{\n\t"appid"\t\t"1295660"\n\t"buildid"\t\t"26660673"\n}\n')
    assert steam_build_id(manifest) == "26660673"


def test_refresh_reads_the_build_from_the_manifest_and_rebuilds_a_legacy_text_marker(tmp_path):
    from unit_scale import refresh_needed, write_manifest

    manifest = tmp_path / "zk-unit-visuals-manifest.json"
    assert refresh_needed(manifest, "26660673")
    write_manifest(manifest, tmp_path, "26660673", files=[], junctions=[])
    assert not refresh_needed(manifest, "26660673")
    assert refresh_needed(manifest, "26700000")
    manifest.write_text("26660673")
    assert refresh_needed(manifest, "26660673")


def owned_override_tree(tmp_path):
    overrides = tmp_path / "Overrides"
    ours = overrides / "Local" / "Base" / "Platforms" / "Windows" / "BLPs" / "StandardAsset.blp"
    ours.parent.mkdir(parents=True)
    ours.write_bytes(b"ours")
    foreign = overrides / "Local" / "DLC" / "other-mod" / "Platforms" / "Windows" / "BLPs" / "Other.blp"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"theirs")
    return overrides, ours, foreign


def test_uninstall_removes_only_the_files_its_manifest_lists(tmp_path):
    from unit_scale import uninstall, write_manifest

    overrides, ours, foreign = owned_override_tree(tmp_path)
    manifest = overrides / "Local" / "zk-unit-visuals-manifest.json"
    write_manifest(manifest, overrides, "26660673", files=[ours], junctions=[])
    # Forward slashes, so a manifest the Windows exe wrote is still read correctly under WSL.
    assert json.loads(manifest.read_text())["files"] == ["Local/Base/Platforms/Windows/BLPs/StandardAsset.blp"]
    uninstall(overrides, manifest)
    assert not ours.exists() and not manifest.exists()
    assert not (overrides / "Local" / "Base").exists()
    assert foreign.read_bytes() == b"theirs"


def test_install_refuses_to_overwrite_a_package_another_mod_put_there(tmp_path):
    import pytest
    from unit_scale import ForeignOverride, claim_target

    _overrides, _ours, foreign = owned_override_tree(tmp_path)
    with pytest.raises(ForeignOverride):
        claim_target(foreign)
    claim_target(tmp_path / "free.blp")


def test_a_manifest_written_on_windows_lists_forward_slash_paths(tmp_path):
    from pathlib import PureWindowsPath

    from unit_scale import write_manifest

    root = PureWindowsPath("C:/Users/p/Overrides")
    manifest = tmp_path / "zk-unit-visuals-manifest.json"
    write_manifest(manifest, root, "1", files=[root / "Local" / "Base" / "StandardAsset.blp"], junctions=[])
    assert json.loads(manifest.read_text())["files"] == ["Local/Base/StandardAsset.blp"]


def test_packed_art_inherits_its_units_size_and_figures():
    from unit_scale import factor_for, figures_for

    sizes = {"default": 0.85, "classes": {"siege": 0.7}, "units": {"UNIT_HEAVY_ARTILLERY": 0.6},
             "figures": {"classes": {"siege": 3}, "units": {}}}
    classes = {"UNIT_CATAPULT": "siege", "UNIT_HEAVY_ARTILLERY": "siege"}
    assert factor_for("UNIT_CATAPULT_PACKED", sizes, classes) == 0.7
    assert factor_for("UNIT_HEAVY_ARTILLERY_PACKED", sizes, classes) == 0.6
    assert figures_for("UNIT_CATAPULT_PACKED", sizes, classes) == 3


def test_packed_art_follows_its_units_formation_swap():
    import pytest

    from blp_package import entry_asset_name
    from unit_scale import GAME_DIR
    from unit_scale import apply_formation_swaps

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.4.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    patched = apply_formation_swaps(package_file.read_bytes(), {"formationSwaps": {"UNIT_CATAPULT": "Formation_AirPatrol"}})
    assert entry_asset_name(patched, "UNIT_CATAPULT_PACKED", "Formation") == "Formation_AirPatrol"
