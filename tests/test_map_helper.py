import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from map_helper import (CATEGORIES, CATEGORY_COLORS, active_creature_favourites,
                        clicked_stat_pin, favourite_creature_pins, favourite_gold_summary,
                        grouped_pin_list,
                        hero_map_position, latest_fog, map_figure, stat_area_interests,
                        normalized_hidden_categories, optional_favourite_number,
                        read_creature_favourites, read_pins, save_pin,
                        visible_town_pins, visible_towns,
                        visible_bonus_pins, visible_obelisk_pins,
                        visible_transport_pins, visible_utopia_pins,
                        visible_creature_pins, read_stat_visits, stat_site_key,
                        stat_site_progress, visited_stat_sites, write_pins, write_stat_visits)


class MapHelperTests(unittest.TestCase):
    def test_discovered_obelisks_show_current_players_visit_status(self):
        mask = np.array([[[True, True, False]]])
        obelisks = [{"level": 0, "x": x, "y": 0, "obelisk_index": x}
                    for x in range(3)]
        data = {"total": 3, "table_offset": 100,
                "objects": [{"index": 0, "visited_by": ["Red"]},
                            {"index": 1, "visited_by": ["Blue"]},
                            {"index": 2, "visited_by": []}]}
        pins = visible_obelisk_pins(obelisks, mask, "Blue", data)
        self.assertEqual([pin["visit_status"] for pin in pins], ["Unvisited", "Visited"])
        self.assertEqual(len(pins), 2)
        self.assertEqual([pin["visit_status"] for pin in
                          visible_obelisk_pins(obelisks, mask, "Red", data)],
                         ["Visited", "Unvisited"])
        figure = map_figure(mask, 2, "Blue", 0, pins)
        self.assertEqual(list(figure.data[1].marker.symbol), ["diamond", "circle-open"])
        self.assertIn("Visited by Blue", figure.data[1].text[1])

        data["table_offset"] = None
        self.assertEqual([pin["visit_status"] for pin in
                          visible_obelisk_pins(obelisks, mask, "Blue", data)],
                         ["Unknown", "Visited"])
        self.assertEqual([pin["visit_status"] for pin in
                          visible_obelisk_pins(obelisks, mask, "Blue")],
                         ["Unknown", "Unknown"])

    def test_stat_clusters_use_site_values_and_keep_distant_outliers_separate(self):
        mask = np.ones((2, 60, 60), dtype=bool)
        pins = visible_bonus_pins([
            {"level": 0, "x": 2, "y": 2, "title": "Library of Enlightenment",
             "category": "Stat increase"},
            {"level": 0, "x": 12, "y": 2, "title": "Arena", "category": "Stat increase"},
            {"level": 0, "x": 15, "y": 5, "title": "Mercenary Camp",
             "category": "Stat increase"},
            {"level": 0, "x": 55, "y": 55, "title": "Marletto Tower",
             "category": "Stat increase"},
            {"level": 1, "x": 3, "y": 3, "title": "Colosseum of the Magi",
             "category": "Stat increase"},
        ], mask, "Blue")
        areas = stat_area_interests(pins, set(), (0, 0, 0), 60)
        self.assertEqual(sorted(len(area["sites"]) for area in areas), [1, 1, 3])
        cluster = next(area for area in areas if len(area["sites"]) == 3)
        self.assertEqual(cluster["value"], 6)
        self.assertEqual(cluster["stat_gain"],
                         {"Attack": 5, "Defense": 4, "Power": 2, "Knowledge": 2})
        self.assertEqual(cluster["unknown_stat_sites"], 0)
        self.assertEqual((cluster["min_x"], cluster["min_y"],
                          cluster["max_x"], cluster["max_y"]), (2, 2, 15, 5))
        self.assertEqual(next(area["value"] for area in areas if area["level"] == 1), 2)
        self.assertEqual(next(area["stat_gain"] for area in areas if area["level"] == 1),
                         {"Attack": 0, "Defense": 0, "Power": 2, "Knowledge": 2})

    def test_stat_areas_rank_known_unvisited_clusters_from_hero_position(self):
        mask = np.ones((2, 40, 40), dtype=bool)
        mask[0, 20, 20] = False
        pins = visible_bonus_pins([
            {"level": 0, "x": 3, "y": 2, "title": "Mercenary Camp", "category": "Stat increase"},
            {"level": 0, "x": 5, "y": 3, "title": "Marletto Tower", "category": "Stat increase"},
            {"level": 0, "x": 30, "y": 30, "title": "Arena", "category": "Stat increase"},
            {"level": 0, "x": 20, "y": 20, "title": "Library of Enlightenment", "category": "Stat increase"},
            {"level": 1, "x": 2, "y": 2, "title": "Star Axis", "category": "Stat increase"},
        ], mask, "Blue")
        position = hero_map_position({"coords": {"x": 2, "y": 2, "z": 0}}, 40, 2)
        self.assertEqual(position, (0, 2, 2))
        areas = stat_area_interests(pins, {"0:30:30"}, position)
        self.assertEqual([len(area["sites"]) for area in areas], [2, 1])
        self.assertEqual(areas[0]["value"], 2)
        self.assertEqual(areas[0]["priority"], 1)
        self.assertEqual(areas[0]["nearest"]["x"], 3)
        self.assertEqual(areas[1]["level"], 1)
        self.assertGreaterEqual(areas[1]["distance"], 40)
        self.assertIsNone(hero_map_position({"coords": {"x": 99, "y": 2, "z": 0}}, 40, 2))

    def test_stat_area_overlay_is_optional_and_marks_hero_and_priority(self):
        mask = np.ones((1, 10, 10), dtype=bool)
        pins = visible_bonus_pins([
            {"level": 0, "x": 4, "y": 4, "title": "Arena", "category": "Stat increase"},
        ], mask, "Blue")
        areas = stat_area_interests(pins, set(), (0, 1, 1))
        plain = map_figure(mask, 3, "Blue", 0, pins)
        marked = map_figure(mask, 3, "Blue", 0, pins,
                            background="data:image/png;base64,AAAA",
                            stat_areas=areas, hero_position=(0, 1, 1))
        self.assertEqual(len(plain.layout.shapes), 0)
        self.assertEqual(marked.data[1].name, "Stat area #1")
        self.assertEqual(marked.data[1].fill, "toself")
        self.assertEqual(list(marked.data[1].x), [2, 6, 6, 2, 2])
        self.assertEqual(list(marked.data[1].y), [2, 2, 6, 6, 2])
        self.assertIn("#1", [item.text.split(" · ")[0] for item in marked.layout.annotations])
        self.assertIn("A+2 D+2 P+0 K+0", marked.layout.annotations[0].text)
        self.assertEqual(marked.data[-1].name, "Selected hero")

        focused = map_figure(mask, 3, "Blue", 0, pins,
                             selected={**pins[0], "focus": True,
                                       "focus_bounds": [2, 2, 6, 6]},
                             stat_areas=areas)
        self.assertLess(focused.layout.xaxis.range[0], 2)
        self.assertGreater(focused.layout.xaxis.range[1], 6)
        self.assertGreater(focused.layout.yaxis.range[0], 6)
        self.assertLess(focused.layout.yaxis.range[1], 2)

    def test_clicked_stat_site_accepts_marker_or_terrain_tile(self):
        pins = [{"id": "stat", "level": 0, "x": 2, "y": 3, "automatic": True,
                 "category": "Stat increase"},
                {"id": "other", "level": 0, "x": 2, "y": 3, "automatic": True,
                 "category": "Portal"}]
        self.assertEqual(clicked_stat_pin({"customdata": "stat", "curveNumber": 1}, pins, 0), pins[0])
        self.assertEqual(clicked_stat_pin({"x": 2, "y": 3, "curveNumber": 0}, pins, 0), pins[0])
        self.assertIsNone(clicked_stat_pin({"customdata": "other", "x": 2, "y": 3,
                                            "curveNumber": 1}, pins, 0))
        self.assertIsNone(clicked_stat_pin({"x": 2, "y": 3, "curveNumber": 0}, pins, 1))

    def test_stat_progress_counts_discovered_sites_and_choice_ceiling(self):
        hero = {"primary_skills": {"attack": 4, "defense": 3,
                                   "spell_power": 2, "knowledge": 1}}
        mask = np.array([[[True, True, False]]])
        sites = visible_bonus_pins([
            {"level": 0, "x": 0, "y": 0, "title": "Arena", "category": "Stat increase"},
            {"level": 0, "x": 1, "y": 0, "title": "Marletto Tower", "category": "Stat increase"},
            {"level": 0, "x": 2, "y": 0, "title": "Star Axis", "category": "Stat increase"},
        ], mask, "Blue")
        current, maximum, types = stat_site_progress(hero, sites, {"0:1:0"})
        self.assertEqual(current, {"Attack": 4, "Defense": 3, "Power": 2, "Knowledge": 1})
        self.assertEqual(maximum, {"Attack": 6, "Defense": 5, "Power": 2, "Knowledge": 1})
        self.assertEqual(types["Arena"], {"visited": 0, "total": 1})
        self.assertEqual(types["Marletto Tower"], {"visited": 1, "total": 1})
        self.assertNotIn("Star Axis", types)
        self.assertEqual(stat_site_progress(hero, sites, {"0:0:0", "0:1:0"})[1], current)

    def test_stat_visits_are_per_hero_and_can_be_hidden(self):
        mask = np.ones((1, 2, 2), dtype=bool)
        pins = visible_bonus_pins([
            {"level": 0, "x": 0, "y": 0, "title": "Arena", "category": "Stat increase"},
            {"level": 0, "x": 1, "y": 0, "title": "Marletto Tower", "category": "Stat increase"},
        ], mask, "Blue")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map_stat_visits.json"
            write_stat_visits(path, [{"player": "Blue", "hero": "Aislinn",
                                      "site": stat_site_key(pins[0])}])
            visits = read_stat_visits(path)
        aislinn = visited_stat_sites(visits, "Blue", "Aislinn")
        dracon = visited_stat_sites(visits, "Blue", "Dracon")
        self.assertEqual(aislinn, {"0:0:0"})
        self.assertEqual(dracon, set())
        marked = map_figure(mask, 1, "Blue", 0, pins, visited_stats=aislinn)
        self.assertEqual(list(marked.data[1].marker.symbol), ["circle-open", "diamond"])
        hidden = map_figure(mask, 1, "Blue", 0, pins, visited_stats=aislinn,
                            hide_visited_stats=True)
        self.assertEqual(list(hidden.data[1].text), ["Stat increase: Marletto Tower"])
        self.assertIn("Visited by Aislinn", str(grouped_pin_list(pins, visited_stats=aislinn,
                                                                hero="Aislinn")))
        self.assertEqual(list(map_figure(mask, 1, "Blue", 0, pins,
                                         visited_stats=dracon,
                                         hide_visited_stats=True).data[1].x), [0, 1])

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

    def test_selected_location_has_green_ring_only_on_explored_player_level(self):
        mask = np.array([[[True, False]]])
        selected = {"id": "site", "player": "Red", "level": 0, "x": 0, "y": 0}
        figure = map_figure(mask, 2, "Red", 0, [], selected=selected)
        ring = figure.data[-1]
        self.assertEqual(ring.name, "Selected location")
        self.assertEqual(list(ring.x), [0])
        self.assertEqual(ring.marker.symbol, "circle-open")
        self.assertEqual(ring.marker.color, "#00FF66")
        self.assertEqual(list(ring.customdata), ["site"])
        self.assertEqual(figure.layout.annotations[-1].text, "SELECTED")
        self.assertEqual(len(map_figure(mask, 2, "Blue", 0, [], selected=selected).data), 1)
        self.assertEqual(len(map_figure(mask, 2, "Red", 0, [],
                                        selected={**selected, "x": 1}).data), 1)

    def test_pin_color_follows_category_and_list_is_grouped(self):
        self.assertEqual(len(CATEGORY_COLORS), len(set(CATEGORY_COLORS.values())))
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
        self.assertEqual(groups[0].children[0].children[0].style["backgroundColor"],
                         CATEGORY_COLORS["Portal"])
        self.assertEqual(groups[0].children[2].children[0].id["pin_id"], "b")
        self.assertEqual(groups[0].children[2].children[0].children,
                         "Blue portal - Surface (1/0)")

    def test_category_visibility_hides_map_markers_but_keeps_list_entries(self):
        mask = np.ones((1, 2, 2), dtype=bool)
        pins = [
            {"id": "a", "player": "Red", "level": 0, "x": 0, "y": 0,
             "title": "Gold bow", "category": "Artifact"},
            {"id": "b", "player": "Red", "level": 0, "x": 1, "y": 0,
             "title": "Blue portal", "category": "Portal"},
        ]
        hidden = ["Artifact"]
        figure = map_figure(mask, 2, "Red", 0, pins, hidden_categories=hidden)
        self.assertEqual(list(figure.data[1].text), ["Portal: Blue portal"])
        groups = grouped_pin_list(pins, hidden)
        self.assertEqual(groups[1].children[1].value, [])
        self.assertEqual(groups[0].children[1].value, ["Portal"])
        self.assertEqual(groups[1].children[2].children[0].children,
                         "Gold bow - Surface (0/0)")

    def test_hiding_towns_removes_marker_and_name(self):
        mask = np.ones((1, 2, 2), dtype=bool)
        town = {"level": 0, "x": 1, "y": 0, "name": "Castle"}
        pins = visible_town_pins([town], "Red")
        figure = map_figure(mask, 2, "Red", 0, pins, towns=[town],
                            hidden_categories=["Town"])
        self.assertEqual(len(figure.data), 1)
        self.assertEqual(len(figure.layout.annotations), 0)
        self.assertIn("Castle", str(grouped_pin_list(pins, ["Town"])))

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
        buttons = grouped_pin_list(pins)[0].children[2].children
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
        self.assertEqual(groups[0].children[2].children[0].id["pin_id"], "old-town")

    def test_auto_marker_types_cannot_be_added_manually(self):
        mask = np.array([[[True]]])
        for category in ("Portal", "Dragon Utopia", "Morale", "Luck", "Morale and luck",
                         "Morale and Luck", "Mana replenishment",
                         "Town", "Underground gate", "Creature level 1",
                         "Creature level 7"):
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
        self.assertEqual(pins[1]["category"], "Morale and Luck")
        self.assertEqual(pins[0]["notes"], "Attack or Defense +2")
        self.assertTrue(all(pin["automatic"] for pin in pins))
        self.assertEqual(len(grouped_pin_list(pins)), 2)
        self.assertNotIn("Faerie Ring", map_figure(mask, 2, "Red", 0, pins).to_json())
        self.assertEqual([pin["title"] for pin in visible_bonus_pins(sites, ~mask, "Blue")],
                         ["Faerie Ring"])
        self.assertEqual(visible_bonus_pins(sites, ~mask, "Blue")[0]["category"],
                         "Morale and Luck")

    def test_mana_pins_follow_exploration_and_group_by_category(self):
        sites = [
            {"level": 0, "x": 0, "y": 0, "title": "Magic Well",
             "category": "Mana replenishment", "notes": "Refills spell points"},
            {"level": 0, "x": 1, "y": 0, "title": "Magic Spring",
             "category": "Mana replenishment"},
            {"level": 1, "x": 1, "y": 0, "title": "Altar of Mana",
             "category": "Mana replenishment"},
        ]
        mask = np.array([[[True, False]], [[False, True]]])
        pins = visible_bonus_pins(sites, mask, "Blue")
        self.assertEqual([pin["title"] for pin in pins], ["Magic Well", "Altar of Mana"])
        self.assertTrue(all(pin["automatic"] for pin in pins))
        self.assertEqual(pins[0]["notes"], "Refills spell points")
        self.assertIn("Mana replenishment (2)", str(grouped_pin_list(pins)[0]))
        self.assertEqual(list(map_figure(mask, 1, "Blue", 0, pins).data[1].marker.color),
                         [CATEGORY_COLORS["Mana replenishment"]])
        self.assertNotIn("Magic Spring", map_figure(mask, 1, "Blue", 0, pins).to_json())

    def test_morale_and_luck_sites_share_one_pin_group(self):
        mask = np.ones((1, 2, 2), dtype=bool)
        sites = [{"level": 0, "x": x, "y": y, "title": title, "category": category}
                 for (x, y), title, category in [
                     ((0, 0), "Buoy", "Morale"),
                     ((1, 0), "Swan Pond", "Luck"),
                     ((0, 1), "Rally Flag", "Morale and luck")]]
        pins = visible_bonus_pins(sites, mask, "Red")
        self.assertEqual({pin["category"] for pin in pins}, {"Morale and Luck"})
        groups = grouped_pin_list(pins)
        self.assertEqual(len(groups), 1)
        self.assertIn("Morale and Luck (3)", str(groups[0].children[0].children))

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

    def test_creature_pins_are_read_only_and_exploration_filtered(self):
        self.assertNotIn("Creature", CATEGORIES)
        for level in range(1, 8):
            self.assertNotIn(f"Creature level {level}", CATEGORIES)
        creatures = [{"level": 0, "x": x, "y": 0, "title": name,
                      "category": f"Creature level {x + 1}"}
                     for x, name in enumerate(("Pikeman", "Archer"))]
        mask = np.array([[[True, False]]])
        pins = visible_creature_pins(creatures, mask, "Blue")
        self.assertEqual([pin["title"] for pin in pins], ["Pikeman"])
        self.assertEqual((pins[0]["category"], pins[0]["creature_level"]), ("Creature", 1))
        self.assertTrue(pins[0]["automatic"])
        group = grouped_pin_list(pins)[0]
        self.assertIn("Creature (1)", str(group.children[0].children))
        levels = group.children[1].children
        self.assertEqual(len(levels), 7)
        self.assertEqual(levels[0].children[0].children, "Level 1 (1)")
        self.assertEqual(levels[1].children[0].children, "Level 2 (0)")
        self.assertEqual(levels[0].children[2].children[0].children[0].children,
                         "Pikeman - Surface (0/0)")
        self.assertNotIn("Archer", map_figure(mask, 2, "Blue", 0, pins).to_json())
        self.assertEqual(normalized_hidden_categories(["Creature"]),
                         {f"Creature level {level}" for level in range(1, 8)} |
                         {"Creature (unknown level)"})

    def test_creature_levels_toggle_independently_with_one_color(self):
        mask = np.ones((1, 2, 2), dtype=bool)
        creatures = [
            {"level": 0, "x": 0, "y": 0, "title": "Pikeman",
             "category": "Creature", "creature_level": 1},
            {"level": 0, "x": 1, "y": 0, "title": "Halberdier",
             "category": "Creature", "creature_level": 1},
            {"level": 0, "x": 0, "y": 1, "title": "Archer",
             "category": "Creature", "creature_level": 2},
        ]
        pins = visible_creature_pins(creatures, mask, "Red")
        figure = map_figure(mask, 2, "Red", 0, pins)
        self.assertEqual(list(figure.data[1].marker.color),
                         [CATEGORY_COLORS["Creature"]] * 3)
        hidden = ["Creature level 1"]
        filtered = map_figure(mask, 2, "Red", 0, pins, hidden_categories=hidden)
        self.assertEqual(list(filtered.data[1].text), ["Creature level 2: Archer"])
        level_groups = grouped_pin_list(pins, hidden)[0].children[1].children
        self.assertEqual(level_groups[0].children[1].value, [])
        self.assertEqual(level_groups[1].children[1].value, ["Creature level 2"])
        self.assertEqual(len(level_groups[0].children[2].children), 2)
        self.assertEqual(level_groups[0].children[2].children[0].children[1].children,
                         "☆ Add to Favourites")

    def test_favourite_creatures_are_gold_and_missing_stacks_are_removed(self):
        mask = np.ones((1, 2, 2), dtype=bool)
        creatures = visible_creature_pins([
            {"level": 0, "x": 0, "y": 0, "title": "Pikeman", "category": "Creature",
             "creature_level": 1},
            {"level": 0, "x": 1, "y": 0, "title": "Archer", "category": "Creature",
             "creature_level": 2},
        ], mask, "Blue")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map_creature_favourites.json"
            write_pins(path, [
                {"player": "Blue", "creature_id": creatures[0]["id"],
                 "title": "Pikeman", "quantity": 25, "gold": 1500},
                {"player": "Blue", "creature_id": creatures[1]["id"],
                 "title": "Archer", "quantity": None, "gold": None},
                {"player": "Red", "creature_id": creatures[0]["id"],
                 "title": "Pikeman", "quantity": 5, "gold": 100},
            ])
            favourites = active_creature_favourites(path, "Blue", creatures)
            pins = favourite_creature_pins(creatures, favourites)
            self.assertEqual([pin["category"] for pin in pins],
                             ["Favourites", "Favourites"])
            self.assertEqual(favourite_gold_summary(pins), (1500, 1))
            self.assertEqual(list(map_figure(mask, 1, "Blue", 0, pins).data[1].marker.color),
                             [CATEGORY_COLORS["Favourites"]] * 2)
            self.assertEqual(len(map_figure(mask, 1, "Blue", 0, pins,
                                            hidden_categories=["Favourites"]).data), 1)
            self.assertIn("Favourites (2)", str(grouped_pin_list(pins)))

            active_creature_favourites(path, "Blue", creatures[1:])
            entries = read_creature_favourites(path)
            self.assertEqual([(item["player"], item["title"]) for item in entries],
                             [("Blue", "Archer"), ("Red", "Pikeman")])
            # A different creature at the same coordinates must not inherit a favourite.
            changed = [{**creatures[1], "title": "Marksman"}]
            self.assertEqual(active_creature_favourites(path, "Blue", changed), {})

    def test_favourite_numbers_are_optional_whole_stack_values(self):
        self.assertIsNone(optional_favourite_number("", "Joining gold", 0))
        self.assertEqual(optional_favourite_number(0, "Joining gold", 0), 0)
        self.assertEqual(optional_favourite_number("2500", "Joining gold", 0), 2500)
        for value in (-1, 1.5, True, "many"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                optional_favourite_number(value, "Creatures", 1)

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
        self.assertTrue(all(trace.marker.color == CATEGORY_COLORS["Town"]
                            for trace in figure.data[1:]))
        self.assertEqual({annotation.text for annotation in figure.layout.annotations},
                         {"Visible Keep", "Neutral Keep"})
        self.assertEqual({(trace.x[0], trace.y[0]) for trace in figure.data[1:]},
                         {(1, 0), (0, 0)})
        self.assertNotIn("Hidden Keep", figure.to_json())


if __name__ == "__main__":
    unittest.main()
