import unittest
from types import SimpleNamespace

from h3tools.lib.utopias import Utopia
from read_save import extract_game_data


UNVISITED_UTOPIA = bytes.fromhex(
    "061e00000000c2101900000094351fe03afc020000009435010195351202"
)
HERO_ON_UTOPIA = bytes.fromhex(
    "061e00000000c2102200000094358e0000000100000094350101"
)


def make_save(tile):
    return SimpleNamespace(
        heroes=[],
        towns=[],
        player_resources=[],
        mapdata={"size": 1, "levels": 1},
        maptiles=[(1234, tile, len(tile))],
    )


class UtopiaOccupancyTests(unittest.TestCase):
    def test_recognizes_hero_object_type(self):
        self.assertTrue(Utopia.is_hero(HERO_ON_UTOPIA))
        self.assertFalse(Utopia.is_hero(UNVISITED_UTOPIA))

    def test_hero_occupancy_defers_update_and_preserves_state(self):
        tracked = [Utopia(0, UNVISITED_UTOPIA, 1)]

        with self.assertLogs("h3_analyzer", level="INFO") as captured:
            _, tracker = extract_game_data(make_save(HERO_ON_UTOPIA), {}, {}, tracked)

        self.assertFalse(tracked[0].conquered)
        self.assertEqual("00000000", tracked[0].visited_bitmask)
        self.assertEqual(0, sum(tracker.as_dict().values()))
        self.assertIn("a hero currently occupies its map tile", "\n".join(captured.output))

    def test_unexpected_object_still_warns(self):
        tracked = [Utopia(0, UNVISITED_UTOPIA, 1)]
        unexpected = bytearray(HERO_ON_UTOPIA)
        unexpected[Utopia.OBJECT_TYPE_OFFSET] = 0x07

        with self.assertLogs("h3_analyzer", level="WARNING") as captured:
            extract_game_data(make_save(bytes(unexpected)), {}, {}, tracked)

        self.assertIn("unexpectedly points to object type 0x07", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
