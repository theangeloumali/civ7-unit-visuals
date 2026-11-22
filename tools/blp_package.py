"""Civ VII CIVBLP package layout, enough to grow one vector safely (format per ghost-ng/blp-studio's parser).

Package (at the file header's 0x8): 16-byte preamble, then five stripes (u32 offset, u32 size) for ResourceLinker,
PackageBlock, TempData, TypeInfo and RootTypeName, then u32 linkerDataOffset. The allocation table starts at
TempData + linkerDataOffset: 40-byte entries (u64 stripe, u32 offset, u32 size, u32 count, u64 user, u64 type),
offsets relative to their stripe. Pointers are 1-based table indexes, so appending never renumbers anything.
"""
import re
import struct
from collections import namedtuple

ENTRY_SIZE = 40
ENTRY_FORMAT = "<QIIIxxxxQQ"
PREAMBLE_SIZE = 16
PACKAGE_BLOCK, TEMP_DATA = 1, 2
SECTION_ALIGNMENT = 0x200

Allocation = namedtuple("Allocation", "stripe offset size count user_data type_name")


def align(value, alignment=16):
    return -(-value // alignment) * alignment


class Package:
    def __init__(self, data):
        self.data = data
        self.start = struct.unpack_from("<I", data, 0x8)[0]
        self.size = struct.unpack_from("<I", data, 0xC)[0]
        self.header_at = self.start + PREAMBLE_SIZE
        self.stripes = [list(struct.unpack_from("<II", data, self.header_at + 8 * i)) for i in range(5)]
        self.linker = struct.unpack_from("<I", data, self.header_at + 40)[0]
        temp_offset, temp_size = self.stripes[TEMP_DATA]
        self.table_at = self.start + temp_offset + self.linker
        self.entry_count = (temp_size - self.linker) // ENTRY_SIZE

    def allocation(self, pointer):
        return Allocation(*struct.unpack_from(ENTRY_FORMAT, self.data, self.table_at + (pointer - 1) * ENTRY_SIZE))

    def allocation_at(self, allocation):
        stripe = PACKAGE_BLOCK if allocation.stripe == 0 else TEMP_DATA
        return self.start + self.stripes[stripe][0] + allocation.offset

    def allocation_bytes(self, pointer):
        allocation = self.allocation(pointer)
        at = self.allocation_at(allocation)
        return self.data[at : at + allocation.size]

    def allocation_ids(self, pointer):
        """Element ids of a pointer array: count entries of <u32 id><u32 0>."""
        allocation = self.allocation(pointer)
        at = self.allocation_at(allocation)
        return [struct.unpack_from("<I", self.data, at + 8 * i)[0] for i in range(allocation.count)]

    def field_name_at(self, string_pointer_at):
        """Name of the field record whose String pointer is at string_pointer_at, or None."""
        pointer = struct.unpack_from("<Q", self.data, string_pointer_at)[0]
        if not 0 < pointer <= self.entry_count:
            return None
        string = self.allocation_bytes(pointer)
        if len(string) < 8:
            return None
        text_pointer = struct.unpack_from("<Q", string, 0)[0]
        if not 0 < text_pointer <= self.entry_count:
            return None
        text = self.allocation_bytes(text_pointer)
        length = struct.unpack_from("<I", text, 4)[0] if len(text) >= 8 else 0
        return text[8 : 8 + length].decode(errors="replace") if length else None

    def tail_padding(self):
        """Zero bytes between the end of TempData and the end of the package region."""
        temp_offset, temp_size = self.stripes[TEMP_DATA]
        return self.size - (temp_offset + temp_size)


def append_allocation(data, content, like, count=None):
    """(new data, new pointer): content appended at the end of PackageBlock with one new table entry.

    The entry copies the stripe-independent metadata of allocation `like`; every existing allocation keeps its
    index and bytes. Offsets inside TempData shift by the growth, so callers re-read them from the result.
    """
    package = Package(data)
    model = package.allocation(like)
    block_offset, block_size = package.stripes[PACKAGE_BLOCK]
    temp_offset, temp_size = package.stripes[TEMP_DATA]
    new_offset = align(block_size)
    lead = new_offset - block_size
    # A multiple of 16 keeps TempData's alignment unchanged.
    block_growth = align(lead + len(content))
    inserted = b"\x00" * lead + content + b"\x00" * (block_growth - lead - len(content))
    count = len(content) if count is None else count
    entry = struct.pack(ENTRY_FORMAT, 0, new_offset, len(content), count, model.user_data, model.type_name)

    blob = bytearray(data)
    struct.pack_into("<II", blob, package.header_at + 8 * PACKAGE_BLOCK, block_offset, block_size + block_growth)
    struct.pack_into("<II", blob, package.header_at + 8 * TEMP_DATA, temp_offset + block_growth, temp_size + ENTRY_SIZE)

    block_end = package.start + block_offset + block_size
    temp_end = package.start + temp_offset + temp_size
    package_end = package.start + package.size
    growth = block_growth + ENTRY_SIZE
    head = blob[:block_end] + inserted + blob[block_end:temp_end] + entry
    pointer = package.entry_count + 1
    if package.tail_padding() >= growth:
        return bytes(head + blob[temp_end + growth : package_end] + blob[package_end:]), pointer
    section_growth = align(growth - package.tail_padding(), SECTION_ALIGNMENT)
    for field in (0xC, 0x10, 0x18):
        struct.pack_into("<I", head, field, struct.unpack_from("<I", head, field)[0] + section_growth)
    # Everything between TempData's end and the package end is zero padding, so it is rebuilt at the new size.
    filler = b"\x00" * (package.tail_padding() + section_growth - growth)
    return bytes(head + filler + blob[package_end:]), pointer


def grow_vector(data, vector_at, target_count):
    """Repoint the vector at vector_at (u64 pointer, u32 count, u32 capacity) to a new, longer array that repeats its ids."""
    package = Package(data)
    pointer, count, _capacity = struct.unpack_from("<QII", data, vector_at)
    ids = package.allocation_ids(pointer)[:count]
    content = b"".join(struct.pack("<II", ids[i % count], 0) for i in range(target_count))
    # The vector is written before the append, so a vector inside TempData moves with it.
    blob = bytearray(data)
    struct.pack_into("<QII", blob, vector_at, package.entry_count + 1, target_count, target_count)
    grown, _pointer = append_allocation(bytes(blob), content, like=pointer, count=target_count)
    return grown


FIELD_MARKER_VALUE, FIELD_MARKER_VECTOR = 0xA, 0xC


def field_name_definition(name):
    encoded = name.encode()
    return struct.pack("<II", len(encoded) + 1, len(encoded)) + encoded + b"\x00"


def field_value_offsets(data, name):
    """Offsets of a named field's u32/f32 values: <value><u32 0><u32 field id>, id 0x18 before the inline name."""
    name_at = data.find(field_name_definition(name))
    if name_at == -1:
        return []
    field_id = struct.unpack_from("<I", data, name_at + 8 - 0x18)[0]
    marker = struct.pack("<II", 0, field_id)
    offsets, position = [], data.find(marker, 4)
    while position != -1:
        offsets.append(position - 4)
        position = data.find(marker, position + 1)
    return offsets


def raise_field_minimum(data, name, minimum):
    blob = bytearray(data)
    for offset in field_value_offsets(data, name):
        if struct.unpack_from("<I", blob, offset)[0] < minimum:
            struct.pack_into("<I", blob, offset, minimum)
    return bytes(blob)




def find_named_vectors(data, name):
    """[(vector offset, count)] for vector-valued field records named `name`."""
    package = Package(data)
    marker = struct.pack("<Q", FIELD_MARKER_VECTOR)
    found, position = [], data.find(marker)
    while position != -1:
        vector_at = position + 8
        if (
            position >= 16
            and struct.unpack_from("<Q", data, position - 16)[0] == FIELD_MARKER_VALUE
            and package.field_name_at(position - 8) == name
        ):
            found.append((vector_at, struct.unpack_from("<I", data, vector_at + 8)[0]))
        position = data.find(marker, position + 1)
    return found


ASSET_ENTRY_TYPE = "PackageAssetEntry_Metadata0"
ENTRY_NAME_AT, ENTRY_VALUES_AT = 0x28, 0x38
TUPLE_NAME_AT, TUPLE_VALUE_AT = 16, 24


def fnv1a(text):
    value = 0x811C9DC5
    for byte in text.encode():
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def _type_name(package, allocation, cache):
    if allocation.type_name not in cache:
        cache[allocation.type_name] = package.allocation_bytes(allocation.type_name).split(b"\x00")[0].decode(errors="replace")
    return cache[allocation.type_name]


def _text(package, pointer):
    """A char allocation stored as <u32 len+1><u32 len><text>."""
    raw = package.allocation_bytes(pointer)
    length = struct.unpack_from("<I", raw, 4)[0] if len(raw) >= 8 else 0
    return raw[8 : 8 + length].decode(errors="replace")


def _value_set_fields(package, entry_pointer):
    """{field name: offset of its value} from an asset entry's ValueSet of named TupleValues."""
    entry = package.allocation_bytes(entry_pointer)
    value_set = package.allocation_bytes(struct.unpack_from("<Q", entry, ENTRY_VALUES_AT)[0])
    fields = {}
    for value_pointer in package.allocation_ids(struct.unpack_from("<Q", value_set, 0)[0]):
        at = package.allocation_at(package.allocation(value_pointer))
        name = package.field_name_at(at + TUPLE_NAME_AT)
        if name:
            fields[name] = at + TUPLE_VALUE_AT
    return fields


def asset_entries(data, prefix):
    """{asset name: entry pointer} for every asset entry whose name starts with prefix."""
    package, cache, entries = Package(data), {}, {}
    for pointer in range(1, package.entry_count + 1):
        allocation = package.allocation(pointer)
        if allocation.size < ENTRY_VALUES_AT + 8 or _type_name(package, allocation, cache) != ASSET_ENTRY_TYPE:
            continue
        name = _text(package, struct.unpack_from("<Q", package.allocation_bytes(pointer), ENTRY_NAME_AT)[0])
        if name.startswith(prefix):
            entries[name] = pointer
    return entries


def asset_fields(data, asset_name):
    return _value_set_fields(Package(data), asset_entries(data, asset_name)[asset_name])


FLOAT_FIELDS = {"SpacingX", "SpacingY", "SpacingMultiplier", "PerRowIncrement", "StaggerIncrement", "RandomLeftRight", "RandomFrontBack"}
DEFAULT_SPREAD = [{"match": ".*", "stackedOnly": True, "set": {"SpacingMultiplier": 1.0, "FirstRowWidth": 2}}]


def _is_stacked(blob, fields):
    """SpacingMultiplier 0 with one slot per row draws every member on one point."""
    if not {"SpacingMultiplier", "FirstRowWidth"} <= fields.keys():
        return False
    return struct.unpack_from("<f", blob, fields["SpacingMultiplier"])[0] == 0.0 and struct.unpack_from("<I", blob, fields["FirstRowWidth"])[0] == 1


def apply_formation_rules(data, rules=DEFAULT_SPREAD):
    """Give each formation the values of the first rule whose regex matches its name.

    A `stackedOnly` rule skips formations that already spread their members.
    """
    blob = bytearray(data)
    package = Package(data)
    for name, entry_pointer in asset_entries(data, "Formation").items():
        fields = _value_set_fields(package, entry_pointer)
        rule = next((rule for rule in rules if re.search(rule["match"], name)), None)
        if rule is None or (rule.get("stackedOnly") and not _is_stacked(blob, fields)):
            continue
        for field, value in rule["set"].items():
            if field in fields:
                struct.pack_into("<f" if field in FLOAT_FIELDS else "<I", blob, fields[field], value)
    return bytes(blob)


# A formation reference (BLPEntryValue) holds String pointers; +16 from the field's value offset is the asset name.
ENTRY_ASSET_NAME_AT, ENTRY_PACKAGE_FILE_AT = 16, 24


def _string_target(package, string_at):
    """The char allocation a String field points at, or 0 for an empty string."""
    string_pointer = struct.unpack_from("<Q", package.data, string_at)[0]
    return struct.unpack_from("<Q", package.allocation_bytes(string_pointer), 0)[0]


def entry_asset_name(data, asset_name, field):
    package = Package(data)
    target = _string_target(package, asset_fields(data, asset_name)[field] + ENTRY_ASSET_NAME_AT)
    return _text(package, target) if target else ""


def repoint_formation(data, unit, formation):
    """Point a unit's Formation and CombatFormation at another formation by name; formations resolve globally by name."""
    package = Package(data)
    fields = asset_fields(data, unit)
    text_like = _string_target(package, fields["Formation"] + ENTRY_ASSET_NAME_AT)
    data, text_pointer = append_allocation(data, field_name_definition(formation), like=text_like)
    package = Package(data)
    fields = asset_fields(data, unit)
    package_file = _string_target(package, fields["Formation"] + ENTRY_PACKAGE_FILE_AT)
    blob = bytearray(data)
    for field in ("Formation", "CombatFormation"):
        for offset, target in ((ENTRY_ASSET_NAME_AT, text_pointer), (ENTRY_PACKAGE_FILE_AT, package_file)):
            string_pointer = struct.unpack_from("<Q", blob, fields[field] + offset)[0]
            struct.pack_into("<Q", blob, package.allocation_at(package.allocation(string_pointer)), target)
    return bytes(blob)


def _override_position_offsets(data, formation):
    """File offsets of each fixed slot's Position (three floats) in a formation's Overrides list."""
    package = Package(data)
    overrides_at = asset_fields(data, formation)["Overrides"]
    pointer, count = struct.unpack_from("<QI", data, overrides_at + 8)
    offsets = []
    for slot in package.allocation_ids(pointer)[:count] if pointer else []:
        children_pointer, children = struct.unpack_from("<QI", package.allocation_bytes(slot), TUPLE_VALUE_AT)
        for child in package.allocation_ids(children_pointer)[:children]:
            child_at = package.allocation_at(package.allocation(child))
            if package.field_name_at(child_at + TUPLE_NAME_AT) == "Position":
                offsets.append(child_at + TUPLE_VALUE_AT)
    return offsets


def override_positions(data, formation):
    return [tuple(round(v, 2) for v in struct.unpack_from("<ff", data, at)) for at in _override_position_offsets(data, formation)]


def scale_override_positions(data, formation, factor):
    blob = bytearray(data)
    for at in _override_position_offsets(data, formation):
        x, y = struct.unpack_from("<ff", blob, at)
        struct.pack_into("<ff", blob, at, x * factor, y * factor)
    return bytes(blob)
