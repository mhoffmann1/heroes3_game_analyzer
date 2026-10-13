import unittest

import pandas as pd

from dashboard import (
    build_achievement_awards,
    create_hero_entry,
    get_hero_artifact_achievement_metrics,
)
from read_save import extract_hero_artifacts


class ArtifactExtractionTests(unittest.TestCase):
    def test_exports_equipment_slots_and_compact_backpack(self):
        hero = type("Hero", (), {})()
        hero.version = "hota"
        hero.equipment = {
            "helm": "Crown of Dragontooth",
            "weapon": None,
            "side1": "Orb of Vulnerability",
        }
        hero.inventory = [None, "Angel Wings", None, "Golden Bow"]

        self.assertEqual(
            {
                "equipped": {
                    "helm": "Crown of Dragontooth",
                    "side1": "Orb of Vulnerability",
                },
                "backpack": ["Angel Wings", "Golden Bow"],
                "combined": [],
            },
            extract_hero_artifacts(hero),
        )

    def test_exports_combination_artifact_occupied_slots(self):
        hero = type("Hero", (), {})()
        hero.version = "hota"
        hero.equipment = {"weapon": "Ironfist of the Ogre"}
        hero.inventory = []

        artifacts = extract_hero_artifacts(hero)

        self.assertEqual(
            [{
                "name": "Ironfist of the Ogre",
                "primary_slot": "weapon",
                "occupied_slots": ["weapon", "helm", "armor", "shield"],
            }],
            artifacts["combined"],
        )

    def test_dashboard_preserves_artifacts_and_supports_older_json(self):
        artifacts = {
            "equipped": {"feet": "Boots of Speed"},
            "backpack": ["Tome of Air Magic"],
            "combined": [],
        }
        current = create_hero_entry("Solmyr", {"artifacts": artifacts}, "Blue", 7)
        legacy = create_hero_entry("Solmyr", {}, "Blue", 6)

        self.assertEqual(artifacts["equipped"], current["equipped_artifacts"])
        self.assertEqual(artifacts["backpack"], current["backpack_artifacts"])
        self.assertEqual([], current["combined_artifacts"])
        self.assertEqual({}, legacy["equipped_artifacts"])
        self.assertEqual([], legacy["backpack_artifacts"])
        self.assertEqual([], legacy["combined_artifacts"])

    def test_combination_reservations_and_scrolls_count_for_hero_metrics(self):
        artifacts = {
            "equipped": {
                "weapon": "Ironfist of the Ogre",
                "cloak": "Cape of Velocity",
                "feet": "Boots of Speed",
                "lefthand": "Ring One",
                "righthand": "Ring Two",
                "neck": "Necklace of Swiftness",
                "side1": "Bow of the Sharpshooter",
                "side4": "Orb of Vulnerability",
                "side5": "The Grail",
            },
            "backpack": [f"Spell Scroll: Spell {index}" for index in range(5)],
            "combined": [
                {
                    "name": "Ironfist of the Ogre",
                    "primary_slot": "weapon",
                    "occupied_slots": ["weapon", "helm", "armor", "shield"],
                },
                {
                    "name": "Bow of the Sharpshooter",
                    "primary_slot": "side1",
                    "occupied_slots": ["side", "side", "side"],
                },
            ],
        }

        metrics = get_hero_artifact_achievement_metrics({"artifacts": artifacts})

        self.assertEqual(14, metrics["effective_equipment_slots"])
        self.assertEqual(1, metrics["full_equipment"])
        self.assertEqual(2, metrics["combined_artifact_count"])
        self.assertEqual(5, metrics["distinct_scroll_count"])

    def test_awards_recommended_artifact_achievements(self):
        equipment = {
            "weapon": "Ironfist of the Ogre",
            "cloak": "Cape of Velocity",
            "feet": "Boots of Speed",
            "lefthand": "Ring One",
            "righthand": "Ring Two",
            "neck": "Necklace of Swiftness",
            "side1": "Bow of the Sharpshooter",
            "side4": "Orb of Vulnerability",
            "side5": "The Grail",
        }
        combined = [
            {
                "name": "Ironfist of the Ogre",
                "primary_slot": "weapon",
                "occupied_slots": ["weapon", "helm", "armor", "shield"],
            },
            {
                "name": "Bow of the Sharpshooter",
                "primary_slot": "side1",
                "occupied_slots": ["side", "side", "side"],
            },
        ]
        scrolls = [f"Spell Scroll: Spell {index}" for index in range(20)]
        tomes = ["Tome of Air", "Tome of Earth", "Tome of Fire", "Tome of Water"]
        collection = tomes + [f"Collected Artifact {index}" for index in range(17)]
        heroes = pd.DataFrame([
            create_hero_entry("Collector", {"artifacts": {
                "equipped": equipment,
                "backpack": scrolls,
                "combined": combined,
            }}, "Red", 1),
            create_hero_entry("Curator", {"artifacts": {
                "equipped": {},
                "backpack": collection,
                "combined": [],
            }}, "Red", 1),
        ])
        players = pd.DataFrame([{"day": 1, "player_color": "Red"}])

        awards = {
            award["key"]: award
            for award in build_achievement_awards(players, heroes)
        }

        expected = {
            "Fully Equipped", "Pack Rat", "Treasure Hoard", "Matching Set",
            "Greater Than the Sum", "Curator", "Elemental Scholar",
            "Scroll Keeper", "Arcane Library",
        }
        self.assertTrue(expected.issubset(awards))
        self.assertTrue(all(awards[name]["player"] == "Red" for name in expected))


if __name__ == "__main__":
    unittest.main()
