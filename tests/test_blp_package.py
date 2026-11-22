"""Growing a unit's member vector by appending a new array allocation; no existing allocation moves."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from blp_package import Package, grow_vector  # noqa: E402

PKG_START = 0x400
ENTRY = 40


def build(member_ids, padding=0x100, tail=b"BIGDATA!"):
    """Preamble + header (5 stripes + linker) + TypeInfo, PackageBlock (vector + array), TempData (table)."""
    type_info = b"T" * 0x20
    package_block = bytearray(b"\x00" * 0x20)
    vector_rel = len(package_block)
    package_block += struct.pack("<QII", 1, len(member_ids), len(member_ids))
    array_rel = len(package_block)
    package_block += b"".join(struct.pack("<II", member, 0) for member in member_ids)
    package_block += b"\x00" * (-len(package_block) % 16)
    linker = 0x10
    entries = [(0, array_rel, 8 * len(member_ids), len(member_ids), 7, 2), (1, 0, 4, 4, 0, 0)]
    temp_data = b"L" * linker + b"".join(struct.pack("<QIIIxxxxQQ", *entry) for entry in entries)
    header_size = 16 + 48
    type_info_off = header_size
    pb_off = type_info_off + len(type_info)
    td_off = pb_off + len(package_block)
    preamble = struct.pack("<IHHII", 5, 8, 8, 72, 1)
    stripes = [(pb_off, 0), (pb_off, len(package_block)), (td_off, len(temp_data)), (type_info_off, len(type_info)), (0x58, 0)]
    header = b"".join(struct.pack("<II", *stripe) for stripe in stripes) + struct.pack("<I", linker) + b"\x00" * 4
    package = preamble + header + type_info + bytes(package_block) + temp_data + b"\x00" * padding
    file_header = bytearray(b"CIVBLP" + b"\x00" * (PKG_START - 6))
    struct.pack_into("<I", file_header, 0x8, PKG_START)
    struct.pack_into("<I", file_header, 0xC, len(package))
    struct.pack_into("<I", file_header, 0x10, PKG_START + len(package))
    struct.pack_into("<I", file_header, 0x18, PKG_START + len(package) + len(tail))
    return bytes(file_header) + package + tail, PKG_START + pb_off + vector_rel


def test_package_reads_the_vector_target_allocation():
    data, vector_at = build([0xA, 0xB, 0xC])
    package = Package(data)
    pointer = struct.unpack_from("<Q", data, vector_at)[0]
    allocation = package.allocation(pointer)
    assert (allocation.count, allocation.size) == (3, 24)
    assert package.allocation_ids(pointer) == [0xA, 0xB, 0xC]


def test_grow_vector_points_at_a_new_allocation_with_cycled_ids():
    data, vector_at = build([0xA, 0xB, 0xC])
    grown = grow_vector(data, vector_at, 6)
    package = Package(grown)
    pointer, count, capacity = struct.unpack_from("<QII", grown, vector_at)
    assert (count, capacity) == (6, 6)
    assert pointer == 3
    assert package.allocation_ids(pointer) == [0xA, 0xB, 0xC, 0xA, 0xB, 0xC]


def test_existing_allocations_keep_their_index_offset_and_content():
    data, vector_at = build([0xA, 0xB, 0xC])
    grown = grow_vector(data, vector_at, 6)
    before, after = Package(data), Package(grown)
    for index in (1, 2):
        assert after.allocation(index) == before.allocation(index)
        assert after.allocation_bytes(index) == before.allocation_bytes(index)


def test_section_after_the_package_survives_and_header_sizes_stay_consistent():
    data, vector_at = build([0xA, 0xB, 0xC], padding=0x100)
    grown = grow_vector(data, vector_at, 6)
    assert grown.endswith(b"BIGDATA!") and len(grown) == len(data)


def test_small_padding_grows_the_package_by_aligned_blocks():
    data, vector_at = build([0xA, 0xB, 0xC], padding=0x8)
    grown = grow_vector(data, vector_at, 6)
    assert len(grown) == len(data) + 0x200
    assert grown.endswith(b"BIGDATA!")
    assert struct.unpack_from("<I", grown, 0x18)[0] == len(grown)
    assert Package(grown).allocation_ids(3) == [0xA, 0xB, 0xC, 0xA, 0xB, 0xC]


def named_field_package():
    """A package whose vector is the value of a field record: [u64 0xa][u64 String ptr][u64 0xc][vector]."""
    data, vector_at = build([0xA, 0xB, 0xC])
    blob = bytearray(data)
    struct.pack_into("<Q", blob, vector_at - 8, 0xC)
    struct.pack_into("<Q", blob, vector_at - 24, 0xA)
    return bytes(blob), vector_at


def test_find_named_vectors_returns_vectors_whose_field_name_matches(monkeypatch):
    import blp_package

    data, vector_at = named_field_package()
    monkeypatch.setattr(blp_package.Package, "field_name_at", lambda self, offset: "MemberInfo" if offset == vector_at - 16 else None)
    found = blp_package.find_named_vectors(data, "MemberInfo")
    assert found == [(vector_at, 3)]


def test_raise_field_minimum_lifts_small_values_and_leaves_larger_ones():
    import blp_package

    name = b"MaxVisibleSlots"
    definition = struct.pack("<III", 1, 0, 0x77) + b"\x00" * 12 + struct.pack("<II", len(name) + 1, len(name)) + name + b"\x00"
    records = struct.pack("<III", 4, 0, 0x77) + b"\x00" * 4 + struct.pack("<III", 16, 0, 0x77) + b"\x00" * 4
    data = b"CIVBLP" + b"\x00" * 10 + definition + b"\x00" * 3 + records
    raised = blp_package.raise_field_minimum(data, "MaxVisibleSlots", 10)
    values = [struct.unpack_from("<I", raised, offset)[0] for offset in blp_package.field_value_offsets(raised, "MaxVisibleSlots")]
    assert values == [10, 10, 16]


def test_asset_fields_reads_named_formation_values_from_the_real_package():
    import pytest

    from blp_package import asset_fields
    from unit_scale import GAME_DIR

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    fields = asset_fields(package_file.read_bytes(), "Formation_SingleCenter")
    assert fields["SpacingMultiplier"] == 0x6A3EEA
    assert fields["FirstRowWidth"] == 0x6A3FAA
    assert fields["MaxVisibleSlots"] == 0x6A435A


def test_apply_formation_rules_sets_spacing_and_row_width():
    import pytest

    from blp_package import asset_fields, apply_formation_rules
    from unit_scale import GAME_DIR

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    patched = apply_formation_rules(package_file.read_bytes())
    fields = asset_fields(patched, "Formation_SingleCenter")
    assert struct.unpack_from("<f", patched, fields["SpacingMultiplier"])[0] == 1.0
    assert struct.unpack_from("<I", patched, fields["FirstRowWidth"])[0] == 2
    double = asset_fields(patched, "Formation_2_Double")
    assert struct.unpack_from("<I", patched, double["FirstRowWidth"])[0] == 5


def test_naval_rule_gives_ship_formations_the_embarked_column_layout():
    import pytest

    from blp_package import asset_fields, apply_formation_rules
    from unit_scale import GAME_DIR

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    rules = [{"match": "SingleCenter", "set": {"SpacingY": 50.0, "SpacingMultiplier": 1.0, "FirstRowWidth": 1}}]
    patched = apply_formation_rules(package_file.read_bytes(), rules)
    fields = asset_fields(patched, "Formation_SingleCenter")
    assert struct.unpack_from("<f", patched, fields["SpacingY"])[0] == 50.0
    assert struct.unpack_from("<f", patched, fields["SpacingMultiplier"])[0] == 1.0
    assert struct.unpack_from("<I", patched, fields["FirstRowWidth"])[0] == 1



def test_named_rule_also_changes_already_spread_formations_but_stacked_only_rule_does_not():
    import pytest

    from blp_package import asset_fields, apply_formation_rules
    from unit_scale import GAME_DIR

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.5.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    data = package_file.read_bytes()
    named = apply_formation_rules(data, [{"match": "AirPatrol", "set": {"AbsoluteOverride": 0, "FirstRowWidth": 2}}])
    fields = asset_fields(named, "Formation_AirPatrol")
    assert struct.unpack_from("<I", named, fields["AbsoluteOverride"])[0] == 0
    assert struct.unpack_from("<I", named, fields["FirstRowWidth"])[0] == 2
    stacked_only = apply_formation_rules(data, [{"match": ".*", "stackedOnly": True, "set": {"FirstRowWidth": 2}}])
    assert struct.unpack_from("<I", stacked_only, asset_fields(stacked_only, "Formation_AirPatrol")["FirstRowWidth"])[0] == 1


def test_per_row_increment_is_written_as_a_float_so_rows_grow_into_an_arrow():
    import pytest

    from blp_package import apply_formation_rules, asset_fields
    from unit_scale import GAME_DIR

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs/StandardAsset.blp"
    if not package_file.exists():
        pytest.skip("needs the installed game")
    patched = apply_formation_rules(package_file.read_bytes(), [{"match": "SingleCenter", "set": {"FirstRowWidth": 1, "PerRowIncrement": 1.0}}])
    fields = asset_fields(patched, "Formation_SingleCenter")
    assert struct.unpack_from("<f", patched, fields["PerRowIncrement"])[0] == 1.0


def test_append_allocation_adds_one_entry_and_moves_nothing():
    from blp_package import append_allocation

    data, _vector_at = build([0xA, 0xB, 0xC])
    grown, pointer = append_allocation(data, b"\x05\x00\x00\x00\x04\x00\x00\x00TANK\x00", like=1)
    before, after = Package(data), Package(grown)
    assert pointer == before.entry_count + 1
    assert after.allocation_bytes(pointer) == b"\x05\x00\x00\x00\x04\x00\x00\x00TANK\x00"
    assert all(after.allocation_bytes(i) == before.allocation_bytes(i) for i in range(1, before.entry_count + 1))


def real_package(name):
    import pytest

    from unit_scale import GAME_DIR

    package_file = GAME_DIR / "Base/Platforms/Windows/BLPs" / name
    if not package_file.exists():
        pytest.skip("needs the installed game")
    return package_file.read_bytes()


def test_repoint_formation_makes_the_tank_use_another_formation_by_name():
    from blp_package import entry_asset_name, repoint_formation

    data = real_package("StandardAsset.2.blp")
    patched = repoint_formation(data, "UNIT_TANK", "Formation_AirPatrol")
    assert entry_asset_name(patched, "UNIT_TANK", "Formation") == "Formation_AirPatrol"
    assert entry_asset_name(patched, "UNIT_TANK", "CombatFormation") == "Formation_AirPatrol"
    assert entry_asset_name(patched, "UNIT_TANK", "PackedFormation") == "Formation_SingleCenter"


def test_scale_override_positions_widens_a_fixed_slot_formation():
    from blp_package import override_positions, scale_override_positions

    data = real_package("StandardAsset.5.blp")
    patched = scale_override_positions(data, "Formation_AirPatrol", 2.0)
    assert override_positions(patched, "Formation_AirPatrol")[:3] == [(0.0, 0.0), (-30.0, 30.0), (-30.0, -30.0)]
