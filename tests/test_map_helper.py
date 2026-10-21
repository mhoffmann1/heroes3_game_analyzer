import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from map_helper import (CATEGORIES, CATEGORY_COLORS, grouped_pin_list, latest_fog, map_figure,
                        read_pins, save_pin, visible_town_pins, visible_towns,
                        visible_bonus_pins, visible_transport_pins, visible_utopia_pins,
                        write_pins)


class MapHelperTests(unittest.TestCase):
    def setUp(self):
        self.players = pd.DataFrame([
            {"day": 1, "player_color": "Red", "fog_of_war": "10000000"},
            {"day": 2, "player_color": "Red", "fog_of_war": "11000000"},
            {"day": 2, "player_color": "Blue", "fog_of_war": "00000001"},
        ])

    def test_latest_mask_is_player_specific_and_has_levels(self):
        day, mask = latest_fog(self.players, "Red", 2, 2)
        self.assertEqual(day, 2)
        self.assertEqual(mask.shape, (2, 2, 2))
        self.assertTrue(mask[0, 0, 1])
        self.assertFalse(mask[1, 1, 1])
        self.assertTrue(latest_fog(self.players, "Blue", 2, 2)[1][1, 1, 1])

    def test_latest_save_wins_when_day_is_shared(self):
        saves = pd.concat([self.players, pd.DataFrame([
            {"day": 2, "player_color": "Red", "fog_of_war": "11100000"}
        ])], ignore_index=True)
        self.assertTrue(latest_fog(saves, "Red", 2, 2)[1][0, 1, 0])

    def test_rejects_pins_on_covered_tiles_and_keeps_players_separate(self):
        red = latest_fog(self.players, "Red", 2, 2)[1]
        blue = latest_fog(self.players, "Blue", 2, 2)[1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map_pins.json"
            with self.assertRaises(ValueError):
                save_pin([], "Red", 1, 1, 1, "Secret", "Other", "", red)
            pins = save_pin([], "Red", 0, 1, 0, "Portal A", "Other", "goes east", red)
            write_pins(path, pins)
            self.assertEqual(read_pins(path), pins)
            self.assertEqual(len(pins), 1)
            self.assertEqual(pins[0]["player"], "Red")
            self.assertNotIn("color", pins[0])
            with self.assertRaises(ValueError):
                save_pin(pins, "Blue", 1, 1, 1, "Changed", "Other", "", blue, pins[0]["id"])
            changed = save_pin(pins, "Red", 0, 1, 0, "Portal B", "Other", "", red, pins[0]["id"])
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0]["title"], "Portal B")

    def test_figure_shows_only_explored_pins(self):
        mask = np.array([[[True, False], [False, False]]])
        pins = [
            {"player": "Red", "level": 0, "x": 0, "y": 0, "title": "Known", "category": "Other", "color": "Red"},
            {"player": "Red", "level": 0, "x": 1, "y": 0, "title": "Hidden", "category": "Other", "color": "Red"},
            {"player": "Blue", "level": 0, "x": 0, "y": 0, "title": "Other player", "category": "Other", "color": "Blue"},
        ]
        figure = map_figure(mask, 2, "Red", 0, pins)
        self.assertEqual(figure.data[0].z.tolist(), [[1, 0], [0, 0]])
        self.assertEqual(list(figure.data[1].x), [0])
        self.assertEqual(list(figure.data[1].text), ["Other: Known"])
        figure.to_json()

    def test_pin_color_follows_category_and_list_is_grouped(self):
        mask = np.array([[[True, True], [True, True]]])
        pins = [
            {"id": "a", "player": "Red", "level": 0, "x": 0, "y": 0,
             "title": "Gold bow", "category": "Artifact", "color": "Red"},
            {"id": "b", "player": "Red", "level": 0, "x": 1, "y": 0,
             "title": "Blue portal", "category": "Portal", "color": "Red"},
        ]
        figure = map_figure(mask, 2, "Red", 0, pins)
        self.assertEqual(list(figure.data[1].marker.color),
                         [CATEGORY_COLORS["Artifact"], CATEGORY_COLORS["Portal"]])
        groups = grouped_pin_list(pins)
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(group.to_plotly_json()["type"] == "Details" and
                            group.open is False for group in groups))
        self.assertIn("Portal", str(groups[0].children[0].children))
        self.assertIn("Artifact", str(groups[1].children[0].children))
        self.assertEqual(groups[0].children[1].children[0].id["pin_id"], "b")
        self.assertEqual(groups[0].children[1].children[0].children,
                         "Blue portal - Surface (1/0)")

    def test_portals_are_grouped_by_color_across_levels(self):
        pins = [
            {"id": "yellow-underground", "category": "Portal", "level": 1,
             "title": "Yellow Two-way Monolith", "x": 4, "y": 5},
            {"id": "blue-surface", "category": "Portal", "level": 0,
             "title": "Blue One-way entrance Portal", "x": 2, "y": 3},
            {"id": "yellow-surface", "category": "Portal", "level": 0,
             "title": "Yellow One-way exit Portal", "x": 6, "y": 7},
            {"id": "blue-underground", "category": "Portal", "level": 1,
             "title": "Blue Two-way Monolith", "x": 8, "y": 9},
        ]
        buttons = grouped_pin_list(pins)[0].children[1].children
        self.assertEqual([button.id["pin_id"] for button in buttons], [
            "blue-surface", "blue-underground", "yellow-surface",
            "yellow-underground",
        ])

    def test_town_is_automatic_only_but_saved_town_pins_remain_accessible(self):
        self.assertNotIn("Town", CATEGORIES)
        mask = np.array([[[True]]])
        with self.assertRaises(ValueError):
            save_pin([], "Red", 0, 0, 0, "Castle", "Town", "", mask)
        legacy = {"id": "old-town", "player": "Red", "level": 0, "x": 0, "y": 0,
                  "title": "Castle", "category": "Town"}
        groups = grouped_pin_list([legacy])
        self.assertEqual(len(groups), 1)
        self.assertIn("Town", str(groups[0].children[0].children))
        self.assertEqual(groups[0].children[1].children[0].id["pin_id"], "old-town")

    def test_auto_marker_types_cannot_be_added_manually(self):
        mask = np.array([[[True]]])
        for category in ("Portal", "Dragon Utopia", "Morale", "Luck", "Morale and luck",
                         "Town", "Underground gate"):
            with self.subTest(category=category):
                self.assertNotIn(category, CATEGORIES)
                with self.assertRaises(ValueError):
                    save_pin([], "Red", 0, 0, 0, category, category, "", mask)

    def test_stat_increase_pin_has_its_own_type_and_color(self):
        self.assertIn("Stat increase", CATEGORIES)
        mask = np.array([[[True]]])
        pins = save_pin([], "Red", 0, 0, 0, "Attack +1", "Stat increase",
                        "Marletto Tower", mask)
        self.assertEqual(pins[0]["category"], "Stat increase")
        self.assertEqual(list(map_figure(mask, 2, "Red", 0, pins).data[1].marker.color),
                         [CATEGORY_COLORS["Stat increase"]])
        self.assertIn("Stat increase", str(grouped_pin_list(pins)[0].children[0].children))

    def test_automatic_transport_pins_follow_player_exploration(self):
        transports = [
            {"level": 0, "x": 0, "y": 0, "title": "Blue Two-way Portal", "category": "Portal"},
            {"level": 0, "x": 1, "y": 0, "title": "Underground Gate", "category": "Underground gate"},
        ]
        mask = np.array([[[True, False]]])
        pins = visible_transport_pins(transports, mask, "Red")
        self.assertEqual(len(pins), 1)
        self.assertEqual(pins[0]["title"], "Blue Two-way Portal")
        self.assertTrue(pins[0]["automatic"])
        self.assertEqual(len(grouped_pin_list(pins)), 1)
        self.assertEqual(list(map_figure(mask, 2, "Red", 0, pins).data[1].x), [0])
        self.assertEqual(visible_transport_pins(transports, np.array([[[False, True]]]), "Blue")[0]["title"],
                         "Underground Gate")

    def test_bonus_pins_follow_player_exploration_on_each_level(self):
        sites = [
            {"level": 0, "x": 0, "y": 0, "title": "Arena", "category": "Stat increase",
             "notes": "Attack or Defense +2"},
            {"level": 0, "x": 1, "y": 0, "title": "Faerie Ring", "category": "Luck"},
            {"level": 1, "x": 1, "y": 0, "title": "Rally Flag", "category": "Morale and luck"},
        ]
        mask = np.array([[[True, False]], [[False, True]]])
        pins = visible_bonus_pins(sites, mask, "Red")
        self.assertEqual([pin["title"] for pin in pins], ["Arena", "Rally Flag"])
        self.assertEqual(pins[0]["notes"], "Attack or Defense +2")
        self.assertTrue(all(pin["automatic"] for pin in pins))
        self.assertEqual(len(grouped_pin_list(pins)), 2)
        self.assertNotIn("Faerie Ring", map_figure(mask, 2, "Red", 0, pins).to_json())
        self.assertEqual([pin["title"] for pin in visible_bonus_pins(sites, ~mask, "Blue")],
                         ["Faerie Ring"])

    def test_dragon_utopia_pins_are_read_only_and_exploration_filtered(self):
        utopias = [
            {"level": 0, "x": 0, "y": 0, "title": "Dragon Utopia",
             "category": "Dragon Utopia", "notes": "Cleared status unknown"},
            {"level": 0, "x": 1, "y": 0, "title": "Dragon Utopia",
             "category": "Dragon Utopia"},
        ]
        mask = np.array([[[True, False]]])
        pins = visible_utopia_pins(utopias, mask, "Red")
        self.assertEqual(len(pins), 1)
        self.assertTrue(pins[0]["automatic"])
        self.assertEqual(pins[0]["notes"], "Cleared status unknown")
        self.assertIn("Dragon Utopia (1)", str(grouped_pin_list(pins)[0].children[0].children))
        self.assertEqual(list(map_figure(mask, 2, "Red", 0, pins).data[1].x), [0])
        self.assertEqual(visible_utopia_pins(utopias, ~mask, "Blue")[0]["x"], 1)

    def test_graphics_background_preserves_clickable_coordinates(self):
        mask = np.array([[[True, False], [False, False]]])
        figure = map_figure(mask, 2, "Red", 0, [], background="data:image/png;base64,AAAA")
        self.assertEqual(figure.layout.images[0].x, -0.5)
        self.assertEqual(figure.layout.images[0].y, -0.5)
        self.assertEqual(figure.layout.images[0].sizex, 2)
        self.assertEqual(figure.data[0].z.tolist(), [[1, 0], [0, 0]])

    def test_initial_view_is_zoomed_toward_explored_tiles(self):
        mask = np.zeros((1, 100, 100), dtype=bool)
        mask[0, 50, 60] = True
        figure = map_figure(mask, 2, "Red", 0, [])
        self.assertEqual(list(figure.layout.xaxis.range), [32.5, 87.5])
        for actual, expected in zip(figure.layout.yaxis.range, [77.5, 22.5]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(figure.layout.xaxis.constrain, "range")
        self.assertEqual(figure.layout.yaxis.scaleanchor, "x")

    def test_visible_towns_include_other_owners_and_hide_covered_cities(self):
        players = pd.DataFrame([
            {"day": 2, "player_color": "Red", "fog_of_war": "1100", "town_summary": []},
            {"day": 2, "player_color": "Blue", "fog_of_war": "0001", "town_summary": [
                {"town_name": "Old name", "coords": [1, 0, "Surface"]}]},
            {"day": 2, "player_color": "None", "fog_of_war": "", "town_summary": [
                {"town_name": "Neutral Keep", "coords": [0, 0, "Surface"]}]},
            {"day": 2, "player_color": "Blue", "fog_of_war": "0001", "town_summary": [
                {"town_name": "Visible Keep", "coords": [1, 0, "Surface"]},
                {"town_name": "Hidden Keep", "coords": [1, 1, "Surface"]}]},
        ])
        towns = visible_towns(players, "Red", 2, 1)
        self.assertEqual({town["name"] for town in towns}, {"Visible Keep", "Neutral Keep"})
        town_pins = visible_town_pins(towns, "Red")
        self.assertEqual({pin["title"] for pin in town_pins}, {"Visible Keep", "Neutral Keep"})
        self.assertTrue(all(pin["automatic"] and pin["category"] == "Town" for pin in town_pins))
        self.assertIn("Town (2)", str(grouped_pin_list(town_pins)[0].children[0].children))
        mask = latest_fog(players, "Red", 2, 1)[1]
        figure = map_figure(mask, 2, "Red", 0, town_pins, towns=towns)
        self.assertEqual({annotation.text for annotation in figure.layout.annotations},
                         {"Visible Keep", "Neutral Keep"})
        self.assertEqual({(trace.x[0], trace.y[0]) for trace in figure.data[1:]},
                         {(1, 0), (0, 0)})
        self.assertNotIn("Hidden Keep", figure.to_json())


if __name__ == "__main__":
    unittest.main()
