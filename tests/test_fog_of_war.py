import unittest
from unittest.mock import patch

import pandas as pd

import dashboard
from fog_of_war import fog_of_war_figure


class SpyRenderer:
    def __init__(self):
        self.calls = []

    def render_overview_data_url(self, mask, level, tile_size=8):
        self.calls.append((level, mask.copy()))
        return "data:image/png;base64,AAAA"


class FogOfWarFigureTests(unittest.TestCase):
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
            {"player_color": "Red", "day": 1, "fog_of_war": "1000", "town_summary": []},
            {"player_color": "Blue", "day": 1, "fog_of_war": "0100", "town_summary": []},
            {"player_color": "Blue", "day": 2, "fog_of_war": "0010", "town_summary": []},
        ])
        heroes = pd.DataFrame(columns=["player_color", "hero_name", "army_strength", "day"])
        army = pd.DataFrame([{"Day": 1}])
        with patch.object(dashboard.dash.Dash, "run", capture_run), patch.object(
            dashboard, "load_terrain_renderer", return_value=(renderer, "sample.h3m")
        ):
            dashboard.run_dashboard(
                heroes, army, pd.DataFrame(), players, pd.DataFrame(),
                {"map_size": 2, "levels": 1}, pd.DataFrame(), 8050,
                input_dir="sample",
            )

        callback = captured["app"].callback_map["fog_of_war_map.figure"]["callback"].__wrapped__
        figure = callback("Blue", 2, ["show"])
        self.assertEqual(figure.layout.title.text.split(" - ")[:3],
                         ["Fog of War", "Blue", "Day 2 (map size: 2, visibility offset: unknown)"])
        self.assertEqual(len(renderer.calls), 1)
        self.assertTrue(renderer.calls[0][1][0, 1, 0])
        self.assertFalse(renderer.calls[0][1][0, 0, 1])
        self.assertEqual(len(callback("Blue", 2, []).data), 0)


if __name__ == "__main__":
    unittest.main()
