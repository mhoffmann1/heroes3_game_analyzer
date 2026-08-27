import unittest

import pandas as pd

from dashboard import (
    build_player_power_scores,
    build_player_summary_rankings,
    get_top_heroes_by_army_strength,
)


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

        strongest_per_player = get_top_heroes_by_army_strength(
            heroes, ["Red", "Blue"], limit=1
        )
        self.assertEqual(["Crag", "Solmyr"], strongest_per_player)

    def test_returns_empty_selection_without_players(self):
        heroes = pd.DataFrame(columns=[
            "day", "player_color", "hero_name", "army_strength"
        ])

        self.assertEqual([], get_top_heroes_by_army_strength(heroes, []))


class PlayerSummaryRankingsTests(unittest.TestCase):
    def test_builds_requested_totals_and_orders_players(self):
        players = pd.DataFrame([
            {
                "day": 4, "player_color": "Red", "town_count": 2,
                "wood": 10, "ore": 15, "gems": 1, "crystal": 2,
                "sulfur": 3, "mercury": 4, "gold": 5000,
                "visited_utopias": 1, "total_army_strength": 900,
                "tiles_explored": 120,
            },
            {
                "day": 4, "player_color": "Blue", "town_count": 3,
                "wood": 20, "ore": 20, "gems": 2, "crystal": 3,
                "sulfur": 4, "mercury": 5, "gold": 4000,
                "visited_utopias": 2, "total_army_strength": 800,
                "tiles_explored": 150,
            },
            {
                "day": 4, "player_color": "None", "town_count": 10,
                "gold": 99999,
            },
        ])
        heroes = pd.DataFrame([
            {
                "day": 3, "player_color": "Red", "hero_name": "Gelu",
                "has_dd": True, "has_tp": False, "has_fly": True,
            },
            {
                "day": 4, "player_color": "Red", "hero_name": "Gelu",
                "has_dd": False, "has_tp": False, "has_fly": False,
            },
            {
                "day": 4, "player_color": "Red", "hero_name": "Kyrre",
                "has_dd": False, "has_tp": True, "has_fly": False,
            },
            {
                "day": 4, "player_color": "Blue", "hero_name": "Solmyr",
                "has_dd": False, "has_tp": False, "has_fly": False,
            },
            {"day": 4, "player_color": "None", "hero_name": "Neutral"},
        ])

        rankings = build_player_summary_rankings(players, heroes, 4)
        by_key = {ranking["key"]: ranking for ranking in rankings}

        self.assertEqual(
            ["Blue", "Red"],
            [entry["player"] for entry in by_key["town_count"]["entries"]],
        )
        self.assertEqual(
            [40, 25],
            [entry["value"] for entry in by_key["wood_and_ore"]["entries"]],
        )
        self.assertEqual(
            [14, 10],
            [entry["value"] for entry in by_key["rare_resources"]["entries"]],
        )
        self.assertEqual(
            [2, 1],
            [entry["value"] for entry in by_key["heroes_controlled"]["entries"]],
        )
        self.assertEqual(
            [("Gelu", 0), ("Solmyr", 0)],
            [
                (entry["hero"], entry["value"])
                for entry in by_key["strongest_hero_strength"]["entries"]
            ],
        )
        self.assertEqual(
            [
                ("Red", 3, ["Dimension Door", "Town Portal", "Fly"]),
                ("Blue", 0, []),
            ],
            [
                (entry["player"], entry["value"], entry["spells"])
                for entry in by_key["adventure_spells"]["entries"]
            ],
        )

        scores = build_player_power_scores(rankings)
        scores_by_player = {score["player"]: score for score in scores}
        self.assertGreater(
            scores_by_player["Red"]["Map control"],
            scores_by_player["Blue"]["Map control"],
        )
        self.assertEqual(
            scores_by_player["Red"]["total"],
            scores_by_player["Red"]["Military"]
            + scores_by_player["Red"]["Map control"]
            + scores_by_player["Red"]["Economic"],
        )
        self.assertGreaterEqual(scores_by_player["Red"]["Map control"], 15)

    def test_tied_values_receive_equal_points(self):
        rankings = [{
            "key": "gold",
            "label": "Gold",
            "group": "Economic",
            "entries": [
                {"player": "Red", "value": 100},
                {"player": "Blue", "value": 100},
                {"player": "Tan", "value": 50},
            ],
        }]

        scores = {
            score["player"]: score for score in build_player_power_scores(rankings)
        }
        self.assertEqual(3, scores["Red"]["Economic"])
        self.assertEqual(3, scores["Blue"]["Economic"])
        self.assertEqual(1, scores["Tan"]["Economic"])


if __name__ == "__main__":
    unittest.main()
