"""Exploration-safe map annotations for the standalone Map Helper."""

import json
import os
import tempfile
import threading
import uuid
from html import escape
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update


CATEGORY_COLORS = {
    "Portal": "#8e44ad",
    "Artifact": "#e0a316",
    "Joining units": "#2b9d74",
    "Stat increase": "#b3426a",
    "Dragon Utopia": "#9a5635",
    "Morale": "#47733b",
    "Luck": "#16a5a1",
    "Morale and luck": "#6185b9",
    "Town": "#cf5b3f",
    "Underground gate": "#b67e51",
    "Resource": "#368bcc",
    "Other": "#747b84",
}
CATEGORIES = [category for category in CATEGORY_COLORS
              if category not in ("Portal", "Dragon Utopia", "Morale", "Luck", "Morale and luck",
                                  "Town", "Underground gate")]
_PIN_LOCK = threading.Lock()


def latest_fog(df_players, player, map_size, levels):
    """Return the latest valid exploration mask for this player, or None."""
    rows = df_players[df_players["player_color"] == player]
    if rows.empty:
        return None, None
    # Preserve input order when several saves have the same in-game day.
    row = rows[rows["day"] == rows["day"].max()].iloc[-1]
    fog = row.get("fog_of_war")
    count = map_size * map_size * levels
    if not isinstance(fog, str) or len(fog) != count or set(fog) - {"0", "1"}:
        return int(row["day"]), None
    return int(row["day"]), np.fromiter((c == "1" for c in fog), bool).reshape(levels, map_size, map_size)


def is_explored(mask, level, x, y):
    return (mask is not None and 0 <= level < mask.shape[0]
            and 0 <= y < mask.shape[1] and 0 <= x < mask.shape[2]
            and bool(mask[level, y, x]))


def visible_towns(df_players, player, map_size, levels):
    """Use the latest save-day town snapshot, filtered by this player's fog."""
    day, mask = latest_fog(df_players, player, map_size, levels)
    if mask is None or "town_summary" not in df_players:
        return []
    rows = df_players[df_players["day"] == day]
    # A day may have several saves. Keep the last town list for each owner.
    rows = rows.drop_duplicates("player_color", keep="last")
    result = {}
    for _, row in rows.iterrows():
        towns = row.get("town_summary")
        if not isinstance(towns, list):
            continue
        for town in towns:
            coords = town.get("coords")
            if not isinstance(coords, (list, tuple)) or len(coords) != 3:
                continue
            try:
                x, y = int(coords[0]), int(coords[1])
                level = 0 if coords[2] in (0, "Surface") else 1 if coords[2] in (1, "Underground") else -1
            except (ValueError, TypeError):
                continue
            if is_explored(mask, level, x, y):
                result[(level, x, y)] = {"level": level, "x": x, "y": y,
                                         "name": str(town.get("town_name") or town.get("name") or "Town")}
    return list(result.values())


def _visible_map_object_pins(objects, mask, player):
    """Generate player-specific read-only pins from the matched map."""
    return [{"id": f"auto:{item['level']}:{item['x']}:{item['y']}:{item['category']}",
             "player": player, "level": item["level"], "x": item["x"], "y": item["y"],
             "title": item["title"], "category": item["category"],
             "notes": item.get("notes", "Automatic marker"), "automatic": True}
            for item in objects
            if is_explored(mask, item["level"], item["x"], item["y"])]


def visible_transport_pins(transports, mask, player):
    return _visible_map_object_pins(transports, mask, player)


def visible_bonus_pins(bonuses, mask, player):
    """Expose bonus sites only after this player has explored their tile."""
    return _visible_map_object_pins(bonuses, mask, player)


def visible_utopia_pins(utopias, mask, player):
    """Expose Dragon Utopias only after this player has explored their tile."""
    return _visible_map_object_pins(utopias, mask, player)


def visible_town_pins(towns, player):
    """Expose visible town markers in the read-only Town pin section."""
    return [{"id": f"auto:town:{town['level']}:{town['x']}:{town['y']}",
             "player": player, "level": town["level"], "x": town["x"], "y": town["y"],
             "title": town["name"], "category": "Town", "notes": "Automatic marker",
             "automatic": True}
            for town in towns]


def read_pins(path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def write_pins(path, pins):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".map_pins_", suffix=".tmp", delete=False) as output:
            temporary = output.name
            json.dump(pins, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def save_pin(pins, player, level, x, y, title, category, notes,
             mask, pin_id=None):
    """Validate and upsert a pin; never write to a covered tile."""
    if not is_explored(mask, level, x, y):
        raise ValueError("Choose a tile explored by this player.")
    title = (title or "").strip()[:100]
    if not title:
        raise ValueError("Enter a pin title.")
    if category not in CATEGORIES:
        raise ValueError("Choose a valid category.")
    if pin_id:
        old = next((p for p in pins if p.get("id") == pin_id and p.get("player") == player), None)
        if old is None:
            raise ValueError("Pin no longer exists for this player.")
    else:
        pin_id = uuid.uuid4().hex
    pin = {"id": pin_id, "player": player, "level": level, "x": x, "y": y,
           "title": title, "category": category,
           "notes": (notes or "").strip()[:2000]}
    return [p for p in pins if p.get("id") != pin_id] + [pin]


def grouped_pin_list(pins):
    """Build closed-by-default, clickable sections for visible pins."""
    sections = []
    # Keep older manually saved Town pins accessible for review and deletion.
    for category in CATEGORY_COLORS:
        group = sorted((p for p in pins if p.get("category") == category),
                       key=lambda p: (p["level"], p["title"].casefold()))
        if not group:
            continue
        color = CATEGORY_COLORS[category]
        sections.append(html.Details([
            html.Summary([
                html.Span("● ", style={"color": color}),
                f"{category} ({len(group)})",
            ], style={"fontWeight": "bold", "cursor": "pointer", "padding": "8px 4px"}),
            html.Div([
                html.Button(
                    f"{pin['title']} - "
                    f"{'Surface' if pin['level'] == 0 else 'Underground'} "
                    f"({pin['x']}/{pin['y']})",
                    id={"type": "map_pin_button", "pin_id": pin["id"]},
                    n_clicks=0,
                    style={"display": "block", "width": "100%", "textAlign": "left",
                           "border": "0", "borderLeft": f"4px solid {color}",
                           "background": "#fffaf0", "padding": "7px 9px",
                           "marginBottom": "4px", "cursor": "pointer"},
                ) for pin in group
            ]),
        ], open=False, style={"marginBottom": "4px"}))
    return sections or [html.Div("No pins on explored tiles for this player.")]


def map_figure(mask, day, player, level, pins, selected=None, background=None, towns=None):
    fig = go.Figure()
    if mask is None:
        fig.update_layout(title="No valid exploration data for this player")
        return fig
    size = mask.shape[1]
    # A categorical heatmap renders each tile without smoothing. Covered tiles stay black.
    fig.add_trace(go.Heatmap(
        z=mask[level].astype(int), x=list(range(size)), y=list(range(size)),
        zmin=0, zmax=1, colorscale=(
            [[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]]
            if background else [[0, "#15171d"], [0.499, "#15171d"],
                                [0.5, "#c7b78c"], [1, "#c7b78c"]]),
        showscale=False, hovertemplate="(%{x}, %{y})<extra></extra>",
    ))
    if background:
        fig.add_layout_image(dict(source=background, xref="x", yref="y",
                                  x=-0.5, y=-0.5, sizex=size, sizey=size,
                                  xanchor="left", yanchor="top", sizing="stretch",
                                  layer="below"))
    for town in towns or []:
        if town.get("level") != level or not is_explored(mask, level, town.get("x", -1), town.get("y", -1)):
            continue
        x, y = town["x"], town["y"]
        name = escape(str(town.get("name") or "Town"))
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers", name="Town",
            marker={"size": 16, "symbol": "square", "color": "#f4d36c",
                    "line": {"color": "#3b2b17", "width": 2}},
            hovertemplate=f"{name}<br>({x}, {y})<extra></extra>",
        ))
        fig.add_annotation(x=x, y=y, text=name, showarrow=False, yshift=20,
                           font={"size": 12, "color": "#fff8e2"},
                           bgcolor="rgba(40, 30, 20, 0.86)", bordercolor="#d8bd78",
                           borderwidth=1, borderpad=2)
    visible = [p for p in pins if p.get("player") == player and p.get("level") == level
               and not (p.get("automatic") and p.get("category") == "Town")
               and is_explored(mask, level, p.get("x", -1), p.get("y", -1))]
    if visible:
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in visible], y=[p["y"] for p in visible], mode="markers",
            marker={"size": 17, "color": [CATEGORY_COLORS.get(p.get("category"), CATEGORY_COLORS["Other"])
                                           for p in visible],
                    "symbol": "diamond", "line": {"color": "#222", "width": 1}},
            text=[f'{p["category"]}: {p["title"]}' for p in visible],
            hovertemplate="%{text}<br>(%{x}, %{y})<extra></extra>",
        ))
    focus = selected and selected.get("focus") and selected.get("level") == level
    width = min(24, size / 2)
    if focus:
        x_range = [selected["x"] - width, selected["x"] + width]
        y_range = [selected["y"] + width, selected["y"] - width]
    else:
        # Start closer to the explored area while keeping a useful map context.
        explored_y, explored_x = np.nonzero(mask[level])
        span = max(1, size * 0.55)
        radius = (span - 1) / 2
        center_x = (explored_x.min() + explored_x.max()) / 2 if len(explored_x) else (size - 1) / 2
        center_y = (explored_y.min() + explored_y.max()) / 2 if len(explored_y) else (size - 1) / 2
        center_x = min(max(center_x, radius), size - 1 - radius)
        center_y = min(max(center_y, radius), size - 1 - radius)
        x_range = [center_x - span / 2, center_x + span / 2]
        y_range = [center_y + span / 2, center_y - span / 2]
    fig.update_layout(
        title=f"{player} · Day {day} · {'Surface' if level == 0 else 'Underground'}",
        xaxis={"range": x_range, "constrain": "range", "showgrid": False,
               "title": "X", "zeroline": False},
        yaxis={"range": y_range, "scaleanchor": "x", "showgrid": False,
               "title": "Y", "zeroline": False},
        dragmode="pan", uirevision=f"{player}:{level}:{selected.get('id') if focus else ''}",
        margin={"l": 45, "r": 15, "t": 50, "b": 45},
        paper_bgcolor="#f5f0e3", plot_bgcolor="#15171d", showlegend=False,
    )
    return fig


def register_map_helper(app, df_players, game_info, input_dir, graphics_provider=None,
                        default_player=None, data_provider=None, refresh_interval_ms=None,
                        lock_player=False, transport_provider=None, bonus_provider=None,
                        utopia_provider=None):
    size = int(game_info.get("map_size") or 0)
    levels = int(game_info.get("levels") or 1)
    path = Path(input_dir) / "map_pins.json"

    def current_data():
        return data_provider() if data_provider else (df_players, 0)

    def available_players(rows):
        return [p for p in rows["player_color"].dropna().unique()
                if p != "None" and latest_fog(rows, p, size, levels)[1] is not None]

    players = available_players(df_players)
    if default_player is not None:
        selected_player = next((p for p in players if p.casefold() == default_player.casefold()), None)
        if selected_player is None:
            raise ValueError(f"Player {default_player!r} has no valid exploration data. "
                             f"Available players: {', '.join(players) or 'none'}.")
    else:
        selected_player = players[0] if players else None
    if lock_player and selected_player is None:
        raise ValueError("Choose a player with valid exploration data at startup.")
    player_property = "data" if lock_player else "value"

    def active_player(requested):
        return selected_player if lock_player else requested

    def current_pins(player, mask, towns=None):
        saved = [p for p in read_pins(path) if p.get("player") == player and
                 is_explored(mask, p.get("level", -1), p.get("x", -1), p.get("y", -1))]
        transports = transport_provider() if transport_provider else []
        bonuses = bonus_provider() if bonus_provider else []
        utopias = utopia_provider() if utopia_provider else []
        if towns is None:
            towns = visible_towns(current_data()[0], player, size, levels)
        return (saved + visible_transport_pins(transports, mask, player) +
                visible_bonus_pins(bonuses, mask, player) +
                visible_utopia_pins(utopias, mask, player) + visible_town_pins(towns, player))

    layout = html.Div([
        html.H2("Map Helper"),
        html.P("Latest processed turn. Click an explored tile to add a pin. Drag to pan; scroll to zoom."),
        dcc.Interval(id="map_poll", interval=refresh_interval_ms or 5000,
                     disabled=refresh_interval_ms is None),
        dcc.Store(id="map_data_revision", data=0),
        dcc.Store(id="map_selected"),
        dcc.Store(id="map_revision", data=0),
        dcc.Store(id="map_action"),
        dcc.Store(id="map_player", data=selected_player) if lock_player else None,
        html.Div([
            html.Div([
                html.Div([
                    html.Div([html.Label("Player"),
                              html.Div(selected_player, style={"fontWeight": "bold"})
                              if lock_player else dcc.Dropdown(
                                  id="map_player", options=players, value=selected_player,
                                  clearable=False)],
                             style={"minWidth": "150px", "flex": "1"}),
                    html.Div([html.Label("Level"), dcc.Dropdown(
                        id="map_level", options=[{"label": "Surface" if i == 0 else "Underground", "value": i}
                                                 for i in range(levels)], value=0, clearable=False)],
                        style={"minWidth": "150px", "flex": "1"}),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
                dcc.Graph(id="map_helper_graph", config={"scrollZoom": True, "displayModeBar": True},
                          style={"height": "min(82vh, 1000px)", "minHeight": "520px"}),
            ], style={"flex": "1 1 720px", "minWidth": "360px"}),
            html.Div([
                html.H3("Pins"),
                html.Div(id="map_pin_list", style={"maxHeight": "300px", "overflowY": "auto"}),
                html.Hr(),
                html.Div("Click an explored tile or choose a pin.", id="map_coordinates"),
                html.Label("Title"), dcc.Input(id="map_title", type="text", maxLength=100,
                                               style={"width": "100%"}),
                html.Label("Type"), dcc.Dropdown(id="map_category", options=CATEGORIES,
                                                value="Other", clearable=False),
                html.Label("Notes"), dcc.Textarea(id="map_notes", maxLength=2000,
                                                 style={"width": "100%", "minHeight": "90px"}),
                html.Div([
                    html.Button("Save pin", id="map_save", n_clicks=0),
                    html.Button("Delete pin", id="map_delete", n_clicks=0),
                ], style={"display": "flex", "gap": "8px", "marginTop": "12px"}),
                html.Div(id="map_message", role="status", style={"marginTop": "10px"}),
            ], style={"flex": "0 1 300px", "minWidth": "240px", "padding": "16px",
                      "background": "#f5f0e3", "borderRadius": "8px"}),
        ], style={"display": "flex", "gap": "18px", "flexWrap": "wrap"}),
    ])

    if lock_player:
        @app.callback(Output("map_data_revision", "data"),
                      Input("map_poll", "n_intervals"), State("map_data_revision", "data"))
        def poll_data(_ticks, revision):
            _rows, current_revision = current_data()
            return current_revision if current_revision != revision else no_update
    else:
        @app.callback(Output("map_data_revision", "data"), Output("map_player", "options"),
                      Input("map_poll", "n_intervals"), State("map_data_revision", "data"))
        def poll_data(_ticks, revision):
            rows, current_revision = current_data()
            if current_revision == revision:
                return no_update, no_update
            return current_revision, available_players(rows)

    @app.callback(Output("map_selected", "data"), Output("map_level", "value"),
                  Input("map_helper_graph", "clickData"),
                  Input({"type": "map_pin_button", "pin_id": ALL}, "n_clicks"),
                  Input("map_player", player_property), Input("map_action", "data"),
                  State("map_level", "value"))
    def select_pin(click, _pin_clicks, player, action, level):
        player = active_player(player)
        trigger = ctx.triggered_id
        if trigger == "map_action" and action:
            if action.get("id"):
                mask = latest_fog(current_data()[0], player, size, levels)[1]
                pin = next((p for p in current_pins(player, mask) if p.get("id") == action["id"]), None)
                if pin:
                    return {**pin, "focus": False}, pin["level"]
            return None, no_update
        if (isinstance(trigger, dict) and trigger.get("type") == "map_pin_button"
                and ctx.triggered[0].get("value")):
            pin_id = trigger.get("pin_id")
            day, mask = latest_fog(current_data()[0], player, size, levels)
            pin = next((p for p in current_pins(player, mask) if p.get("id") == pin_id), None)
            if pin:
                if is_explored(mask, pin["level"], pin["x"], pin["y"]):
                    return {**pin, "focus": True}, pin["level"]
        if trigger == "map_helper_graph" and click and click.get("points"):
            point = click["points"][0]
            x, y = round(point["x"]), round(point["y"])
            day, mask = latest_fog(current_data()[0], player, size, levels)
            if is_explored(mask, level, x, y):
                return {"player": player, "level": level, "x": x, "y": y}, no_update
        return None, no_update

    @app.callback(Output("map_coordinates", "children"), Output("map_title", "value"),
                  Output("map_category", "value"), Output("map_notes", "value"),
                  Output("map_title", "disabled"), Output("map_category", "disabled"),
                  Output("map_notes", "disabled"), Output("map_save", "disabled"),
                  Output("map_delete", "disabled"),
                  Input("map_selected", "data"))
    def show_selected(selected):
        if not selected:
            return "Click an explored tile or choose a pin.", "", "Other", "", False, False, False, False, False
        automatic = bool(selected.get("automatic"))
        label = (f"{'Surface' if selected['level'] == 0 else 'Underground'} "
                 f"({selected['x']}, {selected['y']})")
        if automatic:
            label += f" · Automatic {selected['category']} marker"
        category = selected.get("category")
        return (label, selected.get("title", ""),
                category if category in CATEGORIES else None if automatic else "Other",
                selected.get("notes", ""), automatic, automatic, automatic,
                automatic, automatic)

    @app.callback(Output("map_revision", "data"), Output("map_message", "children"),
                  Output("map_action", "data"),
                  Input("map_save", "n_clicks"), Input("map_delete", "n_clicks"),
                  State("map_selected", "data"), State("map_title", "value"),
                  State("map_category", "value"), State("map_notes", "value"),
                  State("map_player", player_property),
                  State("map_revision", "data"), prevent_initial_call=True)
    def change_pin(save_clicks, delete_clicks, selected, title, category, notes, player, revision):
        player = active_player(player)
        if not selected or selected.get("player") != player:
            return no_update, "Choose a tile or pin first.", no_update
        if selected.get("automatic"):
            return no_update, "Automatic markers cannot be edited or deleted.", no_update
        day, mask = latest_fog(current_data()[0], player, size, levels)
        with _PIN_LOCK:
            pins = read_pins(path)
            try:
                if ctx.triggered_id == "map_save":
                    pins = save_pin(pins, player, selected["level"], selected["x"],
                                    selected["y"], title, category, notes, mask,
                                    selected.get("id"))
                    message = "Pin saved."
                    action = {"id": pins[-1]["id"]}
                else:
                    pin_id = selected.get("id")
                    if not pin_id or not any(p.get("id") == pin_id and p.get("player") == player for p in pins):
                        return no_update, "Choose an existing pin to delete.", no_update
                    pins = [p for p in pins if p.get("id") != pin_id]
                    message = "Pin deleted."
                    action = {"id": None}
                write_pins(path, pins)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                return no_update, str(exc), no_update
        return (revision or 0) + 1, message, action

    @app.callback(Output("map_pin_list", "children"),
                  Input("map_player", player_property), Input("map_revision", "data"),
                  Input("map_data_revision", "data"))
    def pin_options(player, revision, data_revision):
        player = active_player(player)
        day, mask = latest_fog(current_data()[0], player, size, levels)
        return grouped_pin_list(current_pins(player, mask))

    @app.callback(Output("map_helper_graph", "figure"), Input("map_player", player_property),
                  Input("map_level", "value"), Input("map_revision", "data"),
                  Input("map_selected", "data"), Input("map_data_revision", "data"))
    def update_map(player, level, revision, selected, data_revision):
        player = active_player(player)
        if player is None or level is None:
            return go.Figure()
        rows, _ = current_data()
        day, mask = latest_fog(rows, player, size, levels)
        background = graphics_provider(mask, level, player) if graphics_provider and mask is not None else None
        towns = visible_towns(rows, player, size, levels)
        return map_figure(mask, day, player, level, current_pins(player, mask, towns),
                          selected, background, towns)

    return layout
