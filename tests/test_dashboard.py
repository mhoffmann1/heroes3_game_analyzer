import unittest

import pandas as pd

from dashboard import get_top_heroes_by_army_strength


class HeroMetricDefaultsTests(unittest.TestCase):
    def test_selects_three_strongest_heroes_per_player_on_latest_day(self):
        heroes = pd.DataFrame([
            {"day": 1, "player_color": "Red", "hero_name": "OldStar", "army_strength": 999},
            {"day": 2, "player_color": "Red", "hero_name": "OldStar", "army_strength": 5},
            {"day": 2, "player_color": "Red", "hero_name": "Crag", "army_strength": 400},
            {"day": 2, "player_color": "Red", "hero_name": "Gelu", "army_strength": 300},
            {"day": 2, "player_color": "Red", "hero_name": "Kyrre", "army_strength": 200},
            {"day": 2, "player_color": "Red", "hero_name": "Rashka", "army_strength": 100},
            {"day": 2, "player_color": "Blue", "hero_name": "Solmyr", "army_strength": 600},
            {"day": 2, "player_color": "Blue", "hero_name": "Cyra", "army_strength": 500},
            {"day": 2, "player_color": "None", "hero_name": "Neutral", "army_strength": 1000},
        ])

        selected = get_top_heroes_by_army_strength(
            heroes, ["Red", "Blue"], limit=3
        )

        self.assertEqual(
            ["Crag", "Gelu", "Kyrre", "Solmyr", "Cyra"],
            selected,
        )
        self.assertNotIn("OldStar", selected)
        self.assertNotIn("Neutral", selected)

    def test_returns_empty_selection_without_players(self):
        heroes = pd.DataFrame(columns=[
            "day", "player_color", "hero_name", "army_strength"
        ])

        self.assertEqual([], get_top_heroes_by_army_strength(heroes, []))


if __name__ == "__main__":
    unittest.main()
