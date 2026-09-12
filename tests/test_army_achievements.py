import unittest

import pandas as pd

from dashboard import (
    build_achievement_awards,
    create_hero_entry,
    get_hero_army_achievement_metrics,
)
from read_save import add_army_unit_levels, calculate_army_levels


def hero(day, player, name, army):
    return create_hero_entry(name, {"army": army}, player, day)


class ArmyAchievementMetricTests(unittest.TestCase):
    def test_army_level_calculation_keeps_upgraded_unit_counts(self):
        army = [
            {"name": "Angel", "count": 2},
            {"name": "Archangel", "count": 5},
        ]
        unit_stats = {"units": [
            {"Name": "Angel", "Level": 7},
            {"Name": "Archangel", "Level": "7+"},
        ]}

        self.assertEqual(
            {"7": 2, "7+": 5},
            dict(calculate_army_levels(army, unit_stats)),
        )

    def test_enriches_exported_stacks_with_unit_level(self):
        army = [{"name": "Angel", "count": 3}]
        unit_stats = {"units": [{"Name": "Angel", "Level": 7}]}

        self.assertEqual(
            [{"name": "Angel", "count": 3, "level": 7}],
            add_army_unit_levels(army, unit_stats),
        )

    def test_calculates_metrics_for_one_hero_and_normalizes_upgrades(self):
        metrics = get_hero_army_achievement_metrics({"army": [
            {"name": "Angel", "count": 100, "level": 7},
            {"name": "Archangel", "count": 100, "level": "7+"},
            {"name": "Titan", "count": 100, "level": 7},
        ]})

        self.assertEqual(1, metrics["has_tier_seven"])
        self.assertEqual(100, metrics["largest_tier_seven_stack"])
        self.assertEqual(300, metrics["tier_six_army_total"])
        self.assertEqual(1, metrics["mythical_host"])

    def test_requires_three_distinct_types_for_mythical_host(self):
        metrics = get_hero_army_achievement_metrics({"army": [
            {"name": "Titan", "count": 200, "level": 7},
            {"name": "Black Dragon", "count": 200, "level": "7+"},
        ]})

        self.assertEqual(0, metrics["mythical_host"])

    def test_awards_only_hero_army_achievements(self):
        players = pd.DataFrame([
            {"day": day, "player_color": player}
            for day, player in [
                (1, "Red"), (2, "Red"), (2, "Blue"),
                (3, "Tan"), (4, "Green"), (5, "Orange"),
            ]
        ])
        heroes = pd.DataFrame([
            hero(1, "Red", "Scout", [
                {"name": "Angel", "count": 1, "level": 7},
            ]),
            hero(2, "Red", "Horde", [
                {"name": "Gremlin", "count": 500, "level": 1},
            ]),
            hero(2, "Blue", "Myth", [
                {"name": "Angel", "count": 100, "level": 7},
                {"name": "Archangel", "count": 100, "level": "7+"},
                {"name": "Titan", "count": 100, "level": 7},
            ]),
            hero(3, "Tan", "Thousand", [
                {"name": "Skeleton", "count": 1_000, "level": 1},
            ]),
            hero(4, "Green", "Battle Line", [
                {"name": f"Tier {tier}", "count": 1, "level": tier}
                for tier in range(1, 8)
            ]),
            hero(5, "Orange", "Elites", [
                {"name": f"Elite {slot}", "count": 1, "level": "6+"}
                for slot in range(7)
            ]),
        ])

        awards = build_achievement_awards(players, heroes)
        by_key = {}
        for award in awards:
            by_key.setdefault(award["key"], []).append(award)

        self.assertEqual("Red", by_key["Elite Vanguard"][0]["player"])
        self.assertEqual("Red", by_key["The Horde"][0]["player"])
        self.assertEqual("Blue", by_key["Elite Legion"][0]["player"])
        self.assertEqual("Blue", by_key["Seventh Heaven"][0]["player"])
        self.assertEqual("Blue", by_key["Mythical Host"][0]["player"])
        self.assertEqual("Tan", by_key["A Thousand Strong"][0]["player"])
        self.assertEqual("Blue", by_key["Army of Giants"][0]["player"])
        self.assertEqual("Green", by_key["Full Battle Line"][0]["player"])
        self.assertEqual("Orange", by_key["No Weaklings Allowed"][0]["player"])


if __name__ == "__main__":
    unittest.main()
