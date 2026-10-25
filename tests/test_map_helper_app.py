import base64
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from map_helper_app import ProcessedGameData, create_app, day_from_save_name, load_latest_players, main


class StandaloneMapHelperTests(unittest.TestCase):
    def test_hero_stat_visit_toggle_persists_and_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "combined_player_data.json").write_text(json.dumps([{
                "filename": "111.GM2", "game_info": {"map_size": 2, "levels": 1},
                "players": {"Blue": {"fog_of_war": "1111", "heroes": [
                    {"name": "Aislinn"}, {"name": "Dracon"}]}}
            }]), encoding="utf-8")

            class FakeRenderer:
                transports = []
                bonuses = [{"level": 0, "x": 1, "y": 0, "title": "Arena",
                            "category": "Stat increase"}]
                utopias = []

                def render_data_url(self, mask, level):
                    return "data:image/png;base64,AAAA"

            with patch("map_helper_app.load_terrain_renderer", return_value=(FakeRenderer(), "test.h3m")):
                app = create_app(directory, player="Blue")
            client = app.server.test_client()
            selected = {"id": "auto:0:1:0:Stat increase", "player": "Blue", "level": 0,
                        "x": 1, "y": 0, "title": "Arena", "category": "Stat increase",
                        "automatic": True}

            def toggle(hero, revision):
                response = client.post("/_dash-update-component", json={
                    "output": "..map_stat_revision.data...map_stat_message.children..",
                    "outputs": [{"id": "map_stat_revision", "property": "data"},
                                {"id": "map_stat_message", "property": "children"}],
                    "inputs": [{"id": "map_stat_visit_toggle", "property": "n_clicks", "value": 1}],
                    "state": [{"id": "map_selected", "property": "data", "value": selected},
                              {"id": "map_stat_hero", "property": "value", "value": hero},
                              {"id": "map_player", "property": "data", "value": "Blue"},
                              {"id": "map_stat_revision", "property": "data", "value": revision}],
                    "changedPropIds": ["map_stat_visit_toggle.n_clicks"],
                })
                self.assertEqual(response.status_code, 200)
                return response.json["response"]

            first = toggle("Aislinn", 0)
            self.assertIn("visited", first["map_stat_message"]["children"])
            saved = json.loads(Path(directory, "map_stat_visits.json").read_text())
            self.assertEqual(saved, [{"player": "Blue", "hero": "Aislinn", "site": "0:1:0"}])
            self.assertEqual(toggle("Dracon", 1)["map_stat_revision"]["data"], 2)
            self.assertEqual(len(json.loads(Path(directory, "map_stat_visits.json").read_text())), 2)
            self.assertIn("unvisited", toggle("Aislinn", 2)["map_stat_message"]["children"])
            self.assertEqual(json.loads(Path(directory, "map_stat_visits.json").read_text()),
                             [{"player": "Blue", "hero": "Dracon", "site": "0:1:0"}])

    def test_category_toggle_updates_session_visibility(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "combined_player_data.json").write_text(json.dumps([{
                "filename": "111.GM1", "game_info": {"map_size": 2, "levels": 1},
                "players": {"Red": {"fog_of_war": "1111"}},
            }]), encoding="utf-8")
            app = create_app(directory, player="Red", graphics=False)
            pattern = {"category": ["ALL"], "type": "map_group_visibility"}
            ids = [{"category": "Artifact", "type": "map_group_visibility"},
                   {"category": "Portal", "type": "map_group_visibility"},
                   {"category": "Creature level 1", "type": "map_group_visibility"},
                   {"category": "Creature level 2", "type": "map_group_visibility"}]

            def toggle(values, hidden, changed="Artifact"):
                response = app.server.test_client().post("/_dash-update-component", json={
                    "output": "map_hidden_categories.data",
                    "outputs": {"id": "map_hidden_categories", "property": "data"},
                    "inputs": [{"id": pattern, "property": "value", "value": values}],
                    "state": [{"id": pattern, "property": "id", "value": ids},
                              {"id": "map_hidden_categories", "property": "data",
                               "value": hidden}],
                    "changedPropIds": [json.dumps(
                        {"category": changed, "type": "map_group_visibility"},
                        separators=(",", ":")) + ".value"],
                })
                self.assertEqual(response.status_code, 200)
                return response.json["response"]["map_hidden_categories"]["data"]

            self.assertEqual(toggle([[], ["Portal"], ["Creature level 1"],
                                     ["Creature level 2"]], []), ["Artifact"])
            self.assertEqual(toggle([["Artifact"], ["Portal"], ["Creature level 1"],
                                     ["Creature level 2"]], ["Artifact"]), [])
            self.assertEqual(toggle([["Artifact"], ["Portal"], [], ["Creature level 2"]],
                                    [], "Creature level 1"), ["Creature level 1"])

    def test_player_is_required_by_cli(self):
        with patch.object(sys, "argv", ["map_helper_app.py", "/unused/game"]):
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as raised:
                    main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--player", errors.getvalue())

    def test_save_name_day(self):
        self.assertEqual(day_from_save_name("/saves/424.GM1"), 95)
        self.assertIsNone(day_from_save_name("GAME_BEGIN.GM2"))
        self.assertIsNone(day_from_save_name("495.GM1"))

    def test_reads_latest_player_snapshots_and_serves_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = [
                {"filename": "111.GM1", "game_info": {"map_size": 2, "levels": 1},
                 "players": {"Red": {"fog_of_war": "1000"}, "Blue": {"fog_of_war": "0001"}}},
                {"filename": "112.GM1", "game_info": {},
                 "players": {"Red": {"fog_of_war": "1100"},
                             "Blue": {"fog_of_war": "0001", "towns": [
                                 {"name": "Bluehold", "coords": [1, 0, "Surface"]}]}}},
            ]
            source = Path(directory) / "combined_player_data.json"
            source.write_text(json.dumps(entries), encoding="utf-8")
            players, info = load_latest_players(directory)
            self.assertEqual(info["map_size"], 2)
            self.assertEqual(players.loc[players.player_color == "Red", "fog_of_war"].iloc[0], "1100")
            self.assertEqual(players.loc[players.player_color == "Blue", "fog_of_war"].iloc[0], "0001")
            self.assertEqual(players.loc[players.player_color == "Blue", "town_summary"].iloc[0][0]["town_name"], "Bluehold")
            app = create_app(directory, player="Blue")
            response = app.server.test_client().get("/_dash-layout")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"map_helper_graph", response.data)
            self.assertEqual(len(app.callback_map), 10)
            class FakeRenderer:
                transports = [
                    {"level": 0, "x": 0, "y": 0, "title": "Blue Two-way Portal", "category": "Portal"},
                    {"level": 0, "x": 1, "y": 1, "title": "Underground Gate", "category": "Underground gate"},
                ]
                bonuses = [
                    {"level": 0, "x": 0, "y": 0, "title": "Arena", "category": "Stat increase"},
                    {"level": 0, "x": 1, "y": 1, "title": "Faerie Ring", "category": "Luck"},
                ]
                utopias = [
                    {"level": 0, "x": 1, "y": 1, "title": "Dragon Utopia",
                     "category": "Dragon Utopia"},
                ]

                def render_data_url(self, mask, level):
                    return "data:image/png;base64,AAAA"

            with patch("map_helper_app.load_terrain_renderer", return_value=(FakeRenderer(), "test.h3m")):
                marked_app = create_app(directory, player="Blue")
            listed = marked_app.server.test_client().post("/_dash-update-component", json={
                "output": "map_pin_list.children",
                "outputs": {"id": "map_pin_list", "property": "children"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Blue"},
                           {"id": "map_revision", "property": "data", "value": 0},
                           {"id": "map_data_revision", "property": "data", "value": 0},
                           {"id": "map_stat_hero", "property": "value", "value": None},
                           {"id": "map_stat_revision", "property": "data", "value": 0}],
                "state": [{"id": "map_hidden_categories", "property": "data", "value": []}],
                "changedPropIds": ["map_data_revision.data"],
            })
            self.assertEqual(listed.status_code, 200)
            listed_text = json.dumps(listed.json)
            self.assertIn('"type": "Details"', listed_text)
            self.assertIn('"open": false', listed_text)
            self.assertIn("Underground Gate", listed_text)
            self.assertNotIn("Blue Two-way Portal", listed_text)
            self.assertIn("Faerie Ring", listed_text)
            self.assertIn("Morale and Luck (1)", listed_text)
            self.assertIn("Dragon Utopia", listed_text)
            self.assertNotIn("Arena", listed_text)
            town_app = create_app(directory, graphics=False, player="Red")
            town_list = town_app.server.test_client().post("/_dash-update-component", json={
                "output": "map_pin_list.children",
                "outputs": {"id": "map_pin_list", "property": "children"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Red"},
                           {"id": "map_revision", "property": "data", "value": 0},
                           {"id": "map_data_revision", "property": "data", "value": 0},
                           {"id": "map_stat_hero", "property": "value", "value": None},
                           {"id": "map_stat_revision", "property": "data", "value": 0}],
                "state": [{"id": "map_hidden_categories", "property": "data", "value": []}],
                "changedPropIds": ["map_data_revision.data"],
            })
            self.assertEqual(town_list.status_code, 200)
            self.assertIn("Town (1)", json.dumps(town_list.json))
            self.assertIn("Bluehold", json.dumps(town_list.json))
            blue_app = create_app(directory, graphics=False, player="blue")
            layout = blue_app.server.test_client().get("/_dash-layout").json

            def player_component(node):
                if isinstance(node, dict):
                    if node.get("props", {}).get("id") == "map_player":
                        return node
                    for value in node.values():
                        found = player_component(value)
                        if found:
                            return found
                elif isinstance(node, list):
                    for value in node:
                        found = player_component(value)
                        if found:
                            return found
                return None

            self.assertEqual(player_component(layout)["type"], "Store")
            self.assertEqual(player_component(layout)["props"]["data"], "Blue")
            self.assertNotIn(b'"id":"map_player","options"',
                             blue_app.server.test_client().get("/_dash-layout").data)
            with self.assertRaisesRegex(ValueError, "Available players: Red, Blue"):
                create_app(directory, graphics=False, player="Purple")

            live = ProcessedGameData(directory)
            before, revision = live.get()
            self.assertEqual(revision, 0)
            entries.append({"filename": "113.GM1", "game_info": {},
                            "players": {"Red": {"fog_of_war": "1110"},
                                        "Blue": {"fog_of_war": "1111"}}})
            source.write_text(json.dumps(entries), encoding="utf-8")
            after, revision = live.get()
            self.assertEqual(revision, 1)
            self.assertEqual(after.loc[after.player_color == "Blue", "fog_of_war"].iloc[0], "1111")
            self.assertEqual(live.get()[1], 1)
            poll = app.server.test_client().post("/_dash-update-component", json={
                "output": "map_data_revision.data",
                "outputs": {"id": "map_data_revision", "property": "data"},
                "inputs": [{"id": "map_poll", "property": "n_intervals", "value": 1}],
                "state": [{"id": "map_data_revision", "property": "data", "value": 0}],
                "changedPropIds": ["map_poll.n_intervals"],
            })
            self.assertEqual(poll.status_code, 200)
            self.assertEqual(poll.json["response"]["map_data_revision"]["data"], 1)
            redraw = app.server.test_client().post("/_dash-update-component", json={
                "output": "map_helper_graph.figure",
                "outputs": {"id": "map_helper_graph", "property": "figure"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Red"},
                           {"id": "map_level", "property": "value", "value": 0},
                           {"id": "map_revision", "property": "data", "value": 0},
                           {"id": "map_selected", "property": "data", "value": None},
                           {"id": "map_data_revision", "property": "data", "value": 1},
                           {"id": "map_hidden_categories", "property": "data", "value": []},
                           {"id": "map_stat_hero", "property": "value", "value": None},
                           {"id": "map_stat_revision", "property": "data", "value": 0},
                           {"id": "map_hide_visited_stats", "property": "value", "value": []}],
                "state": [], "changedPropIds": ["map_data_revision.data"],
            })
            self.assertEqual(redraw.status_code, 200)
            figure = redraw.json["response"]["map_helper_graph"]["figure"]
            self.assertIn("Blue · Day 3", figure["layout"]["title"]["text"])
            self.assertEqual(base64.b64decode(figure["data"][0]["z"]["bdata"]),
                             bytes([1, 1, 1, 1]))
            source.write_text("[", encoding="utf-8")
            with self.assertLogs("map_helper_app", level="WARNING"):
                self.assertEqual(live.get()[1], 1)
                self.assertEqual(live.get()[0].loc[lambda rows: rows.player_color == "Blue", "fog_of_war"].iloc[0],
                                 "1111")


if __name__ == "__main__":
    unittest.main()
