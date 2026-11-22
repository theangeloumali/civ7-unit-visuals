#!/usr/bin/env python3
"""Shrink Civ VII unit figures by writing a rescaled copy of an art package into the game's override folder.

The shipped package is only read. The engine loads same-named packages from
%LOCALAPPDATA%/.../Overrides/Local/<Base|DLC/pkg>/Platforms/Windows/BLPs; --undo removes only what install wrote.
"""
import argparse
import bisect
import json
import os
import re
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from blp_package import (
    apply_formation_rules,
    asset_entries,
    find_named_vectors,
    fnv1a,
    grow_vector,
    raise_field_minimum,
    repoint_formation,
    scale_override_positions,
)
from civ7_paths import game_dir, make_junction, remove_junction, user_dir

# Each package numbers its own field names. A field's first use is its value record followed by the inline
# name (<u32 len+1><u32 len>"UniformScale\0"), with the field id 0x18 bytes before the string; value records
# are <float value><u32 0><u32 field id>.
UNIFORM_SCALE_NAME = b"\x0d\x00\x00\x00\x0c\x00\x00\x00UniformScale\x00"
FIELD_ID_BEFORE_NAME = 0x18
PLAUSIBLE_SCALE = (0.01, 10.0)
GAME_DIR = game_dir()
OVERRIDES_DIR = user_dir() / "Overrides"
GAME_BLPS = GAME_DIR / "Base/Platforms/Windows/BLPs"
# The packaged installer unpacks its bundled files into sys._MEIPASS.
SIZES_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "unit_sizes.json"
SHARED_DATA = "SHARED_DATA"
APP_MANIFEST = GAME_DIR.parent.parent / "appmanifest_1295660.acf"
# The game build the override was made from (a patch replaces the packages it copies) and every file and
# junction install wrote, so uninstall never touches another mod's overrides.
MANIFEST = OVERRIDES_DIR / "Local" / "zk-unit-visuals-manifest.json"
LEGACY_MARKER_NAME = "zk-unit-visuals-build.txt"


class ForeignOverride(RuntimeError):
    pass


def uniform_scale_field_id(data):
    name_at = data.find(UNIFORM_SCALE_NAME)
    if name_at == -1:
        return None
    return struct.unpack_from("<I", data, name_at + 8 - FIELD_ID_BEFORE_NAME)[0]


def find_scale_records(data):
    """Offsets of UniformScale float values, found by this package's field id after each value."""
    field_id = uniform_scale_field_id(data)
    if field_id is None:
        return []
    marker = struct.pack("<II", 0, field_id)
    offsets = []
    position = data.find(marker, 4)
    while position != -1:
        value_offset = position - 4
        value = struct.unpack_from("<f", data, value_offset)[0]
        if PLAUSIBLE_SCALE[0] <= value <= PLAUSIBLE_SCALE[1]:
            offsets.append(value_offset)
        position = data.find(marker, position + 1)
    return offsets


def unit_headers(data, unit_names):
    """Sorted (offset, unit): a unit asset starts with its name's FNV-1a hash at 2 mod 8 and holds its own records."""
    headers = []
    for name in unit_names:
        marker = struct.pack("<I", fnv1a(name))
        position = data.find(marker)
        while position != -1:
            if position % 8 == 2:
                headers.append((position, name))
            position = data.find(marker, position + 1)
    return sorted(headers)


def owner_of(offset, headers):
    index = bisect.bisect_right(headers, (offset, "\uffff")) - 1
    return headers[index][1] if index >= 0 else None


def package_unit_names(data, known_units):
    """Gameplay units plus art-only unit assets (embarked transports), so no record is credited to the unit before it."""
    return set(known_units) | set(asset_entries(data, "UNIT_"))


def scale_record_owners(data, unit_names):
    """{scale offset: unit} for every UniformScale record."""
    headers = unit_headers(data, unit_names)
    return {offset: owner_of(offset, headers) for offset in find_scale_records(data)}


PACKED_SUFFIX = "_PACKED"


def base_unit(asset_name):
    """Siege and gun units have a separate *_PACKED asset, shown until they deploy; it follows its unit's settings."""
    return asset_name[: -len(PACKED_SUFFIX)] if asset_name and asset_name.endswith(PACKED_SUFFIX) else asset_name


def figures_for(unit, sizes, classes):
    unit = base_unit(unit)
    figures = sizes.get("figures", {})
    if unit in figures.get("units", {}):
        return figures["units"][unit]
    return figures.get("classes", {}).get(classes.get(unit), 0)


def add_figures(data, sizes, classes, unit_names):
    """Grows each unit's MemberInfo vector to its figure target (never shrinks) and lifts formation slot caps."""
    headers = unit_headers(data, unit_names)
    for vector_at, count in find_named_vectors(data, "MemberInfo"):
        target = figures_for(owner_of(vector_at, headers), sizes, classes)
        if target > count:
            data = grow_vector(data, vector_at, target)
    minimum_slots = sizes.get("figures", {}).get("minimumVisibleSlots")
    if minimum_slots:
        data = raise_field_minimum(data, "MaxVisibleSlots", minimum_slots)
    figures = sizes.get("figures", {})
    data = apply_formation_rules(data, figures["formations"]) if "formations" in figures else apply_formation_rules(data)
    return apply_formation_swaps(data, figures)


def apply_formation_swaps(data, figures):
    """Moves units onto another formation by name and widens fixed-slot formations defined in this package."""
    units = set(asset_entries(data, "UNIT_"))
    swaps = figures.get("formationSwaps", {})
    for asset in sorted(units):
        formation = swaps.get(base_unit(asset))
        if formation:
            data = repoint_formation(data, asset, formation)
    formations = set(asset_entries(data, "Formation"))
    for formation, factor in figures.get("slotScale", {}).items():
        if formation in formations:
            data = scale_override_positions(data, formation, factor)
    return data


def factor_for(unit, sizes, classes):
    unit = base_unit(unit)
    if unit in sizes.get("units", {}):
        return sizes["units"][unit]
    return sizes.get("classes", {}).get(classes.get(unit), sizes["default"])


def unit_classes():
    """commander / naval / air / siege / cavalry / infantry for every shipped unit, from its domain, formation and tags."""
    domains, formations, tags = {}, {}, {}
    for xml_file in list((GAME_DIR / "Base/modules").glob("*/data/*.xml")) + list(GAME_DIR.glob("DLC/*/modules/data/*.xml")):
        try:
            root = ET.parse(xml_file).getroot()
        except ET.ParseError:
            continue
        for row in root.iterfind("Units/Row"):
            if row.get("UnitType") and row.get("Domain"):
                domains[row.get("UnitType")] = row.get("Domain")
                formations[row.get("UnitType")] = row.get("FormationClass")
        for row in root.iterfind("TypeTags/Row"):
            tags.setdefault(row.get("Type"), set()).add(row.get("Tag"))
    classes = {}
    for unit, domain in domains.items():
        unit_tags = tags.get(unit, set())
        # A commander is one person whatever its domain, so it never gets extra figures.
        if formations.get(unit) == "FORMATION_CLASS_COMMAND":
            classes[unit] = "commander"
        elif domain == "DOMAIN_SEA":
            classes[unit] = "naval"
        elif domain == "DOMAIN_AIR":
            classes[unit] = "air"
        elif "UNIT_CLASS_SIEGE" in unit_tags:
            classes[unit] = "siege"
        elif "UNIT_CLASS_CAVALRY" in unit_tags:
            classes[unit] = "cavalry"
        else:
            classes[unit] = "infantry"
    return classes


def rescaled(data, factor):
    """Every UniformScale value multiplied by factor: a number, or a function of the record's offset."""
    blob = bytearray(data)
    factor_at = factor if callable(factor) else (lambda _offset: factor)
    for offset in find_scale_records(blob):
        struct.pack_into("<f", blob, offset, struct.unpack_from("<f", blob, offset)[0] * factor_at(offset))
    return bytes(blob)


def package_folders():
    """Base plus every DLC pack: each ships its own unit visuals beside its own SHARED_DATA."""
    yield GAME_BLPS
    yield from sorted(GAME_DIR.glob("DLC/*/Platforms/Windows/BLPs"))


def override_folder_for(game_blps):
    # Mirrors the install layout under Overrides/Local, as ArtDef.log names it for Base and each DLC.
    return OVERRIDES_DIR / "Local" / game_blps.relative_to(GAME_DIR)


def load_sizes(path=SIZES_FILE):
    return json.loads(Path(path).read_text())


def scale_packages(sizes, pattern="StandardAsset*.blp", owned=None):
    """Every quality tier and patch layer carries its own copy of the unit visuals, so all of them are rescaled.

    sizes is a uniform factor or a {"default", "classes", "units"} table applied per owning unit;
    owned collects the files and junctions written.
    """
    owned = owned if owned is not None else {"files": [], "junctions": []}
    if not isinstance(sizes, dict):
        sizes = {"default": sizes}
    classes = unit_classes()
    total = 0
    for game_blps in package_folders():
        override_blps = override_folder_for(game_blps)
        written = 0
        for package in sorted(game_blps.glob(pattern)):
            data = package.read_bytes()
            unit_names = package_unit_names(data, classes)
            owners = scale_record_owners(data, unit_names)
            if not owners:
                continue
            data = rescaled(data, lambda offset: factor_for(owners[offset], sizes, classes))
            target = override_blps / package.name
            claim_target(target)
            override_blps.mkdir(parents=True, exist_ok=True)
            target.write_bytes(add_figures(data, sizes, classes, unit_names))
            owned["files"].append(target)
            written += len(owners)
        if written and link_shared_data(override_blps, game_blps):
            owned["junctions"].append(override_blps / SHARED_DATA)
        total += written
    return total


def steam_build_id(manifest=APP_MANIFEST):
    match = re.search(r'"buildid"\s+"(\d+)"', Path(manifest).read_text())
    return match.group(1) if match else None


def write_manifest(path, root, build, files, junctions):
    # Forward slashes, so a manifest the Windows exe wrote reads the same under WSL.
    def relative(paths):
        return [item.relative_to(root).as_posix() for item in paths]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"build": build, "files": relative(files), "junctions": relative(junctions)}, indent=2))


def read_manifest(path):
    """None when missing or written by an older version (a bare build number)."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def refresh_needed(manifest, build):
    data = read_manifest(manifest)
    return data is None or data.get("build") != build


def claim_target(path):
    if Path(path).exists():
        raise ForeignOverride(f"{path} already exists and was not installed by ZKidz Unit Visuals; remove that mod's file first")


def install(sizes, pattern="StandardAsset*.blp"):
    """A clean override for the current game build, so stale copies of patched packages never linger."""
    uninstall()
    owned = {"files": [], "junctions": []}
    build = steam_build_id() or "unknown"
    try:
        count = scale_packages(sizes, pattern, owned)
    except Exception:
        # Record the partial install so it is undone the same safe way.
        write_manifest(MANIFEST, OVERRIDES_DIR, build, **owned)
        uninstall()
        raise
    write_manifest(MANIFEST, OVERRIDES_DIR, build, **owned)
    return count


def link_shared_data(override_blps, game_blps):
    """Packages resolve their mesh and transform blobs from SHARED_DATA beside them; a junction reuses the 11 GB shipped copy."""
    link = override_blps / SHARED_DATA
    if link.exists():
        return False
    make_junction(link, game_blps / SHARED_DATA)
    return True


def legacy_owned(root):
    """Installs before the manifest wrote only StandardAsset packages and SHARED_DATA junctions in these folders."""
    folders = [root / "Local" / game_blps.relative_to(GAME_DIR) for game_blps in package_folders()]
    return {
        "files": [str(f.relative_to(root)) for folder in folders for f in folder.glob("StandardAsset*.blp")],
        "junctions": [str((folder / SHARED_DATA).relative_to(root)) for folder in folders if (folder / SHARED_DATA).exists()],
    }


def prune_empty_parents(root, paths):
    for path in paths:
        folder = path.parent
        while folder != root and root in folder.parents:
            try:
                os.rmdir(folder)
            except OSError:
                break
            folder = folder.parent


def uninstall(root=OVERRIDES_DIR, manifest=MANIFEST):
    """Removes only what install recorded, junctions first, so other mods' overrides and the game's blobs survive."""
    legacy_marker = root / "Local" / LEGACY_MARKER_NAME
    owned = read_manifest(manifest) or (legacy_owned(root) if legacy_marker.exists() else {"files": [], "junctions": []})
    removed = []
    for link in owned["junctions"]:
        if (root / link).exists():
            remove_junction(root / link)
        removed.append(root / link)
    for name in owned["files"]:
        (root / name).unlink(missing_ok=True)
        removed.append(root / name)
    Path(manifest).unlink(missing_ok=True)
    legacy_marker.unlink(missing_ok=True)
    prune_empty_parents(root, removed + [Path(manifest)])
    if owned["junctions"] and not any((GAME_BLPS / SHARED_DATA).iterdir()):
        raise RuntimeError("shipped SHARED_DATA is empty after uninstalling; verify game files in Steam")


def remove_override_tree(root=OVERRIDES_DIR, game_blps=GAME_BLPS):
    """Test runs only, on an Overrides folder they own: junctions are unlinked first, then the whole tree goes."""
    if not root.exists():
        return
    # Junctions sit exactly in <...>/Platforms/Windows/BLPs/SHARED_DATA; never walk into one to find the next.
    for link in root.glob("**/Platforms/Windows/BLPs/" + SHARED_DATA):
        remove_junction(link)
    shutil.rmtree(root)
    if not any((game_blps / SHARED_DATA).iterdir()):
        raise RuntimeError("shipped SHARED_DATA is empty after removing overrides; verify game files in Steam")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor", type=float, help="one factor for every unit; default: tools/unit_sizes.json")
    parser.add_argument("--package", default="StandardAsset*.blp", help="package glob under Base/Platforms/Windows/BLPs")
    parser.add_argument("--undo", action="store_true", help="remove the files install wrote")
    parser.add_argument("--refresh", action="store_true", help="rebuild only if the game's Steam build changed since the last install")
    args = parser.parse_args()
    if args.refresh and not refresh_needed(MANIFEST, steam_build_id()):
        print(f"unit visuals already match game build {steam_build_id()}")
        return 0
    if args.undo:
        uninstall()
        print(f"removed ZKidz Unit Visuals from {OVERRIDES_DIR}")
        return 0
    sizes = args.factor if args.factor is not None else load_sizes()
    count = install(sizes, args.package)
    print(f"wrote {OVERRIDES_DIR / 'Local'}: {count} scale values ({'x' + str(args.factor) if args.factor else SIZES_FILE.name})")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
