"""Render explored Heroes III terrain from a matched H3M and local game sprites.

This module reads the user's installed game data. It never persists or serves
an unmasked map image. Static scenery comes from the matching original map.
"""

import base64
import gzip
import io
import json
import logging
import lzma
import struct
import threading
import zlib
from pathlib import Path

from PIL import Image

from h3tools.metadata import Savefile


logger = logging.getLogger(__name__)
TERRAIN_DEFS = (
    "DIRTTL.DEF", "SANDTL.DEF", "GRASTL.DEF", "SNOWTL.DEF", "SWMPTL.DEF",
    "ROUGTL.DEF", "SUBBTL.DEF", "LAVATL.DEF", "WATRTL.DEF", "ROCKTL.DEF",
)
RIVER_DEFS = (None, "CLRRVR.DEF", "ICYRVR.DEF", "MUDRVR.DEF", "LAVRVR.DEF")
ROAD_DEFS = (None, "DIRTRD.DEF", "GRAVRD.DEF", "COBBRD.DEF")
HOTA_TERRAINS = (("HGLNT", 124), ("WSTLT", 124))
TILE_SIZE = 32
# H3M object classes with no mutable map state: ground decorations and obstacles.
SCENERY_CLASSES = (set((0, 40, 124, 125, 139, 141, 142, 144, 145, 146,
                        175, 176, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231))
                   | set(range(114, 124)) | set(range(126, 162))
                   | set(range(165, 175)) | set(range(177, 212)))
TRANSPORT_CLASSES = {43, 44, 45, 103}
TOWN_CLASSES = {77, 98}  # Random and specified towns.
# Fixed-effect visit sites. IDs are H3M object class IDs (not sprite IDs).
# Variable rewards such as Pandora's Box cannot be inferred from their
# template alone. Explicit primary-stat Scholars are read separately below.
BONUS_OBJECTS = {
    4: ("Arena", "Stat increase", "Attack or Defense +2"),
    11: ("Buoy", "Morale and Luck", "Morale bonus"),
    14: ("Swan Pond", "Morale and Luck", "Luck bonus"),
    23: ("Marletto Tower", "Stat increase", "Defense +1"),
    28: ("Faerie Ring", "Morale and Luck", "Luck bonus"),
    30: ("Fountain of Fortune", "Morale and Luck", "Luck effect varies"),
    31: ("Fountain of Youth", "Morale and Luck", "Morale bonus"),
    32: ("Garden of Revelation", "Stat increase", "Knowledge +1"),
    38: ("Idol of Fortune", "Morale and Luck", "Morale or luck, depending on day"),
    41: ("Library of Enlightenment", "Stat increase", "All primary stats +2, level requirement"),
    47: ("School of Magic", "Stat increase", "Power or Knowledge +1, fee"),
    51: ("Mercenary Camp", "Stat increase", "Attack +1"),
    52: ("Mermaid", "Morale and Luck", "Luck bonus"),
    56: ("Oasis", "Morale and Luck", "Morale bonus"),
    61: ("Star Axis", "Stat increase", "Power +1"),
    64: ("Rally Flag", "Morale and Luck", "Morale and luck bonus"),
    96: ("Temple", "Morale and Luck", "Morale bonus"),
    107: ("School of War", "Stat increase", "Attack or Defense +1, fee"),
    110: ("Watering Hole", "Morale and Luck", "Morale bonus"),
}
# HotA uses class 144 for several unrelated visit sites. Only subtype 2 is
# the Colosseum of the Magi; other subtypes must not become stat pins.
HOTA_BONUS_OBJECTS = {
    (144, 2): ("Colosseum of the Magi", "Stat increase", "Power or Knowledge +2"),
}
ONE_WAY_COLORS = {
    0: "Blue", 1: "Pink", 2: "Orange", 3: "Yellow", 4: "Purple",
    5: "Orange", 6: "Red", 7: "Cyan", 8: "Turquoise",
    9: "Violet", 10: "Chartreuse", 11: "White",
}
TWO_WAY_COLORS = {
    0: "Green", 1: "Brown", 2: "Violet", 3: "Orange", 4: "Green",
    5: "Yellow", 6: "Red", 7: "Cyan", 9: "Pink", 10: "Turquoise",
    11: "Yellow", 12: "Black", 13: "Chartreuse", 14: "Turquoise",
    15: "Violet", 16: "Orange", 17: "Blue", 18: "Red", 19: "Pink",
    20: "Blue", 24: "Yellow",
}


class LodArchive:
    def __init__(self, path):
        self.path = Path(path)
        file_size = self.path.stat().st_size
        with self.path.open("rb") as source:
            header = source.read(92)
            if header[:4] != b"LOD\0":
                raise ValueError(f"Not a Heroes III LOD archive: {self.path}")
            count = struct.unpack_from("<I", header, 8)[0]
            if count > 100_000 or 92 + count * 32 > file_size:
                raise ValueError("LOD archive has an invalid entry count")
            xor_key = struct.unpack_from("<I", header, 12)[0]
            self.obfuscated = xor_key not in (0, 0x7e0213)
            index = source.read(count * 32)
        self.entries = {}
        for index_number in range(count):
            record = index[index_number * 32:(index_number + 1) * 32]
            if self.obfuscated:
                name_hash, offset, size, compressed = struct.unpack_from("<IIII", record)
                offset, size, compressed = offset ^ xor_key, size ^ xor_key, compressed ^ xor_key
                kind = record[16]
                name = name_hash
                if (compressed == 0) != (kind == 0):
                    raise ValueError("Invalid HotA LOD compression metadata")
            else:
                name = record[:16].split(b"\0", 1)[0].decode("ascii", "replace").upper()
                offset, size, kind, compressed = struct.unpack_from("<IIII", record, 16)
            if offset + (compressed or size) > file_size:
                raise ValueError("LOD archive entry exceeds file size")
            self.entries.setdefault(name, (offset, size, compressed, kind))

    @staticmethod
    def _name_hash(name):
        value = 0x811c9dc5
        for byte in name.lower().encode("ascii", "replace"):
            value = ((value ^ byte) * 0x01000193) & 0xffffffff
        return value

    def _key(self, name):
        return self._name_hash(name) if self.obfuscated else name.upper()

    def has(self, name):
        return self._key(name) in self.entries

    def read(self, name):
        offset, size, compressed, kind = self.entries[self._key(name)]
        with self.path.open("rb") as source:
            source.seek(offset)
            data = source.read(compressed or size)
        if compressed:
            if self.obfuscated and kind == 2:
                if len(data) < 17 or data[0] != 0:
                    raise ValueError(f"Invalid HotA LZMA entry: {name}")
                expected_size, expected_stored = struct.unpack_from("<qq", data, len(data) - 16)
                if expected_size != size or expected_stored != compressed + 5:
                    raise ValueError(f"Invalid HotA LZMA footer: {name}")
                data = lzma.decompress(data[1:-16], format=lzma.FORMAT_RAW,
                                       filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 1 << 24,
                                                 "lc": 3, "lp": 0, "pb": 2}])
            elif not self.obfuscated or kind == 3:
                data = zlib.decompress(data)
            else:
                raise ValueError(f"Unsupported HotA LOD compression type {kind}: {name}")
        if len(data) != size:
            raise ValueError(f"Corrupt LOD entry: {name}")
        return data


def decode_hota_terrain_tile(raw):
    """Decode one 32x32 Highlands or Wasteland LOD image."""
    if len(raw) < 12:
        raise ValueError("Truncated HotA terrain image")
    data_size, width, height = struct.unpack_from("<III", raw)
    if (width, height) != (TILE_SIZE, TILE_SIZE):
        raise ValueError("Unexpected HotA terrain tile dimensions")
    if data_size == width * height and len(raw) == 12 + data_size + 768:
        tile = Image.frombytes("P", (width, height), raw[12:12 + data_size])
        tile.putpalette(raw[12 + data_size:])
        return tile.convert("RGB")
    if data_size == width * height * 3 and len(raw) == 12 + data_size:
        return Image.frombytes("RGB", (width, height), raw[12:], "raw", "BGR")
    raise ValueError("Unsupported HotA terrain tile encoding")


def decode_terrain_def(raw):
    """Decode uncompressed 32x32 terrain frames from a Heroes III DEF."""
    _kind, width, height, blocks = struct.unpack_from("<IIII", raw)
    if (width, height) != (TILE_SIZE, TILE_SIZE) or blocks != 1:
        raise ValueError("Unexpected terrain DEF dimensions or block count")
    palette = raw[16:784]
    block = 784
    _block_id, frame_count, _unused1, _unused2 = struct.unpack_from("<IIII", raw, block)
    offsets_at = block + 16 + frame_count * 13
    frames = []
    for index in range(frame_count):
        offset = struct.unpack_from("<I", raw, offsets_at + index * 4)[0]
        _size, encoding, full_w, full_h, sprite_w, sprite_h, left, top = struct.unpack_from(
            "<IIIIIIii", raw, offset)
        if encoding != 0 or (full_w, full_h, sprite_w, sprite_h, left, top) != (32, 32, 32, 32, 0, 0):
            raise ValueError("Unsupported terrain DEF frame layout")
        pixels = raw[offset + 32:offset + 32 + TILE_SIZE * TILE_SIZE]
        if len(pixels) != TILE_SIZE * TILE_SIZE:
            raise ValueError("Truncated terrain DEF frame")
        frame = Image.frombytes("P", (TILE_SIZE, TILE_SIZE), pixels)
        frame.putpalette(palette)
        frames.append(frame.convert("RGB"))
    return frames


def decode_overlay_def(raw):
    """Decode the transparent river and road frames used on terrain tiles."""
    _kind, width, height, blocks = struct.unpack_from("<IIII", raw)
    if (width, height) != (32, 32) or blocks != 1:
        raise ValueError("Unexpected road or river DEF layout")
    palette = [tuple(raw[16 + i * 3:19 + i * 3]) for i in range(256)]
    _block_id, count, _u1, _u2 = struct.unpack_from("<IIII", raw, 784)
    offsets_at = 800 + count * 13
    result = []
    for frame_index in range(count):
        frame_at = struct.unpack_from("<I", raw, offsets_at + frame_index * 4)[0]
        _size, encoding, full_w, full_h, sprite_w, sprite_h, left, top = struct.unpack_from(
            "<IIIIIIii", raw, frame_at)
        if (encoding != 2 or (full_w, full_h) != (32, 32) or
                not 0 < sprite_w <= 32 or not 0 < sprite_h <= 32 or
                left < 0 or top < 0 or left + sprite_w > 32 or top + sprite_h > 32):
            raise ValueError("Unsupported road or river frame encoding")
        body = frame_at + 32
        indices = bytearray()
        for row in range(sprite_h):
            relative = struct.unpack_from("<H", raw, body + row * 2)[0]
            position = body + relative
            decoded = bytearray()
            while len(decoded) < sprite_w:
                segment = raw[position]
                position += 1
                code, length = segment >> 5, (segment & 31) + 1
                if code == 7:
                    decoded.extend(raw[position:position + length])
                    position += length
                else:
                    decoded.extend(bytes([code]) * length)
            if len(decoded) != sprite_w:
                raise ValueError("Invalid road or river scanline")
            indices.extend(decoded)
        pixels = bytearray()
        for index in indices:
            if index in (0, 5):
                pixels.extend((0, 0, 0, 0))
            elif index in (1, 2, 3, 7):
                pixels.extend((0, 0, 0, 64))
            elif index in (4, 6):
                pixels.extend((0, 0, 0, 128))
            else:
                pixels.extend((*palette[index], 255))
        cropped = Image.frombytes("RGBA", (sprite_w, sprite_h), bytes(pixels))
        full = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        full.paste(cropped, (left, top))
        result.append(full)
    return result


def decode_object_def(raw):
    """Decode the first adventure-map sprite frame (DEF encoding 3)."""
    if len(raw) < 804:
        raise ValueError("Truncated object DEF")
    _kind, width, height, blocks = struct.unpack_from("<IIII", raw)
    if blocks < 1 or not 0 < width <= 256 or not 0 < height <= 256:
        raise ValueError("Unsupported object DEF dimensions")
    palette = [tuple(raw[16 + i * 3:19 + i * 3]) for i in range(256)]
    count = struct.unpack_from("<I", raw, 788)[0]
    if not 0 < count <= 10_000:
        raise ValueError("Invalid object DEF frame count")
    offset_at = 800 + count * 13
    frame_at = struct.unpack_from("<I", raw, offset_at)[0]
    _size, encoding, full_w, full_h, sprite_w, sprite_h, left, top = struct.unpack_from(
        "<IIIIIIii", raw, frame_at)
    if (encoding != 3 or (full_w, full_h) != (width, height)
            or not 0 < sprite_w <= width or not 0 < sprite_h <= height
            or left < 0 or top < 0 or left + sprite_w > width or top + sprite_h > height):
        raise ValueError("Unsupported object DEF frame layout")
    body = frame_at + 32
    chunks = (sprite_w + 31) // 32
    pixels = bytearray()
    for row in range(sprite_h):
        for chunk in range(chunks):
            relative = struct.unpack_from("<H", raw, body + (row * chunks + chunk) * 2)[0]
            position = body + relative
            target = min(32, sprite_w - chunk * 32)
            decoded = bytearray()
            while len(decoded) < target:
                segment = raw[position]
                position += 1
                code, length = segment >> 5, (segment & 31) + 1
                if code == 7:
                    decoded.extend(raw[position:position + length])
                    position += length
                else:
                    decoded.extend(bytes([code]) * length)
            if len(decoded) != target:
                raise ValueError("Invalid object DEF scanline")
            pixels.extend(decoded)
    rgba = bytearray()
    for index in pixels:
        if index == 0:
            rgba.extend((0, 0, 0, 0))
        elif index in (1, 2, 3, 4, 5, 6, 7):
            rgba.extend((0, 0, 0, 96))
        else:
            rgba.extend((*palette[index], 255))
    cropped = Image.frombytes("RGBA", (sprite_w, sprite_h), bytes(rgba))
    full = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    full.paste(cropped, (left, top))
    return full


def parse_map_scenery(raw, terrain_start, size, levels):
    """Read the H3M's initial property-free object run after its terrain tiles."""
    at = terrain_start + size * size * levels * 7
    count = struct.unpack_from("<I", raw, at)[0]
    if not 0 < count <= 20_000:
        raise ValueError("Invalid H3M object-template count")
    at += 4
    templates = []
    for _ in range(count):
        length = struct.unpack_from("<I", raw, at)[0]
        if not 1 <= length <= 64:
            raise ValueError("Invalid H3M object sprite name")
        at += 4
        name = raw[at:at + length].decode("ascii", "replace").upper()
        at += length + 16  # footprint masks and terrain permissions
        object_class = struct.unpack_from("<I", raw, at)[0]
        at += 26  # class, subclass, editor group, ground flag, reserved
        templates.append((name, object_class))
    object_count = struct.unpack_from("<I", raw, at)[0]
    if object_count > size * size * levels * 10:
        raise ValueError("Invalid H3M object count")
    at += 4
    scenery = []
    for _ in range(object_count):
        x, y, level = struct.unpack_from("<BBB", raw, at)
        template_index = struct.unpack_from("<I", raw, at + 3)[0]
        if (template_index >= count or level >= levels or
                raw[at + 7:at + 12] != bytes(5)):
            break
        name, object_class = templates[template_index]
        if object_class not in SCENERY_CLASSES:
            break  # Later objects have varying property lengths.
        scenery.append((x, y, level, name))
        at += 12
    return scenery


def _map_object_templates(raw, terrain_start, size, levels):
    """Read H3M template records and return their object-stream start."""
    at = terrain_start + size * size * levels * 7
    count = struct.unpack_from("<I", raw, at)[0]
    if not 0 < count <= 20_000:
        raise ValueError("Invalid H3M object-template count")
    at += 4
    templates = []
    for _ in range(count):
        length = struct.unpack_from("<I", raw, at)[0]
        if not 1 <= length <= 64:
            raise ValueError("Invalid H3M object sprite name")
        at += 4
        name = raw[at:at + length].decode("ascii", "replace").upper()
        at += length + 16
        object_class, subclass = struct.unpack_from("<II", raw, at)
        at += 26
        templates.append((name, object_class, subclass))
    object_count = struct.unpack_from("<I", raw, at)[0]
    if object_count > size * size * levels * 10:
        raise ValueError("Invalid H3M object count")
    return templates, at + 4


def _find_template_objects(raw, start, templates, classes, size, levels):
    """Find known body-free H3M objects by their 12-byte object header.

    Variable-length object bodies prevent a cheap walk through the complete
    stream. The object header still identifies a template and coordinates;
    callers may inspect a fixed-size body immediately after it.
    """
    result = []
    seen = set()
    for index, (name, object_class, subclass) in enumerate(templates):
        if object_class not in classes:
            continue
        signature = struct.pack("<I", index) + bytes(5)
        search_at = start + 3
        while (found := raw.find(signature, search_at)) >= 0:
            search_at = found + 1
            x, y, level = raw[found - 3:found]
            key = (x, y, level, object_class, subclass)
            if x >= size or y >= size or level >= levels or key in seen:
                continue
            seen.add(key)
            result.append({"x": x, "y": y, "level": level, "name": name,
                           "object_class": object_class, "subclass": subclass,
                           "template_index": index, "record_offset": found - 3})
    return result


def parse_map_transports(raw, terrain_start, size, levels):
    """Locate fixed-layout transport objects by their H3M template signatures."""
    templates, start = _map_object_templates(raw, terrain_start, size, levels)
    result = []
    for item in _find_template_objects(raw, start, templates, TRANSPORT_CLASSES, size, levels):
        object_class, subclass = item["object_class"], item["subclass"]
        if object_class == 103:
            title, category = "Underground Gate", "Underground gate"
        else:
            colors = TWO_WAY_COLORS if object_class == 45 else ONE_WAY_COLORS
            color = colors.get(subclass)
            if color is None:
                logger.debug("Unknown portal color for class %s subclass %s", object_class, subclass)
                continue
            direction = {43: "One-way entrance", 44: "One-way exit", 45: "Two-way"}[object_class]
            monolith = (subclass in (0, 1, 2, 3, 8, 9, 10, 11)
                        if object_class in (43, 44) else
                        subclass in (0, 1, 2, 3, 9, 10, 11, 12, 17, 18))
            kind = "Monolith" if monolith else "Portal"
            title, category = f"{color} {direction} {kind}", "Portal"
        result.append({**item, "title": title, "category": category})
    return result


def parse_map_towns(raw, terrain_start, size, levels, town_anchors):
    """Locate town sprites, verified against the current save's town positions."""
    templates, start = _map_object_templates(raw, terrain_start, size, levels)
    return [item for item in _find_template_objects(raw, start, templates,
                                                    TOWN_CLASSES, size, levels)
            if (item["level"], item["x"], item["y"]) in town_anchors]


def parse_map_bonuses(raw, terrain_start, size, levels):
    """Locate standard stat, morale and luck visit sites in the matched map."""
    templates, start = _map_object_templates(raw, terrain_start, size, levels)
    result = [{**item, "title": BONUS_OBJECTS[item["object_class"]][0],
               "category": BONUS_OBJECTS[item["object_class"]][1],
               "notes": BONUS_OBJECTS[item["object_class"]][2]}
              for item in _find_template_objects(raw, start, templates, BONUS_OBJECTS, size, levels)]
    for item in _find_template_objects(raw, start, templates, {144}, size, levels):
        bonus = HOTA_BONUS_OBJECTS.get((item["object_class"], item["subclass"]))
        if bonus is not None:
            result.append({**item, "title": bonus[0], "category": bonus[1], "notes": bonus[2]})
    # Scholars have an eight-byte body: reward type 0 means a named primary
    # stat, followed by the stat index (Attack, Defense, Power, Knowledge).
    # Secondary skills, spells and random Scholars are intentionally omitted.
    stats = ("Attack", "Defense", "Power", "Knowledge")
    last_scholar_end = -1
    scholars = sorted(_find_template_objects(raw, start, templates, {81}, size, levels),
                      key=lambda item: item["record_offset"])
    for item in scholars:
        if item["record_offset"] < last_scholar_end:
            continue
        last_scholar_end = item["record_offset"] + 20
        signature = struct.pack("<I", item["template_index"]) + bytes(5)
        # Locate this exact object's header, not just its template: several
        # Scholars can share a template while granting different rewards.
        prefix = bytes((item["x"], item["y"], item["level"])) + signature
        found = item["record_offset"] if raw[item["record_offset"]:item["record_offset"] + 12] == prefix else -1
        if found < 0 or found + 14 > len(raw):
            continue
        reward_type, stat = raw[found + 12:found + 14]
        if reward_type == 0 and stat < len(stats):
            result.append({**item, "title": f"Scholar ({stats[stat]})",
                           "category": "Stat increase", "notes": f"{stats[stat]} +1"})
    return result


def parse_map_dragon_utopias(raw, terrain_start, size, levels):
    """Locate Dragon Utopias (H3M object class 25) in the matched map."""
    templates, start = _map_object_templates(raw, terrain_start, size, levels)
    return [{**item, "title": "Dragon Utopia", "category": "Dragon Utopia",
             "notes": "Location from the original map; cleared status unknown"}
            for item in _find_template_objects(raw, start, templates, {25}, size, levels)]


def creature_level(creature_id):
    """Return the 1–7 map-helper tier for a Heroes III/HotA creature ID."""
    if 0 <= creature_id < 112:  # Eight original towns, seven base/upgrade pairs each.
        return (creature_id % 14) // 2 + 1
    if 0x99 <= creature_id <= 0xA6:  # Cove pairs.
        return (creature_id - 0x99) // 2 + 1
    if 0xBA <= creature_id <= 0xC7:  # Bulwark pairs.
        return (creature_id - 0xBA) // 2 + 1
    if 0xAC <= creature_id <= 0xB5:  # Factory levels 2–6.
        return (creature_id - 0xAC) // 2 + 2
    if 0xB6 <= creature_id <= 0xB9:  # Factory's two level-7 lines.
        return 7
    extras = {
        # Conflux (the IDs are not in dwelling order).
        0x70: 2, 0x7F: 2, 0x71: 5, 0x7D: 5, 0x72: 4, 0x81: 4,
        0x73: 3, 0x7B: 3, 0x76: 1, 0x77: 1, 0x78: 6, 0x79: 6,
        0x82: 7, 0x83: 7,
        # Neutral creatures. Special dragons are grouped with level 7 so the
        # sidebar keeps the requested seven-level scale.
        0x74: 5, 0x75: 6, 0x84: 7, 0x85: 7, 0x86: 7, 0x87: 7,
        0x88: 6, 0x89: 4, 0x8A: 1, 0x8B: 1, 0x8C: 2,
        0x8D: 3, 0x8E: 3, 0x8F: 2, 0x90: 5,
        0x97: 3,  # Sea Dog is a third upgrade of Cove's level-3 Pirate.
        0xA7: 4, 0xA8: 5, 0xA9: 2, 0xAA: 4,
        0xAB: 1,  # Factory Halfling Grenadier upgrades the level-1 Halfling.
    }
    return extras.get(creature_id)


def parse_map_creatures(raw, terrain_start, size, levels):
    """Locate fixed creature stacks and their types in the original H3M map."""
    templates, start = _map_object_templates(raw, terrain_start, size, levels)
    result = []
    for item in _find_template_objects(raw, start, templates, {54}, size, levels):
        creature_id = item["subclass"]
        level = creature_level(creature_id)
        name = Savefile.creature_mapping.get(creature_id)
        if name is None:
            name = "Magma Elemental" if creature_id == 0x7D else f"Unknown creature ({creature_id})"
        result.append({**item, "title": name,
                       "category": "Creature",
                       "creature_level": level,
                       "notes": "Neutral stack in latest save; joining and count unknown"})
    return result


def active_map_creatures(save_tiles, map_creatures, shift, size, levels):
    """Keep only stacks still present in the current save's map tile records.

    The save extractor begins `shift` terrain tiles into the map. The object
    class in each tile record refers to the following map coordinate.
    """
    by_position = {(item["level"], item["x"], item["y"]): item
                   for item in map_creatures}
    result = []
    for index, tile in enumerate(save_tiles):
        if len(tile) <= 8 or tile[8] != 54:
            continue
        position = index + shift + 1
        if position >= size * size * levels:
            continue
        level, offset = divmod(position, size * size)
        y, x = divmod(offset, size)
        item = by_position.get((level, x, y))
        if item is not None:
            result.append(item)
    return result


def _install_directory(processed_dir, explicit=None):
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not (root / "Data" / "H3sprite.lod").is_file():
            raise FileNotFoundError(f"No Data/H3sprite.lod in {root}")
        state_path = Path(processed_dir) / ".incremental_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else None
        return root, state
    state_path = Path(processed_dir) / ".incremental_state.json"
    if not state_path.is_file():
        return None, None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    save_dir = Path(state["source_directory"])
    for root in (save_dir, *save_dir.parents):
        if (root / "Data" / "H3sprite.lod").is_file():
            return root, state
    return None, state


def _candidate_start(raw, save_tiles, tile_count):
    """Find terrain start, including save-extractor shifts before tile zero."""
    prefix = save_tiles[0][:6]
    search_at = 0
    while True:
        found = raw.find(prefix, search_at)
        if found < 0:
            return None
        search_at = found + 1
        for shift in range(65):
            start = found - shift * 7
            end = start + tile_count * 7
            if start < 0 or end + 12 > len(raw):
                continue
            template_count, name_size = struct.unpack_from("<II", raw, end)
            if not 1 <= template_count <= 20_000 or not 1 <= name_size <= 64:
                continue
            name = raw[end + 8:end + 8 + name_size].lower()
            if b".def" not in name:
                continue
            matches = sum(raw[found + i * 7:found + i * 7 + 6] == save_tiles[i][:6]
                          for i in range(min(128, tile_count - shift)))
            if matches < min(128, tile_count - shift) - 2:
                continue
            return start, shift


def match_h3m(install_dir, save_tiles, size, levels, town_anchors=None):
    tile_count = size * size * levels
    if len(save_tiles) != tile_count:
        return None
    candidates = [*(install_dir / "random_maps").glob("*.h3m"),
                  *(install_dir / "Maps").glob("*.h3m")]
    for path in candidates:
        try:
            with gzip.open(path, "rb") as source:
                raw = source.read()
            match = _candidate_start(raw, save_tiles, tile_count)
            if match is None:
                continue
            start, shift = match
            compared = tile_count - shift
            mismatches = sum(raw[start + (i + shift) * 7:start + (i + shift) * 7 + 6]
                             != save_tiles[i][:6] for i in range(compared))
            if mismatches <= max(8, tile_count // 10_000):
                logger.info("Matched map %s (%s save tile differences, shift %s)",
                            path, mismatches, shift)
                try:
                    scenery = parse_map_scenery(raw, start, size, levels)
                    transports = parse_map_transports(raw, start, size, levels)
                    towns = parse_map_towns(raw, start, size, levels, town_anchors or set())
                    bonuses = parse_map_bonuses(raw, start, size, levels)
                    utopias = parse_map_dragon_utopias(raw, start, size, levels)
                    creatures = parse_map_creatures(raw, start, size, levels)
                except (ValueError, IndexError, struct.error) as exc:
                    logger.warning("Could not read H3M scenery in %s: %s", path, exc)
                    scenery = []
                    transports = []
                    towns = []
                    bonuses = []
                    utopias = []
                    creatures = []
                return (path, raw[start:start + tile_count * 7], scenery, transports,
                        towns, bonuses, utopias, creatures, shift)
        except (OSError, EOFError, ValueError, struct.error):
            continue
    return None


class TerrainRenderer:
    def __init__(self, terrain, archive, scenery=None, object_archives=None,
                 transports=None, hota_archive=None, bonuses=None, utopias=None,
                 creature_templates=None, creature_tile_shift=0, creatures=None,
                 towns=None):
        self.terrain = terrain
        self.scenery = scenery or []
        self.transports = transports or []
        self.towns = towns or []
        self.bonuses = bonuses or []
        self.utopias = utopias or []
        self.creature_templates = creature_templates or []
        self.creature_tile_shift = creature_tile_shift
        self.creatures = creatures or []
        rendered_objects = (self.transports + self.towns + self.utopias +
                            [item for item in self.bonuses
                             if item.get("category") == "Stat increase"])
        self.sprite_objects = sorted(
            set(self.scenery) | {(item["x"], item["y"], item["level"], item["name"])
                                 for item in rendered_objects},
            key=lambda item: (item[2], item[1], item[0]),
        )
        self.object_archives = object_archives or [archive]
        self.object_frames = {}
        self._overview_bases = {}
        self._overview_lock = threading.Lock()
        self.frames = [decode_terrain_def(archive.read(name)) for name in TERRAIN_DEFS]
        for prefix, count in HOTA_TERRAINS:
            tiles = []
            if hota_archive is not None:
                try:
                    tiles = [decode_hota_terrain_tile(hota_archive.read(f"{prefix}{index:03}.PCX"))
                             for index in range(count)]
                except (KeyError, ValueError, lzma.LZMAError, zlib.error) as exc:
                    logger.warning("HotA terrain %s unavailable: %s", prefix, exc)
                    tiles = []
            self.frames.append(tiles)
        self.rivers = [None] + [decode_overlay_def(archive.read(name)) for name in RIVER_DEFS[1:]]
        self.roads = [None] + [decode_overlay_def(archive.read(name)) for name in ROAD_DEFS[1:]]
        self.fallback = Image.new("RGB", (TILE_SIZE, TILE_SIZE), "#806c50")

    @staticmethod
    def _flip(frame, flags, shift):
        if flags & (1 << shift):
            frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if flags & (2 << shift):
            frame = frame.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        return frame

    def _object_frame(self, name):
        if name not in self.object_frames:
            for archive in self.object_archives:
                has_sprite = archive.has(name) if hasattr(archive, "has") else name in archive.entries
                if has_sprite:
                    try:
                        self.object_frames[name] = decode_object_def(archive.read(name))
                    except (ValueError, IndexError, struct.error, lzma.LZMAError, zlib.error) as exc:
                        logger.debug("Unsupported scenery sprite %s: %s", name, exc)
                        self.object_frames[name] = None
                    break
            else:
                self.object_frames[name] = None
        return self.object_frames[name]

    def _overview_base(self, level, size, tile_size):
        """Build a compact map image kept only in server memory."""
        key = (level, size, tile_size)
        with self._overview_lock:
            if key in self._overview_bases:
                return self._overview_bases[key]
            image = Image.new("RGB", (size * tile_size, size * tile_size), "#15171d")
            terrain_frames = {}
            overlay_frames = {}
            for y in range(size):
                for x in range(size):
                    offset = ((level * size * size) + y * size + x) * 7
                    tile = self.terrain[offset:offset + 7]
                    terrain_type, view = tile[:2]
                    frame_key = (terrain_type, view, tile[6] & 3)
                    if frame_key not in terrain_frames:
                        if terrain_type < len(self.frames) and view < len(self.frames[terrain_type]):
                            frame = self._flip(self.frames[terrain_type][view], tile[6], 0)
                            terrain_frames[frame_key] = frame.resize(
                                (tile_size, tile_size), Image.Resampling.BILINEAR)
                        else:
                            terrain_frames[frame_key] = self.fallback.resize((tile_size, tile_size))
                    destination = (x * tile_size, y * tile_size)
                    image.paste(terrain_frames[frame_key], destination)
                    for layer, kind, index, view_index, shift in (
                            ("river", self.rivers, tile[2], tile[3], 2),
                            ("road", self.roads, tile[4], tile[5], 4)):
                        if not (0 < index < len(kind) and view_index < len(kind[index])):
                            continue
                        overlay_key = (layer, index, view_index, tile[6] & (3 << shift))
                        if overlay_key not in overlay_frames:
                            overlay = self._flip(kind[index][view_index], tile[6], shift)
                            overlay_frames[overlay_key] = overlay.resize(
                                (tile_size, tile_size), Image.Resampling.BILINEAR)
                        overlay = overlay_frames[overlay_key]
                        image.paste(overlay, destination, overlay)

            sprites = {}
            for x, y, z, name in self.sprite_objects:
                if z != level:
                    continue
                if name not in sprites:
                    original = self._object_frame(name)
                    sprites[name] = (original.resize(
                        (max(1, round(original.width * tile_size / TILE_SIZE)),
                         max(1, round(original.height * tile_size / TILE_SIZE))),
                        Image.Resampling.BILINEAR) if original is not None else None)
                sprite = sprites[name]
                if sprite is not None:
                    image.paste(sprite, ((x + 1) * tile_size - sprite.width,
                                         (y + 1) * tile_size - sprite.height), sprite)
            self._overview_bases[key] = image
            return image

    def render_overview_data_url(self, mask, level, tile_size=8):
        """Render a compact fog-clipped map for the dashboard's day slider."""
        size = mask.shape[1]
        base = self._overview_base(level, size, tile_size)
        visible = Image.frombytes("L", (size, size),
                                  (mask[level].astype("uint8") * 255).tobytes())
        visible = visible.resize(base.size, Image.Resampling.NEAREST)
        image = Image.new("RGB", base.size, "#15171d")
        image.paste(base, (0, 0), visible)
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=False)
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")

    def render_png(self, mask, level):
        size = mask.shape[1]
        image = Image.new("RGB", (size * TILE_SIZE, size * TILE_SIZE), "#15171d")
        for y in range(size):
            for x in range(size):
                if not mask[level, y, x]:
                    continue
                offset = ((level * size * size) + (y * size) + x) * 7
                tile = self.terrain[offset:offset + 7]
                terrain_type, view = tile[:2]
                if terrain_type < len(self.frames) and view < len(self.frames[terrain_type]):
                    frame = self._flip(self.frames[terrain_type][view], tile[6], 0)
                else:
                    frame = self.fallback
                destination = (x * TILE_SIZE, y * TILE_SIZE)
                image.paste(frame, destination)
                for kind, index, view_index, shift in ((self.rivers, tile[2], tile[3], 2),
                                                       (self.roads, tile[4], tile[5], 4)):
                    if 0 < index < len(kind) and view_index < len(kind[index]):
                        overlay = self._flip(kind[index][view_index], tile[6], shift)
                        image.paste(overlay, destination, overlay)
        if self.sprite_objects:
            objects = Image.new("RGBA", image.size, (0, 0, 0, 0))
            for x, y, z, name in self.sprite_objects:
                if z != level:
                    continue
                sprite = self._object_frame(name)
                if sprite is None:
                    continue
                position = ((x + 1) * TILE_SIZE - sprite.width,
                            (y + 1) * TILE_SIZE - sprite.height)
                objects.alpha_composite(sprite, position)
            # A sprite may span many tiles. Strip every covered tile before
            # encoding the image so the browser never receives hidden pixels.
            from PIL import ImageDraw
            draw = ImageDraw.Draw(objects)
            for y in range(size):
                for x in range(size):
                    if not mask[level, y, x]:
                        left, top = x * TILE_SIZE, y * TILE_SIZE
                        draw.rectangle((left, top, left + TILE_SIZE - 1,
                                        top + TILE_SIZE - 1), fill=(0, 0, 0, 0))
            image.paste(objects, (0, 0), objects)
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=False)
        return output.getvalue()

    def render_data_url(self, mask, level):
        return "data:image/png;base64," + base64.b64encode(self.render_png(mask, level)).decode("ascii")


def load_terrain_renderer(processed_dir, size, levels, install_dir=None):
    """Return renderer and matched map path, or (None, reason)."""
    try:
        root, state = _install_directory(processed_dir, install_dir)
        if root is None:
            return None, "Game installation or source save directory was not found."
        if state is None:
            state_path = Path(processed_dir) / ".incremental_state.json"
            if not state_path.is_file():
                return None, "Source save metadata was not found."
            state = json.loads(state_path.read_text(encoding="utf-8"))
        save_dir = Path(state["source_directory"])
        latest = state["saves"][-1]["filename"]
        save = Savefile(str(save_dir / latest), parse_heroes=False)
        save_tiles = [tile for _offset, tile, _length in save.maptiles]
        town_anchors = set()
        for town in save.towns:
            coords = town.get("coords")
            if not isinstance(coords, (list, tuple)) or len(coords) != 3:
                continue
            x, y, layer = coords
            z = 0 if layer in (0, "Surface") else 1 if layer in (1, "Underground") else None
            if (z is not None and isinstance(x, int) and isinstance(y, int)
                    and 0 <= x + 2 < size and 0 <= y < size):
                town_anchors.add((z, x + 2, y))
        match = match_h3m(root, save_tiles, size, levels, town_anchors)
        if match is None:
            return None, "No exact generated .h3m map matched the latest save."
        map_path, terrain, scenery, transports, towns, bonuses, utopias, creature_templates, shift = match
        creatures = active_map_creatures(save_tiles, creature_templates, shift, size, levels)
        archive = LodArchive(root / "Data" / "H3sprite.lod")
        object_archives = [archive]
        hota_archive = None
        for name in ("HotA.lod", "HotA_ext.lod", "H3ab_spr.lod", "H3psprit.lod"):
            path = root / "Data" / name
            if path.is_file():
                try:
                    candidate = LodArchive(path)
                    if name == "HotA.lod":
                        hota_archive = candidate
                        object_archives.insert(0, candidate)
                    else:
                        object_archives.append(candidate)
                except ValueError:
                    logger.debug("Skipping unsupported sprite archive %s", path)
        return TerrainRenderer(terrain, archive, scenery, object_archives,
                               transports, hota_archive, bonuses, utopias,
                               creature_templates, shift, creatures, towns), str(map_path)
    except (OSError, ValueError, KeyError, IndexError, struct.error) as exc:
        logger.warning("Terrain graphics unavailable: %s", exc)
        return None, str(exc)
