import unittest

from hero_visits import visited_object_sites
from map_helper import resolved_hero_visits


class HeroVisitsTests(unittest.TestCase):
    def test_masks_are_per_hero_and_use_full_map_order(self):
        objects = [
            {"title": "Arena", "level": 1, "x": 4, "y": 3},
            {"title": "Arena", "level": 0, "x": 9, "y": 7},
            {"title": "Arena", "level": 0, "x": 2, "y": 7},
            {"title": "Marletto Tower", "level": 0, "x": 1, "y": 1},
            {"title": "Colosseum of the Magi", "level": 0, "x": 5, "y": 5},
        ]
        first = bytearray(62)
        second = bytearray(62)
        first[50:54] = (0b101).to_bytes(4, "little")
        first[26:30] = (1).to_bytes(4, "little")
        second[50:54] = (0b010).to_bytes(4, "little")
        self.assertEqual(visited_object_sites(first, objects),
                         {"0:2:7", "1:4:3", "0:1:1"})
        self.assertEqual(visited_object_sites(second, objects), {"0:9:7"})

    def test_manual_marks_only_extend_untracked_types(self):
        pins = [
            {"title": "Arena", "level": 0, "x": 1, "y": 1},
            {"title": "Colosseum of the Magi", "level": 0, "x": 2, "y": 2},
            {"title": "Scholar (Attack)", "level": 0, "x": 3, "y": 3},
        ]
        marks = [{"player": "Blue", "hero": "Solmyr", "site": site}
                 for site in ("0:1:1", "0:2:2", "0:3:3")]
        self.assertEqual(resolved_hero_visits(marks, "Blue", "Solmyr", pins, set()),
                         {"0:2:2", "0:3:3"})
        self.assertEqual(resolved_hero_visits(marks, "Blue", "Solmyr", pins,
                                              {"0:1:1"}),
                         {"0:1:1", "0:2:2", "0:3:3"})
        self.assertEqual(resolved_hero_visits(marks, "Blue", "Other", pins, set()), set())


if __name__ == "__main__":
    unittest.main()
