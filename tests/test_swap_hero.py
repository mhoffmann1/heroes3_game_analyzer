import unittest
from types import SimpleNamespace

from swap_hero import (
    HeroSpan,
    ACTIVE_HERO_TABLE_SUFFIX,
    _find_source_hero_object_id,
    _place_hero_map_object,
    _register_active_hero,
)


def empty_tile():
    return bytes.fromhex("0a6a0000000040000000ffffffff0000000000000000")


class SwapHeroMapObjectTests(unittest.TestCase):
    def test_finds_hero_object_on_neighbouring_anchor_tile(self):
        raw = bytearray(80)
        span = HeroSpan("Sylvia", 0, 80)
        raw[5:7] = (2).to_bytes(2, "big")
        raw[7:9] = (2).to_bytes(2, "big")
        raw[9:11] = (0).to_bytes(2, "big")

        tiles = [(0, empty_tile(), 22) for _ in range(16)]
        hero_tile = bytearray(empty_tile())
        hero_tile[7] |= 0x10
        hero_tile[8] = 0x22
        hero_tile[14:18] = (3).to_bytes(4, "little")
        tiles[1 * 4 + 1] = (0, bytes(hero_tile), 22)
        save = SimpleNamespace(
            raw=raw,
            mapdata={"size": 4, "levels": 1},
            maptiles=tiles,
        )

        self.assertEqual(3, _find_source_hero_object_id(save, span))

    def test_places_hero_on_empty_fixed_size_tile(self):
        tile = empty_tile()
        raw = bytearray(tile)
        save = SimpleNamespace(
            mapdata={"size": 1, "levels": 1},
            maptiles=[(0, tile, len(tile))],
        )

        tile_index, tile_offset = _place_hero_map_object(
            save, raw, "Gelu", 148, 0, 0, 0
        )

        self.assertEqual((0, 0), (tile_index, tile_offset))
        self.assertEqual(0x22, raw[8])
        self.assertEqual(148, int.from_bytes(raw[14:18], "little"))

    def test_refuses_to_overwrite_existing_object(self):
        tile = bytearray(empty_tile())
        tile[8] = 0x19
        save = SimpleNamespace(
            mapdata={"size": 1, "levels": 1},
            maptiles=[(0, bytes(tile), len(tile))],
        )

        with self.assertRaisesRegex(ValueError, "already contains object type"):
            _place_hero_map_object(save, bytearray(tile), "Gelu", 148, 0, 0, 0)

    def test_registers_confirmed_hota_active_hero_record(self):
        prefix = bytes(22)
        table_offset = len(prefix)
        raw = bytearray(prefix + (0).to_bytes(4, "little") + ACTIVE_HERO_TABLE_SUFFIX)

        found_table, inserted_at = _register_active_hero(
            raw, hero_object_id=0x2E, owner_byte=1, x=11, y=5, z=0
        )

        self.assertEqual(table_offset, found_table)
        self.assertEqual(1, int.from_bytes(raw[table_offset:table_offset + 4], "little"))
        self.assertEqual(
            bytes.fromhex("09012e00000001ff0b000500ff03ff3f00000000"),
            raw[inserted_at:inserted_at + 20],
        )

    def test_registers_second_hero_after_zero_terminated_record(self):
        table_offset = 22
        first_record = bytes.fromhex(
            "09009400000000ff0a000a00ff03ff3f00000000"
        )
        raw = bytearray(
            bytes(table_offset)
            + (1).to_bytes(4, "little")
            + first_record
            + ACTIVE_HERO_TABLE_SUFFIX
        )

        found_table, inserted_at = _register_active_hero(
            raw, hero_object_id=0x2D, owner_byte=1, x=11, y=10, z=0
        )

        self.assertEqual(table_offset, found_table)
        self.assertEqual(2, int.from_bytes(raw[table_offset:table_offset + 4], "little"))
        self.assertEqual(table_offset + 24, inserted_at)
        self.assertEqual(
            bytes.fromhex("09012d00000001ff0b000a00ff03ff3f00000000"),
            raw[inserted_at:inserted_at + 20],
        )

    def test_accepts_map_specific_active_table_marker_values(self):
        suffix = bytearray(ACTIVE_HERO_TABLE_SUFFIX)
        suffix[16] = 7
        suffix[21] = 8
        table_offset = 22
        raw = bytearray(bytes(table_offset) + bytes(4) + suffix)

        found_table, inserted_at = _register_active_hero(
            raw, hero_object_id=0x94, owner_byte=0, x=10, y=10, z=0
        )

        self.assertEqual(table_offset, found_table)
        self.assertEqual(table_offset + 4, inserted_at)
        self.assertEqual(1, int.from_bytes(raw[table_offset:table_offset + 4], "little"))


if __name__ == "__main__":
    unittest.main()
