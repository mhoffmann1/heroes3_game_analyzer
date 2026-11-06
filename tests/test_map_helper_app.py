import base64
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from dash import Dash

from map_helper import register_map_helper
from map_helper_app import ProcessedGameData, create_app, day_from_save_name, load_latest_players, main


class StandaloneMapHelperTests(unittest.TestCase):
    def test_creature_favourites_edit_total_and_disappearance(self):
        with tempfile.TemporaryDirectory() as directory:
            creatures = [
                {"level": 0, "x": 0, "y": 0, "title": "Pikeman",
                 "category": "Creature", "creature_level": 1},
                {"level": 0, "x": 1, "y": 0, "title": "Archer",
                 "category": "Creature", "creature_level": 2},
            ]
            rows = pd.DataFrame([{"day": 1, "player_color": "Blue", "fog_of_war": "1111"}])
            app = Dash(__name__)
            app.layout = register_map_helper(app, rows, {"map_size": 2, "levels": 1},
                                             directory, default_player="Blue", lock_player=True,
                                             creature_provider=lambda: creatures)
            client = app.server.test_client()
            pin_ids = [f"auto:0:{x}:0:Creature" for x in (0, 1)]
            patterns = {action: {"type": f"map_favourite_{action}", "pin_id": ["ALL"]}
                        for action in ("add", "remove", "save", "quantity", "gold")}

            def change(action, pin_id, revision, quantity=None, gold=None):
                button_id = {"type": f"map_favourite_{action}", "pin_id": pin_id}
                response = client.post("/_dash-update-component", json={
                    "output": "..map_favourites_revision.data...map_favourite_message.children..",
                    "outputs": [{"id": "map_favourites_revision", "property": "data"},
                                {"id": "map_favourite_message", "property": "children"}],
                    "inputs": [
                        {"id": "map_favourite_selected", "property": "n_clicks", "value": 0},
                        {"id": patterns["add"], "property": "n_clicks",
                         "value": [1] if action == "add" else []},
                        {"id": patterns["remove"], "property": "n_clicks",
                         "value": [1] if action == "remove" else []},
                        {"id": patterns["save"], "property": "n_clicks",
                         "value": [1] if action == "save" else []},
                    ],
                    "state": [
                        {"id": patterns["quantity"], "property": "value",
                         "value": [quantity] if action == "save" else []},
                        {"id": patterns["quantity"], "property": "id",
                         "value": [{"type": "map_favourite_quantity", "pin_id": pin_id}]
                         if action == "save" else []},
                        {"id": patterns["gold"], "property": "value",
                         "value": [gold] if action == "save" else []},
                        {"id": patterns["gold"], "property": "id",
                         "value": [{"type": "map_favourite_gold", "pin_id": pin_id}]
                         if action == "save" else []},
                        {"id": "map_selected", "property": "data", "value": None},
                        {"id": "map_player", "property": "data", "value": "Blue"},
                        {"id": "map_favourites_revision", "property": "data", "value": revision},
                    ],
                    "changedPropIds": [json.dumps(button_id, separators=(",", ":")) + ".n_clicks"],
                })
                self.assertEqual(response.status_code, 200)
                return response.json["response"]

            self.assertEqual(change("add", pin_ids[0], 0)["map_favourites_revision"]["data"], 1)
            self.assertEqual(change("add", pin_ids[1], 1)["map_favourites_revision"]["data"], 2)
            self.assertEqual(change("save", pin_ids[0], 2, 12, 700)["map_favourites_revision"]["data"], 3)
            self.assertEqual(change("save", pin_ids[1], 3, 4, 300)["map_favourites_revision"]["data"], 4)
            entries = json.loads(Path(directory, "map_creature_favourites.json").read_text())
            self.assertEqual([(item["quantity"], item["gold"]) for item in entries],
                             [(12, 700), (4, 300)])

            total = client.post("/_dash-update-component", json={
                "output": "map_favourites_total.children",
                "outputs": {"id": "map_favourites_total", "property": "children"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Blue"},
                           {"id": "map_favourites_revision", "property": "data", "value": 4},
                           {"id": "map_data_revision", "property": "data", "value": 0}],
                "state": [], "changedPropIds": ["map_favourites_revision.data"],
            })
            self.assertEqual(total.status_code, 200)
            self.assertIn("1,000 (2 priced stacks)", total.json["response"]
                          ["map_favourites_total"]["children"])

            figure = client.post("/_dash-update-component", json={
                "output": "map_helper_graph.figure",
                "outputs": {"id": "map_helper_graph", "property": "figure"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Blue"},
                           {"id": "map_level", "property": "value", "value": 0},
                           {"id": "map_revision", "property": "data", "value": 0},
                           {"id": "map_selected", "property": "data", "value": None},
                           {"id": "map_data_revision", "property": "data", "value": 0},
                           {"id": "map_favourites_revision", "property": "data", "value": 4},
                           {"id": "map_hidden_categories", "property": "data", "value": []},
                           {"id": "map_stat_hero", "property": "value", "value": None},
                           {"id": "map_stat_revision", "property": "data", "value": 0},
                           {"id": "map_hide_visited_stats", "property": "value", "value": []},
                           {"id": "map_stat_interest_enabled", "property": "data", "value": False}],
                "state": [], "changedPropIds": ["map_favourites_revision.data"],
            })
            self.assertEqual(figure.status_code, 200)
            marker = figure.json["response"]["map_helper_graph"]["figure"]["data"][1]
            self.assertEqual(marker["marker"]["color"], ["#FFD700", "#FFD700"])

            selected = {"id": pin_ids[0], "player": "Blue", "level": 0,
                        "x": 0, "y": 0, "title": "Pikeman", "category": "Favourites",
                        "automatic": True}
            selected_action = client.post("/_dash-update-component", json={
                "output": "..map_favourites_revision.data...map_favourite_message.children..",
                "outputs": [{"id": "map_favourites_revision", "property": "data"},
                            {"id": "map_favourite_message", "property": "children"}],
                "inputs": [
                    {"id": "map_favourite_selected", "property": "n_clicks", "value": 1},
                    {"id": patterns["add"], "property": "n_clicks", "value": []},
                    {"id": patterns["remove"], "property": "n_clicks", "value": []},
                    {"id": patterns["save"], "property": "n_clicks", "value": []}],
                "state": [
                    {"id": patterns["quantity"], "property": "value", "value": []},
                    {"id": patterns["quantity"], "property": "id", "value": []},
                    {"id": patterns["gold"], "property": "value", "value": []},
                    {"id": patterns["gold"], "property": "id", "value": []},
                    {"id": "map_selected", "property": "data", "value": selected},
                    {"id": "map_player", "property": "data", "value": "Blue"},
                    {"id": "map_favourites_revision", "property": "data", "value": 4}],
                "changedPropIds": ["map_favourite_selected.n_clicks"],
            })
            self.assertEqual(selected_action.status_code, 200)
            self.assertEqual(selected_action.json["response"]
                             ["map_favourites_revision"]["data"], 5)
            self.assertEqual(change("add", pin_ids[0], 5)
                             ["map_favourites_revision"]["data"], 6)
            self.assertEqual(change("remove", pin_ids[0], 6)
                             ["map_favourites_revision"]["data"], 7)
            creatures[:] = creatures[:1]
            total = client.post("/_dash-update-component", json={
                "output": "map_favourites_total.children",
                "outputs": {"id": "map_favourites_total", "property": "children"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Blue"},
                           {"id": "map_favourites_revision", "property": "data", "value": 7},
                           {"id": "map_data_revision", "property": "data", "value": 1}],
                "state": [], "changedPropIds": ["map_data_revision.data"],
            })
            self.assertIn("0 (0 priced stacks)", total.json["response"]
                          ["map_favourites_total"]["children"])
            self.assertEqual(json.loads(Path(directory, "map_creature_favourites.json").read_text()), [])

    def test_stat_overview_refreshes_after_visit_and_new_save(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "combined_player_data.json")

            def save(filename, attack, fog):
                source.write_text(json.dumps([{
                    "filename": filename, "game_info": {"map_size": 2, "levels": 1},
                    "players": {"Blue": {"fog_of_war": fog, "heroes": [{
                        "name": "Aislinn", "primary_skills": {"attack": attack,
                        "defense": 3, "spell_power": 2, "knowledge": 1},
                        "coords": {"x": 0, "y": 0, "z": 0}}]}}
                }]), encoding="utf-8")

            save("111.GM2", 4, "1000")

            class FakeRenderer:
                transports = []
                bonuses = [
                    {"level": 0, "x": 0, "y": 0, "title": "Mercenary Camp",
                     "category": "Stat increase"},
                    {"level": 0, "x": 1, "y": 0, "title": "Arena", "category": "Stat increase"},
                ]
                utopias = []

                def render_data_url(self, mask, level):
                    return "data:image/png;base64,AAAA"

            with patch("map_helper_app.load_terrain_renderer", return_value=(FakeRenderer(), "test.h3m")):
                app = create_app(directory, player="Blue")
            client = app.server.test_client()

            enabled = client.post("/_dash-update-component", json={
                "output": "map_stat_interest_enabled.data",
                "outputs": {"id": "map_stat_interest_enabled", "property": "data"},
                "inputs": [{"id": "map_stat_interest_toggle", "property": "n_clicks", "value": 1}],
                "state": [{"id": "map_stat_interest_enabled", "property": "data", "value": False}],
                "changedPropIds": ["map_stat_interest_toggle.n_clicks"],
            })
            self.assertEqual(enabled.status_code, 200)
            self.assertTrue(enabled.json["response"]["map_stat_interest_enabled"]["data"])

            def interests():
                response = client.post("/_dash-update-component", json={
                    "output": "map_stat_interest_summary.children",
                    "outputs": {"id": "map_stat_interest_summary", "property": "children"},
                    "inputs": [{"id": "map_stat_interest_enabled", "property": "data", "value": True},
                               {"id": "map_player", "property": "data", "value": "Blue"},
                               {"id": "map_stat_hero", "property": "value", "value": "Aislinn"},
                               {"id": "map_stat_revision", "property": "data", "value": 0},
                               {"id": "map_data_revision", "property": "data", "value": 0}],
                    "state": [], "changedPropIds": ["map_stat_revision.data"],
                })
                self.assertEqual(response.status_code, 200)
                return json.dumps(response.json["response"], ensure_ascii=False)

            self.assertIn("Mercenary Camp", interests())
            self.assertNotIn('"children": "Arena"', interests())
            self.assertIn("Attack +1, Defense +0, Power +0, Knowledge +0", interests())
            self.assertIn("map_interest_area", interests())

            def overview():
                response = client.post("/_dash-update-component", json={
                    "output": "map_stat_overview.children",
                    "outputs": {"id": "map_stat_overview", "property": "children"},
                    "inputs": [{"id": "map_player", "property": "data", "value": "Blue"},
                               {"id": "map_stat_hero", "property": "value", "value": "Aislinn"},
                               {"id": "map_stat_revision", "property": "data", "value": 0},
                               {"id": "map_data_revision", "property": "data", "value": 0}],
                    "state": [], "changedPropIds": ["map_data_revision.data"],
                })
                self.assertEqual(response.status_code, 200)
                return json.dumps(response.json["response"]["map_stat_overview"], ensure_ascii=False)

            self.assertIn("4 → 5", overview())
            self.assertNotIn("Arena visited", overview())
            marked = client.post("/_dash-update-component", json={
                "output": "..map_stat_revision.data...map_stat_message.children..",
                "outputs": [{"id": "map_stat_revision", "property": "data"},
                            {"id": "map_stat_message", "property": "children"}],
                "inputs": [{"id": "map_stat_visit_toggle", "property": "n_clicks", "value": 1},
                           {"id": "map_stat_unvisit", "property": "n_clicks", "value": 0},
                           {"id": "map_helper_graph", "property": "clickData", "value": None}],
                "state": [{"id": "map_selected", "property": "data",
                           "value": {"player": "Blue", "level": 0, "x": 0, "y": 0}},
                          {"id": "map_stat_hero", "property": "value", "value": "Aislinn"},
                          {"id": "map_player", "property": "data", "value": "Blue"},
                          {"id": "map_stat_revision", "property": "data", "value": 0},
                          {"id": "map_level", "property": "value", "value": 0}],
                "changedPropIds": ["map_stat_visit_toggle.n_clicks"],
            })
            self.assertEqual(marked.status_code, 200)
            self.assertEqual(marked.json["response"]["map_stat_revision"]["data"], 1)
            self.assertEqual(json.loads(Path(directory, "map_stat_visits.json").read_text()),
                             [{"player": "Blue", "hero": "Aislinn", "site": "0:0:0"}])
            self.assertIn("4 → 4", overview())
            self.assertIn("No discovered, unvisited stat sites remain", interests())
            rendered = client.post("/_dash-update-component", json={
                "output": "map_helper_graph.figure",
                "outputs": {"id": "map_helper_graph", "property": "figure"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Blue"},
                           {"id": "map_level", "property": "value", "value": 0},
                           {"id": "map_revision", "property": "data", "value": 0},
                           {"id": "map_selected", "property": "data", "value": None},
                           {"id": "map_data_revision", "property": "data", "value": 0},
                           {"id": "map_favourites_revision", "property": "data", "value": 0},
                           {"id": "map_hidden_categories", "property": "data", "value": []},
                           {"id": "map_stat_hero", "property": "value", "value": "Aislinn"},
                           {"id": "map_stat_revision", "property": "data", "value": 1},
                           {"id": "map_hide_visited_stats", "property": "value", "value": []},
                           {"id": "map_stat_interest_enabled", "property": "data", "value": False}],
                "state": [], "changedPropIds": ["map_stat_revision.data"],
            })
            self.assertEqual(rendered.status_code, 200)
            markers = rendered.json["response"]["map_helper_graph"]["figure"]["data"][1]
            self.assertEqual(markers["marker"]["symbol"], ["circle-open"])
            save("112.GM2", 5, "1100")
            self.assertIn("5 → 7", overview())
            self.assertIn("Arena visited", overview())
            self.assertIn("Arena (weight 2)", interests())

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
                            "category": "Stat increase"},
                           {"level": 0, "x": 0, "y": 1, "title": "Tree of Knowledge",
                            "category": "Level increase"}]
                utopias = []

                def render_data_url(self, mask, level):
                    return "data:image/png;base64,AAAA"

            with patch("map_helper_app.load_terrain_renderer", return_value=(FakeRenderer(), "test.h3m")):
                app = create_app(directory, player="Blue")
            client = app.server.test_client()
            selected = {"id": "auto:0:1:0:Stat increase", "player": "Blue", "level": 0,
                        "x": 1, "y": 0, "title": "Arena", "category": "Stat increase",
                        "automatic": True}

            def toggle(hero, revision, use_map=False, unvisit=False, site=selected):
                response = client.post("/_dash-update-component", json={
                    "output": "..map_stat_revision.data...map_stat_message.children..",
                    "outputs": [{"id": "map_stat_revision", "property": "data"},
                                {"id": "map_stat_message", "property": "children"}],
                    "inputs": [{"id": "map_stat_visit_toggle", "property": "n_clicks", "value": 1},
                               {"id": "map_stat_unvisit", "property": "n_clicks", "value": 1},
                               {"id": "map_helper_graph", "property": "clickData",
                                "value": {"points": [{"customdata": site["id"]}]}
                                if use_map else None}],
                    "state": [{"id": "map_selected", "property": "data", "value": site},
                              {"id": "map_stat_hero", "property": "value", "value": hero},
                              {"id": "map_player", "property": "data", "value": "Blue"},
                              {"id": "map_stat_revision", "property": "data", "value": revision},
                              {"id": "map_level", "property": "value", "value": 0}],
                    "changedPropIds": ["map_helper_graph.clickData" if use_map else
                                       "map_stat_unvisit.n_clicks" if unvisit else
                                       "map_stat_visit_toggle.n_clicks"],
                })
                self.assertEqual(response.status_code, 200)
                return response.json["response"]

            first = toggle("Aislinn", 0, use_map=True)
            self.assertIn("visited", first["map_stat_message"]["children"])
            saved = json.loads(Path(directory, "map_stat_visits.json").read_text())
            self.assertEqual(saved, [{"player": "Blue", "hero": "Aislinn", "site": "0:1:0"}])
            self.assertEqual(toggle("Dracon", 1)["map_stat_revision"]["data"], 2)
            self.assertEqual(len(json.loads(Path(directory, "map_stat_visits.json").read_text())), 2)
            self.assertIn("unvisited", toggle("Aislinn", 2, unvisit=True)["map_stat_message"]["children"])
            self.assertEqual(json.loads(Path(directory, "map_stat_visits.json").read_text()),
                             [{"player": "Blue", "hero": "Dracon", "site": "0:1:0"}])

            def target_status(hero, site=selected):
                response = client.post("/_dash-update-component", json={
                    "output": "map_stat_target.children",
                    "outputs": {"id": "map_stat_target", "property": "children"},
                    "inputs": [{"id": "map_selected", "property": "data", "value": site},
                               {"id": "map_stat_hero", "property": "value", "value": hero},
                               {"id": "map_stat_revision", "property": "data", "value": 3}],
                    "state": [{"id": "map_player", "property": "data", "value": "Blue"}],
                    "changedPropIds": ["map_stat_revision.data"],
                })
                self.assertEqual(response.status_code, 200)
                return response.json["response"]["map_stat_target"]["children"]

            self.assertEqual(target_status("Aislinn"), "Arena · Aislinn: unvisited")
            self.assertEqual(target_status("Dracon"), "Arena · Dracon: visited")
            self.assertIn("Select a discovered", target_status("Aislinn", None))
            self.assertIn("Choose a hero", target_status(None))
            self.assertIn("Select a discovered stat or level site",
                          toggle("Aislinn", 3, site=None)["map_stat_message"]["children"])

            pattern = {"pin_id": ["ALL"], "type": "map_pin_button"}
            area_pattern = {"site": ["ALL"], "type": "map_interest_area"}

            def select(changed, selected_pin=None, clicks=0, area_click=False):
                response = client.post("/_dash-update-component", json={
                    "output": "..map_selected.data...map_level.value..",
                    "outputs": [{"id": "map_selected", "property": "data"},
                                {"id": "map_level", "property": "value"}],
                    "inputs": [{"id": "map_helper_graph", "property": "clickData", "value": None},
                               {"id": pattern, "property": "n_clicks", "value": [1]},
                               {"id": area_pattern, "property": "n_clicks",
                                "value": [1] if area_click else []},
                               {"id": "map_player", "property": "data", "value": "Blue"},
                               {"id": "map_action", "property": "data", "value": None},
                               {"id": "map_show_selected", "property": "n_clicks", "value": clicks}],
                    "state": [{"id": "map_level", "property": "value", "value": 0},
                              {"id": "map_selected", "property": "data", "value": selected_pin},
                              {"id": "map_stat_hero", "property": "value", "value": "Aislinn"}],
                    "changedPropIds": [changed],
                })
                self.assertEqual(response.status_code, 200)
                return response.json["response"]["map_selected"]["data"]

            pin_button = json.dumps({"pin_id": selected["id"], "type": "map_pin_button"},
                                    separators=(",", ":")) + ".n_clicks"
            from_list = select(pin_button)
            self.assertFalse(from_list["focus"])
            empty_graph_click = client.post("/_dash-update-component", json={
                "output": "..map_selected.data...map_level.value..",
                "outputs": [{"id": "map_selected", "property": "data"},
                            {"id": "map_level", "property": "value"}],
                "inputs": [{"id": "map_helper_graph", "property": "clickData", "value": None},
                           {"id": pattern, "property": "n_clicks", "value": [1]},
                           {"id": area_pattern, "property": "n_clicks", "value": []},
                           {"id": "map_player", "property": "data", "value": "Blue"},
                           {"id": "map_action", "property": "data", "value": None},
                           {"id": "map_show_selected", "property": "n_clicks", "value": 0}],
                "state": [{"id": "map_level", "property": "value", "value": 0},
                          {"id": "map_selected", "property": "data", "value": from_list},
                          {"id": "map_stat_hero", "property": "value", "value": "Aislinn"}],
                "changedPropIds": ["map_helper_graph.clickData"],
            })
            self.assertEqual(empty_graph_click.status_code, 200)
            self.assertEqual(empty_graph_click.json["response"], {})
            rendered = client.post("/_dash-update-component", json={
                "output": "map_helper_graph.figure",
                "outputs": {"id": "map_helper_graph", "property": "figure"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Blue"},
                           {"id": "map_level", "property": "value", "value": 0},
                           {"id": "map_revision", "property": "data", "value": 0},
                           {"id": "map_selected", "property": "data", "value": from_list},
                           {"id": "map_data_revision", "property": "data", "value": 0},
                           {"id": "map_favourites_revision", "property": "data", "value": 0},
                           {"id": "map_hidden_categories", "property": "data", "value": []},
                           {"id": "map_stat_hero", "property": "value", "value": "Aislinn"},
                           {"id": "map_stat_revision", "property": "data", "value": 3},
                           {"id": "map_hide_visited_stats", "property": "value", "value": []},
                           {"id": "map_stat_interest_enabled", "property": "data", "value": False}],
                "state": [], "changedPropIds": ["map_selected.data"],
            })
            self.assertEqual(rendered.status_code, 200)
            figure = rendered.json["response"]["map_helper_graph"]["figure"]
            self.assertIn("Selected location", [trace.get("name") for trace in figure["data"]])
            self.assertIn("SELECTED", [item.get("text") for item in
                                       figure["layout"].get("annotations", [])])
            shown = select("map_show_selected.n_clicks", from_list, 1)
            self.assertTrue(shown["focus"])
            self.assertEqual(shown["focus_request"], 1)
            self.assertEqual(select(pin_button, shown)["focus_request"], 1)
            self.assertFalse(select(pin_button, shown)["focus"])
            area_button = json.dumps({"site": selected["id"], "type": "map_interest_area"},
                                     separators=(",", ":")) + ".n_clicks"
            self.assertTrue(select(area_button, from_list, area_click=True)["focus"])

            tree = {"id": "auto:0:0:1:Level increase", "player": "Blue", "level": 0,
                    "x": 0, "y": 1, "title": "Tree of Knowledge",
                    "category": "Level increase", "automatic": True}
            self.assertIn("visited", toggle("Aislinn", 3, use_map=True, site=tree)
                          ["map_stat_message"]["children"])
            self.assertEqual(target_status("Aislinn", tree),
                             "Tree of Knowledge · Aislinn: visited")
            self.assertEqual(target_status("Dracon", tree),
                             "Tree of Knowledge · Dracon: unvisited")
            self.assertIn("unvisited", toggle("Aislinn", 4, unvisit=True, site=tree)
                          ["map_stat_message"]["children"])
            self.assertEqual(target_status("Aislinn", tree),
                             "Tree of Knowledge · Aislinn: unvisited")

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
                 "obelisks": {"total": 1, "table_offset": 100,
                               "objects": [{"index": 0, "visited_by": ["Blue"]}]},
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
            self.assertEqual(players.loc[players.player_color == "Blue", "obelisk_data"].iloc[0]["total"], 1)
            self.assertEqual(players.loc[players.player_color == "Blue", "town_summary"].iloc[0][0]["town_name"], "Bluehold")
            app = create_app(directory, player="Blue")
            response = app.server.test_client().get("/_dash-layout")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"map_helper_graph", response.data)
            self.assertEqual(len(app.callback_map), 17)
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
                obelisks = [{"level": 0, "x": 1, "y": 1, "obelisk_index": 0,
                             "title": "Obelisk", "category": "Obelisk"}]

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
                           {"id": "map_stat_revision", "property": "data", "value": 0},
                           {"id": "map_favourites_revision", "property": "data", "value": 0}],
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
            self.assertIn("Obelisk (1)", listed_text)
            self.assertIn("Obelisk - Surface (1/1) \\u00b7 Visited", listed_text)
            self.assertNotIn("Arena", listed_text)
            town_app = create_app(directory, graphics=False, player="Red")
            town_list = town_app.server.test_client().post("/_dash-update-component", json={
                "output": "map_pin_list.children",
                "outputs": {"id": "map_pin_list", "property": "children"},
                "inputs": [{"id": "map_player", "property": "data", "value": "Red"},
                           {"id": "map_revision", "property": "data", "value": 0},
                           {"id": "map_data_revision", "property": "data", "value": 0},
                           {"id": "map_stat_hero", "property": "value", "value": None},
                           {"id": "map_stat_revision", "property": "data", "value": 0},
                           {"id": "map_favourites_revision", "property": "data", "value": 0}],
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
                           {"id": "map_favourites_revision", "property": "data", "value": 0},
                           {"id": "map_hidden_categories", "property": "data", "value": []},
                           {"id": "map_stat_hero", "property": "value", "value": None},
                           {"id": "map_stat_revision", "property": "data", "value": 0},
                           {"id": "map_hide_visited_stats", "property": "value", "value": []},
                           {"id": "map_stat_interest_enabled", "property": "data", "value": False}],
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
