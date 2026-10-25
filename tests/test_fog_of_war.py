import unittest
from unittest.mock import patch

import pandas as pd

import dashboard
from fog_of_war import fog_of_war_figure, hero_track_colors


class SpyRenderer:
    def __init__(self):
        self.calls = []

    def render_overview_data_url(self, mask, level, tile_size=8):
        self.calls.append((level, mask.copy()))
        return "data:image/png;base64,AAAA"


class FogOfWarFigureTests(unittest.TestCase):
    def test_hero_trails_follow_saved_days_without_crossing_levels_or_gaps(self):
        heroes = pd.DataFrame([
            {"player_color": "Red", "hero_name": "Adele", "day": 1,
             "coords": {"x": 0, "y": 0, "z": 0}},
            {"player_color": "Red", "hero_name": "Adele", "day": 2,
             "coords": {"x": 1, "y": 0, "z": 0}},
            {"player_color": "Red", "hero_name": "Adele", "day": 3,
             "coords": {"x": 1, "y": 1, "z": 1}},
            {"player_color": "Red", "hero_name": "Adele", "day": 4,
             "coords": {"x": 2, "y": 1, "z": 1}},
            {"player_color": "Red", "hero_name": "Adele", "day": 6,
             "coords": {"x": 2, "y": 2, "z": 1}},
            {"player_color": "Red", "hero_name": "Bertram", "day": 2,
             "coords": {"x": 2, "y": 2, "z": 0}},
            {"player_color": "Blue", "hero_name": "Adele", "day": 2,
             "coords": {"x": 2, "y": 0, "z": 0}},
        ])
        colors = hero_track_colors(heroes, "Red")
        self.assertEqual(set(colors), {"Adele", "Bertram"})
        self.assertNotEqual(colors["Adele"], colors["Bertram"])
        self.assertEqual(colors["Adele"], hero_track_colors(heroes, "Blue")["Adele"])
        figure = fog_of_war_figure("Red", 6, "1" * 18, [], None, 3, 2,
                                   "#ff0000", hero_history=heroes,
                                   selected_heroes=["Adele"], hero_colors=colors)
        self.assertEqual(len(figure.data), 6)  # Two maps, with outlined tracks on each level.
        surface, underground = figure.data[3], figure.data[5]
        self.assertEqual(list(surface.x), [2, 6])
        self.assertEqual(list(underground.x), [38, 42, None, 42])
        self.assertEqual(surface.line.color, underground.line.color)
        self.assertNotIn("Bertram", figure.to_json())
        self.assertNotIn("(2, 0)", figure.to_json())  # Blue's Adele is excluded.

        covered = fog_of_war_figure("Red", 6, "1" * 17 + "0", [], None, 3, 2,
                                    "#ff0000", hero_history=heroes,
                                    selected_heroes=["Adele"], hero_colors=colors)
        self.assertEqual(list(covered.data[5].x), [38, 42])
        lost_hero = fog_of_war_figure("Red", 6, "1" * 18, [], None, 3, 2,
                                      "#ff0000", hero_history=heroes,
                                      selected_heroes=["Bertram"], hero_colors=colors)
        self.assertEqual(list(lost_hero.data[2].x), [10])

    def test_terrain_rendering_receives_selected_fog_and_hides_covered_markers(self):
        renderer = SpyRenderer()
        towns = [{"coords": [0, 0, "Surface"]},
                 {"coords": [1, 0, "Surface"]},
                 {"coords": [1, 1, "Underground"]}]
        utopias = pd.DataFrame([
            {"X": 1, "Y": 0, "underground": False},
            {"X": 1, "Y": 1, "underground": True},
        ])
        figure = fog_of_war_figure("Red", 3, "10000001", towns, utopias,
                                   2, 2, "#ff0000", renderer=renderer)
        self.assertEqual(len(renderer.calls), 2)
        self.assertTrue(renderer.calls[0][1][0, 0, 0])
        self.assertFalse(renderer.calls[0][1][0, 0, 1])
        self.assertTrue(renderer.calls[1][1][1, 1, 1])
        self.assertTrue(all(trace.source.startswith("data:image/png;base64,")
                            for trace in figure.data))
        self.assertEqual([item.text for item in figure.layout.annotations],
                         ["■", "Ground", "X", "■", "Underground"])
        self.assertEqual(figure.layout.dragmode, "pan")
        figure.to_json()

    def test_missing_renderer_uses_colored_grid_and_bad_fog_stays_blank(self):
        figure = fog_of_war_figure("Blue", 1, "1000", [], None, 2, 1, "#0000ff")
        image = figure.data[0]
        self.assertEqual(image.z[0][0].tolist(), [0, 0, 255])
        self.assertEqual(image.z[0][4].tolist(), [200, 200, 200])
        self.assertEqual(len(fog_of_war_figure("Blue", 1, "1", [], None,
                                                2, 1, "#0000ff").data), 0)

    def test_dashboard_callback_uses_selected_player_and_day(self):
        renderer = SpyRenderer()
        captured = {}

        def capture_run(app, **kwargs):
            captured["app"] = app

        players = pd.DataFrame([
            {"player_color": "Red", "day": 1, "snapshot_index": 0,
             "fog_of_war": "1000", "town_summary": []},
            {"player_color": "Blue", "day": 1, "snapshot_index": 0,
             "fog_of_war": "0100", "town_summary": []},
            {"player_color": "Blue", "day": 1, "snapshot_index": 1,
             "fog_of_war": "0100", "town_summary": []},
            {"player_color": "Blue", "day": 2, "snapshot_index": 2,
             "fog_of_war": "0010", "town_summary": []},
        ])
        heroes = pd.DataFrame([
            {"player_color": "Blue", "hero_name": "Solmyr", "army_strength": 0,
             "day": 1, "snapshot_index": 1, "coords": {"x": 1, "y": 0, "z": 0}},
            {"player_color": "Blue", "hero_name": "Solmyr", "army_strength": 0,
             "day": 2, "snapshot_index": 2, "coords": {"x": 0, "y": 1, "z": 0}},
            {"player_color": "Blue", "hero_name": "Cyra", "army_strength": 0,
             "day": 1, "snapshot_index": 1, "coords": {"x": 1, "y": 0, "z": 0}},
            {"player_color": "Blue", "hero_name": "Jeddite", "army_strength": 0,
             "day": 1, "snapshot_index": 0, "coords": {"x": 1, "y": 0, "z": 0}},
            {"player_color": "Red", "hero_name": "Gelu", "army_strength": 0,
             "day": 1, "snapshot_index": 0, "coords": {"x": 0, "y": 0, "z": 0}},
        ])
        army = pd.DataFrame([{"Day": 1}])
        with patch.object(dashboard.dash.Dash, "run", capture_run), patch.object(
            dashboard, "load_terrain_renderer", return_value=(renderer, "sample.h3m")
        ):
            dashboard.run_dashboard(
                heroes, army, pd.DataFrame(), players, pd.DataFrame(),
                {"map_size": 2, "levels": 1}, pd.DataFrame(), 8050,
                input_dir="sample",
            )

        layout = captured["app"].server.test_client().get("/_dash-layout")
        self.assertEqual(layout.status_code, 200)
        self.assertIn(b"fog_hero_selector", layout.data)

        def component(node, component_id):
            if isinstance(node, dict):
                if node.get("props", {}).get("id") == component_id:
                    return node
                for value in node.values():
                    found = component(value, component_id)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for value in node:
                    found = component(value, component_id)
                    if found is not None:
                        return found
            return None

        graph = component(layout.json, "fog_of_war_map")
        self.assertTrue(graph["props"]["responsive"])
        self.assertEqual(graph["props"]["style"], {"width": "100%", "height": "100%"})
        frame = component(layout.json, "fog_map_frame")
        self.assertEqual(frame["props"]["style"]["width"], "100%")
        self.assertEqual(frame["props"]["style"]["aspectRatio"], "16 / 96")

        callback = captured["app"].callback_map["fog_of_war_map.figure"]["callback"].__wrapped__
        figure = callback("Blue", 2, ["show"], ["Solmyr"])
        self.assertEqual(figure.layout.title.text.split(" - ")[:3],
                         ["Fog of War", "Blue", "Day 2 (map size: 2, visibility offset: unknown)"])
        self.assertEqual(len(renderer.calls), 1)
        self.assertTrue(renderer.calls[0][1][0, 1, 0])
        self.assertFalse(renderer.calls[0][1][0, 0, 1])
        self.assertEqual(len(figure.data), 2)
        self.assertEqual(figure.data[1].mode, "lines+markers")
        self.assertIsNone(figure.layout.width)
        self.assertIsNone(figure.layout.height)
        self.assertEqual(len(callback("Blue", 2, ["show"], ["Cyra"]).data), 1)
        self.assertEqual(len(callback("Blue", 2, [], ["Solmyr"]).data), 0)

        options_key = next(key for key in captured["app"].callback_map
                           if "fog_hero_selector.options" in key)
        options_callback = captured["app"].callback_map[options_key]["callback"].__wrapped__
        options, selected = options_callback("Blue", 1, [])
        self.assertEqual([option["value"] for option in options], ["Cyra", "Solmyr"])
        self.assertNotIn("Jeddite", [option["value"] for option in options])
        self.assertEqual(selected, [])
        later_options, later_selected = options_callback("Blue", 2, ["Cyra", "Solmyr"])
        self.assertEqual([option["value"] for option in later_options], ["Solmyr"])
        self.assertEqual(later_selected, ["Solmyr"])
        red_options, red_selected = options_callback("Red", 1, ["Solmyr"])
        self.assertEqual([option["value"] for option in red_options], ["Gelu"])
        self.assertEqual(red_selected, [])


if __name__ == "__main__":
    unittest.main()
