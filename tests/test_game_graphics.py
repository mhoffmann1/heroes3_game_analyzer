import base64
import io
import lzma
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from game_graphics import (LodArchive, TerrainRenderer, _candidate_start,
                           decode_hota_terrain_tile, decode_object_def,
                           decode_terrain_def, parse_map_bonuses, parse_map_dragon_utopias,
                           parse_map_scenery,
                           parse_map_transports)


def simple_def(rgb):
    palette = bytearray(768)
    palette[3:6] = bytes(rgb)
    header = struct.pack("<IIII", 69, 32, 32, 1)
    block = struct.pack("<IIII", 0, 1, 0, 0)
    name = b"TILE0000.DEF\0"
    offset = len(header) + len(palette) + len(block) + len(name) + 4
    frame = struct.pack("<IIIIIIii", 1024, 0, 32, 32, 32, 32, 0, 0)
    return header + palette + block + name + struct.pack("<I", offset) + frame + bytes([1]) * 1024


def simple_overlay_def():
    palette = bytes(768)
    header = struct.pack("<IIII", 69, 32, 32, 1)
    block = struct.pack("<IIII", 0, 1, 0, 0)
    name = b"TILE0000.DEF\0"
    offset = len(header) + len(palette) + len(block) + len(name) + 4
    frame = struct.pack("<IIIIIIii", 96, 2, 32, 32, 32, 32, 0, 0)
    row_offsets = b"".join(struct.pack("<H", 64 + row) for row in range(32))
    return header + palette + block + name + struct.pack("<I", offset) + frame + row_offsets + bytes([31]) * 32


def simple_object_def():
    palette = bytearray(768)
    palette[8 * 3:8 * 3 + 3] = bytes((200, 30, 20))
    header = struct.pack("<IIII", 67, 64, 32, 1)
    block = struct.pack("<IIII", 0, 1, 0, 0)
    name = b"TREE0000.DEF\0"
    frame_at = len(header) + len(palette) + len(block) + len(name) + 4
    frame = struct.pack("<IIIIIIii", 32 + 128 + 32 * 66, 3, 64, 32, 64, 32, 0, 0)
    encoded = bytearray()
    offsets = []
    for _row in range(32):
        for _chunk in range(2):
            offsets.append(128 + len(encoded))
            encoded.extend(bytes([255]) + bytes([8]) * 32)
    return (header + palette + block + name + struct.pack("<I", frame_at) +
            frame + struct.pack("<64H", *offsets) + encoded)


class FakeArchive:
    entries = {"TREE.DEF": True, "PORTAL.DEF": True, "CAVE.DEF": True}

    def read(self, name):
        if name in self.entries:
            return simple_object_def()
        return simple_overlay_def() if name.endswith(("RVR.DEF", "RD.DEF")) else simple_def((20, 90, 160))


class GameGraphicsTests(unittest.TestCase):
    def test_reads_hota_archive_tiles_and_lzma_object_sprites(self):
        key = 0x18525487
        palette = bytearray(768)
        palette[3:6] = bytes((12, 34, 56))
        tile = struct.pack("<III", 1024, 32, 32) + bytes([1]) * 1024 + palette
        sprite = simple_object_def()
        compressed = lzma.compress(sprite, format=lzma.FORMAT_RAW,
                                   filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 1 << 24,
                                             "lc": 3, "lp": 0, "pb": 2}])
        packed = bytes(1) + compressed
        packed += struct.pack("<qq", len(sprite), len(packed) + 16 + 5)
        start = 92 + 2 * 32

        def entry(name, offset, raw_size, stored_size, kind):
            return (struct.pack("<IIII", LodArchive._name_hash(name), offset ^ key,
                                raw_size ^ key, stored_size ^ key) + bytes([kind]) + bytes(15))

        archive_bytes = (b"LOD\0" + struct.pack("<III", 200, 2, key) + bytes(76) +
                         entry("HGLNT000.PCX", start, len(tile), 0, 0) +
                         entry("AVTCAVE2.DEF", start + len(tile), len(sprite), len(packed), 2) +
                         tile + packed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "HotA.lod"
            path.write_bytes(archive_bytes)
            archive = LodArchive(path)
            self.assertTrue(archive.obfuscated)
            self.assertTrue(archive.has("hglnt000.pcx"))
            self.assertEqual(decode_hota_terrain_tile(archive.read("HGLNT000.PCX")).getpixel((0, 0)),
                             (12, 34, 56))
            self.assertEqual(decode_object_def(archive.read("AVTCAVE2.DEF")).size, (64, 32))

    def test_decodes_terrain_and_hides_covered_tile_pixels(self):
        frame = decode_terrain_def(simple_def((20, 90, 160)))[0]
        self.assertEqual(frame.getpixel((0, 0)), (20, 90, 160))
        renderer = TerrainRenderer(bytes(4 * 7), FakeArchive())
        mask = np.array([[[True, False], [False, False]]])
        image = Image.open(io.BytesIO(renderer.render_png(mask, 0)))
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.getpixel((16, 16)), (20, 90, 160))
        self.assertEqual(image.getpixel((48, 16)), (21, 23, 29))
        self.assertEqual(image.getpixel((16, 48)), (21, 23, 29))

    def test_hota_terrain_uses_its_tiles_and_preserves_fog(self):
        palette = bytearray(768)
        palette[3:6] = bytes((90, 45, 20))
        tile = struct.pack("<III", 1024, 32, 32) + bytes([1]) * 1024 + palette

        class FakeHotaArchive:
            def read(self, name):
                return tile

        terrain = bytes((10, 0, 0, 0, 0, 0, 0,
                         11, 0, 0, 0, 0, 0, 0)) + bytes(2 * 7)
        renderer = TerrainRenderer(terrain, FakeArchive(), hota_archive=FakeHotaArchive())
        mask = np.array([[[True, False], [False, False]]])
        image = Image.open(io.BytesIO(renderer.render_png(mask, 0)))
        self.assertEqual(image.getpixel((16, 16)), (90, 45, 20))
        self.assertEqual(image.getpixel((48, 16)), (21, 23, 29))

    def test_finds_terrain_start_before_shifted_save_tiles(self):
        tiles = [bytes([0, i, 0, 0, 0, 0, 0]) for i in range(8)]
        raw = b"header" + b"".join(tiles) + struct.pack("<II", 5, 9) + b"TEST.DEF\0"
        save_tiles = [tiles[i] for i in range(2, 8)] + [b"later", b"later"]
        self.assertEqual(_candidate_start(raw, save_tiles, 8), (6, 2))

    def test_scenery_sprite_is_clipped_at_fog_boundary(self):
        sprite = decode_object_def(simple_object_def())
        self.assertEqual(sprite.size, (64, 32))
        renderer = TerrainRenderer(bytes(4 * 7), FakeArchive(),
                                   [(1, 0, 0, "TREE.DEF")])
        mask = np.array([[[True, False], [False, False]]])
        image = Image.open(io.BytesIO(renderer.render_png(mask, 0)))
        self.assertEqual(image.getpixel((16, 16)), (200, 30, 20))
        self.assertEqual(image.getpixel((48, 16)), (21, 23, 29))
        self.assertEqual(image.getpixel((16, 48)), (21, 23, 29))

    def test_dashboard_overview_reuses_map_but_masks_each_day(self):
        renderer = TerrainRenderer(bytes(4 * 7), FakeArchive(),
                                   [(1, 0, 0, "TREE.DEF")])
        first = np.array([[[True, False], [False, False]]])
        second = np.array([[[True, True], [False, False]]])

        def decode(mask):
            url = renderer.render_overview_data_url(mask, 0)
            return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))

        image = decode(first)
        self.assertEqual(image.size, (16, 16))
        self.assertEqual(image.getpixel((12, 4)), (21, 23, 29))
        self.assertEqual(decode(second).getpixel((12, 4)), (200, 30, 20))
        self.assertEqual(len(renderer._overview_bases), 1)

    def test_reads_initial_scenery_objects_from_h3m(self):
        template = (struct.pack("<I", 8) + b"TREE.DEF" + bytes(16) +
                    struct.pack("<II", 199, 0) + bytes(18))
        object_record = bytes((1, 0, 0)) + struct.pack("<I", 0) + bytes(5)
        raw = (bytes(4 * 7) + struct.pack("<I", 1) + template +
               struct.pack("<I", 1) + object_record)
        self.assertEqual(parse_map_scenery(raw, 0, 2, 1), [(1, 0, 0, "TREE.DEF")])

    def test_finds_portal_and_gate_after_variable_object_and_renders_sprites(self):
        def template(name, object_class, subclass):
            return (struct.pack("<I", len(name)) + name + bytes(16) +
                    struct.pack("<II", object_class, subclass) + bytes(18))

        raw = (bytes(4 * 7) + struct.pack("<I", 3) +
               template(b"TREE.DEF", 199, 0) +
               template(b"PORTAL.DEF", 45, 17) +
               template(b"CAVE.DEF", 103, 0) +
               struct.pack("<I", 3) +
               bytes((0, 0, 0)) + struct.pack("<I", 0) + bytes(5) +
               bytes((99, 99, 99, 99, 99)) +
               bytes((1, 0, 0)) + struct.pack("<I", 1) + bytes(5) +
               bytes((0, 1, 0)) + struct.pack("<I", 2) + bytes(5))
        transports = parse_map_transports(raw, 0, 2, 1)
        self.assertEqual([(item["x"], item["y"], item["title"]) for item in transports],
                         [(1, 0, "Blue Two-way Monolith"), (0, 1, "Underground Gate")])
        renderer = TerrainRenderer(bytes(4 * 7), FakeArchive(), transports=transports)
        image = Image.open(io.BytesIO(renderer.render_png(np.ones((1, 2, 2), bool), 0)))
        self.assertEqual(image.getpixel((48, 16)), (200, 30, 20))
        self.assertEqual(image.getpixel((16, 48)), (200, 30, 20))

    def test_finds_bonus_sites_after_variable_object(self):
        def template(name, object_class):
            return (struct.pack("<I", len(name)) + name + bytes(16) +
                    struct.pack("<II", object_class, 0) + bytes(18))

        raw = (bytes(4 * 7) + struct.pack("<I", 3) +
               template(b"ARENA.DEF", 4) + template(b"RALLY.DEF", 64) +
               template(b"EVENT.DEF", 26) + struct.pack("<I", 3) +
               bytes((0, 0, 0)) + struct.pack("<I", 2) + bytes(5) +
               bytes((99, 98, 97, 96, 95)) +
               bytes((0, 1, 0)) + struct.pack("<I", 0) + bytes(5) +
               bytes((1, 1, 0)) + struct.pack("<I", 1) + bytes(5))
        bonuses = parse_map_bonuses(raw, 0, 2, 1)
        self.assertEqual([(item["x"], item["y"], item["title"], item["category"])
                          for item in bonuses],
                         [(0, 1, "Arena", "Stat increase"),
                          (1, 1, "Rally Flag", "Morale and luck")])

    def test_primary_stat_scholar_is_pinned_but_spell_scholar_is_not(self):
        template = (struct.pack("<I", 11) + b"SCHOLAR.DEF" + bytes(16) +
                    struct.pack("<II", 81, 0) + bytes(18))
        raw = (bytes(4 * 7) + struct.pack("<I", 1) + template +
               struct.pack("<I", 2) +
               bytes((0, 0, 0)) + struct.pack("<I", 0) + bytes(5) +
               bytes((0, 2)) + bytes(6) +
               bytes((1, 0, 0)) + struct.pack("<I", 0) + bytes(5) +
               bytes((2, 5)) + bytes(6))
        self.assertEqual([(item["title"], item["notes"]) for item in
                          parse_map_bonuses(raw, 0, 2, 1)],
                         [("Scholar (Power)", "Power +1")])

    def test_hota_colosseum_subtype_is_pinned_without_other_class_144_sites(self):
        def template(name, subclass):
            return (struct.pack("<I", len(name)) + name + bytes(16) +
                    struct.pack("<II", 144, subclass) + bytes(18))

        raw = (bytes(4 * 7) + struct.pack("<I", 2) +
               template(b"AVSMGARN.DEF", 2) + template(b"AVWTPLCE.DEF", 3) +
               struct.pack("<I", 2) +
               bytes((0, 0, 0)) + struct.pack("<I", 0) + bytes(5) +
               bytes((1, 0, 0)) + struct.pack("<I", 1) + bytes(5))
        self.assertEqual([(item["x"], item["title"], item["notes"]) for item in
                          parse_map_bonuses(raw, 0, 2, 1)],
                         [(0, "Colosseum of the Magi", "Power or Knowledge +2")])

    def test_finds_dragon_utopia_after_variable_object_body(self):
        def template(name, object_class):
            return (struct.pack("<I", len(name)) + name + bytes(16) +
                    struct.pack("<II", object_class, 0) + bytes(18))

        raw = (bytes(4 * 7) + struct.pack("<I", 2) +
               template(b"EVENT.DEF", 26) + template(b"AVSUTOP0.DEF", 25) +
               struct.pack("<I", 2) +
               bytes((0, 0, 0)) + struct.pack("<I", 0) + bytes(5) +
               bytes((99, 98, 97, 96, 95)) +
               bytes((1, 0, 0)) + struct.pack("<I", 1) + bytes(5) +
               bytes((4, 3, 2, 1)))
        utopias = parse_map_dragon_utopias(raw, 0, 2, 1)
        self.assertEqual([(item["x"], item["y"], item["title"], item["category"])
                          for item in utopias],
                         [(1, 0, "Dragon Utopia", "Dragon Utopia")])


if __name__ == "__main__":
    unittest.main()
