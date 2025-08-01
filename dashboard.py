import argparse
import json
import logging
import os

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import dash_table, dcc, html
from dash.dependencies import Input, Output

logger = logging.getLogger(__package__)



def load_combined_data(directory):
    combined_path = os.path.join(directory, "combined_player_data.json")
    if not os.path.isfile(combined_path):
        raise FileNotFoundError(f"combined_player_data.json not found in {directory}")

    with open(combined_path, "r") as f:
        data = json.load(f)
    return data

def parse_data(data):
    hero_rows = []
    player_rows = []
    game_info = None

    for entry in data:
        filename = entry.get("filename", "")
        day = parse_day_from_filename(filename)

        # If game_info is not defined then we are parsing first savefile
        # This info should be extracted only once
        if not game_info:
            game_info = entry.get("game_info", {})


        players = entry.get("players", {})
        for player_color, player_data in players.items():
            # Hero data
            heroes = player_data.get("heroes", {})
            if isinstance(heroes, list):
                for hero_data in heroes:
                    hero_name = hero_data.get("name", "Unknown")
                    hero = {
                        "day": day,
                        "player_color": player_color.capitalize(),
                        "hero_name": hero_name,
                        "experience": hero_data.get("experience", 0),
                        "army_strength": hero_data.get("army_strength", 0),
                        "attack": hero_data.get("primary_skills", {}).get("attack", 0),
                        "defense": hero_data.get("primary_skills", {}).get("defense", 0),
                        "power": hero_data.get("primary_skills", {}).get("spell_power", 0),
                        "knowledge": hero_data.get("primary_skills", {}).get("knowledge", 0),
                        "has_dd": hero_data.get("has_dd", False),
                        "has_fly": hero_data.get("has_fly", False),
                        "has_tp": hero_data.get("has_tp", False),
                    }
                    if not all(isinstance(val, int) for val in [hero['attack'], hero["defense"],hero["power"],hero["knowledge"]]):
                        continue
                    hero_rows.append(hero)
            elif isinstance(heroes, dict):
                for hero_name, hero_data in heroes.items():
                    hero = {
                        "day": day,
                        "player_color": player_color.capitalize(),
                        "hero_name": hero_name,
                        "experience": hero_data.get("experience", 0),
                        "army_strength": hero_data.get("army_strength", 0),
                        "attack": hero_data.get("primary_skills", {}).get("attack", 0),
                        "defense": hero_data.get("primary_skills", {}).get("defense", 0),
                        "power": hero_data.get("primary_skills", {}).get("spell_power", 0),
                        "knowledge": hero_data.get("primary_skills", {}).get("knowledge", 0),
                        "has_dd": hero_data.get("has_dd", False),
                        "has_fly": hero_data.get("has_fly", False),
                        "has_tp": hero_data.get("has_tp", False),
                    }
                    if not all(isinstance(val, int) for val in [hero['attack'], hero["defense"],hero["power"],hero["knowledge"]]):
                        logger.debug(f"Detected hero {hero_name} with invalid skill value.")
                        continue
                    hero_rows.append(hero)

            # Player-level data
            player_rows.append({
                "day": day,
                "player_color": player_color.capitalize(),
                "gold": player_data.get("resources", {}).get("gold", 0),
                "wood": player_data.get("resources", {}).get("wood", 0),
                "ore": player_data.get("resources", {}).get("ore", 0),
                "mercury": player_data.get("resources", {}).get("mercury", 0),
                "sulfur": player_data.get("resources", {}).get("sulfur", 0),
                "crystal": player_data.get("resources", {}).get("crystals", 0),
                "gems": player_data.get("resources", {}).get("gems", 0),
                "town_count": player_data.get("town_count", 0),
                "visited_utopias": player_data.get("visited_utopias", 0),
                "total_strength": player_data.get("total_strength", 0)
            })

    df_heroes = pd.DataFrame(hero_rows)
    df_players = pd.DataFrame(player_rows)

    return df_heroes, df_players, game_info


def parse_day_from_filename(filename):
    try:
        basename = os.path.basename(filename).upper()
        if basename.endswith((".GM1", ".GM2", ".GM3", ".GM4", ".GM5", ".GM6", ".GM7", ".GM8")):
            name = basename.split(".")[0]  # e.g., "123"
            if len(name) == 3 and name.isdigit():
                month = int(name[0])
                week = int(name[1])
                day = int(name[2])
                absolute_day = (month - 1) * 28 + (week - 1) * 7 + day
                return absolute_day
    except Exception:
        pass
    return None


def run_dashboard(df_heroes, df_players, game_info, port):
    app = dash.Dash(__name__)
    server = app.server

    player_options = sorted(df_heroes["player_color"].dropna().unique())
    hero_options = sorted(df_heroes["hero_name"].dropna().unique())
    metric_options = ["experience", "army_strength", "attack", "defense", "power", "knowledge"]
    player_metric_options = ["gold", "wood", "ore", "mercury", "sulfur", "crystal", "gems", "town_count", "total_strength"]

    PLAYER_COLORS = {
        "Red": "#FF0000",
        "Blue": "#0000FF",
        "Tan": "#D2B48C",
        "Green": "#00A000",
        "Orange": "#FFA500",
        "Purple": "#800080",
        "Teal": "#008080",
        "Pink": "#FF69B4",
        "None": "#808080",   # Grey for 'None' player
    }

    PLAYER_ORDER = ["Red", "Blue", "Tan", "Green", "Orange", "Purple", "Teal", "Pink", "None"]

    app.layout = html.Div([
        html.H1("Heroes 3 Savegame Analyzer Dashboard"),
        html.Div([
            html.H3("Game Info"),
            dash_table.DataTable(
                columns=[{"name": "Key", "id": "Key"}, {"name": "Value", "id": "Value"}],
                data=[{"Key": k, "Value": str(v)} for k, v in game_info.items()],
                style_table={'width': '50%'},
                style_cell={'textAlign': 'left'},
            )
        ], style={"marginBottom": "30px"}),

        html.Div([
            html.H2("Hero Metrics Over Time"),

            html.Label("Select Players"),
            dcc.Dropdown(
                id="player_selector",
                options=[{"label": p, "value": p} for p in player_options],
                value=player_options,
                multi=True
            ),

            html.Label("Select Heroes"),
            dcc.Dropdown(
                id="hero_selector",
                options=[{"label": h, "value": h} for h in hero_options],
                value=hero_options,
                multi=True
            ),

            html.Label("Select Hero Metrics"),
            dcc.Dropdown(
                id="metric_selector",
                options=[{"label": m.capitalize(), "value": m} for m in metric_options],
                value=["experience"],
                multi=True
            ),
        ], style={"width": "50%", "marginBottom": "30px"}),

        dcc.Graph(id="line_chart"),

        html.Hr(),

        html.Div([
            html.H2("Player Metrics Over Time"),

            html.Label("Select Player Metrics"),
            dcc.Dropdown(
                id="player_metric_selector",
                options=[{"label": m.capitalize(), "value": m} for m in player_metric_options],
                value=["town_count", "gold"],
                multi=True
            ),
        ], style={"width": "50%", "marginBottom": "30px"}),

        dcc.Graph(id="player_chart"),

        html.H2("Town Ownership Distribution"),

        html.Label("Select Day"),
        dcc.Slider(
            id="day_slider",
            min=df_players["day"].min(),
            max=df_players["day"].max(),
            step=1,
            value=df_players["day"].max(),
            marks={int(day): str(int(day)) for day in sorted(df_players["day"].unique())},
            tooltip={"placement": "bottom", "always_visible": True}
        ),

        dcc.Graph(id="town_pie_chart"),

        html.H2("Utopia Visitation"),
        dcc.Graph(id="utopia_pie_chart"),

        html.H2("Spell Availability Over Time"),

        html.Label("Select Spell:"),
        dcc.Dropdown(
            id="spell_selector",
            options=[
                {"label": "Dimension Door", "value": "has_dd"},
                {"label": "Fly", "value": "has_fly"},
                {"label": "Town Portal", "value": "has_tp"}
            ],
            value="has_dd",  # Default to Dimension Door
            clearable=False
        ),

        dcc.Graph(id="spell_chart"),

        html.H2("Timeline Heatmap"),

        html.Label("Select Heatmap Metric"),
        dcc.Dropdown(
            id="heatmap_metric_selector",
            options=[{"label": m.capitalize(), "value": m} for m in player_metric_options],
            value="town_count",
            clearable=False
        ),

        dcc.Graph(id="heatmap_chart"),

    ])


    # Update hero selector based on player selection
    @app.callback(
        Output("hero_selector", "options"),
        Output("hero_selector", "value"),
        Input("player_selector", "value")
    )
    def update_hero_selector(selected_players):
        filtered = df_heroes[df_heroes["player_color"].isin(selected_players)]
        heroes = sorted(filtered["hero_name"].dropna().unique())
        options = [{"label": h, "value": h} for h in heroes]
        return options, heroes

    # Update line chart for heroes
    @app.callback(
        Output("line_chart", "figure"),
        Input("player_selector", "value"),
        Input("hero_selector", "value"),
        Input("metric_selector", "value")
    )
    def update_chart(selected_players, selected_heroes, selected_metrics):
        if not selected_players or not selected_heroes or not selected_metrics:
            return go.Figure()

        filtered = df_heroes[
            (df_heroes["player_color"].isin(selected_players)) &
            (df_heroes["hero_name"].isin(selected_heroes))
        ]

        fig = go.Figure()

        for metric in selected_metrics:
            for (player, hero), group in filtered.groupby(["player_color", "hero_name"]):
                fig.add_trace(go.Scatter(
                    x=group["day"],
                    y=group[metric],
                    mode="lines+markers",
                    name=f"{hero} ({player}) - {metric.capitalize()}"
                ))

        fig.update_layout(
            title="Hero Progress Over Time",
            xaxis_title="Game Day",
            yaxis_title="Value",
            hovermode="x unified"
        )
        return fig

    # Player-level chart
    @app.callback(
        Output("player_chart", "figure"),
        Input("player_selector", "value"),
        Input("player_metric_selector", "value")
    )
    def update_player_chart(selected_players, selected_metrics):
        if not selected_players or not selected_metrics:
            return go.Figure()
    
        filtered = df_players[df_players["player_color"].isin(selected_players)]
        fig = go.Figure()
    
        for metric in selected_metrics:
            for player in PLAYER_ORDER:
                if player not in selected_players:
                    continue
                group = filtered[filtered["player_color"] == player]
                if group.empty:
                    continue
                
                color = PLAYER_COLORS.get(player, "#000000")  # fallback to black if not defined
    
                fig.add_trace(go.Scatter(
                    x=group["day"],
                    y=group[metric],
                    mode="lines+markers",
                    name=f"{player} - {metric.capitalize()}",
                    line=dict(color=color),
                    marker=dict(color=color)
                ))
    
        fig.update_layout(
            title="Player Metrics Over Time",
            xaxis_title="Game Day",
            yaxis_title="Value",
            hovermode="x unified",
            legend=dict(traceorder="normal")  # Keep the order in which traces are added
        )
        return fig

    # Pie chart for town ownership (latest day)
    @app.callback(
        Output("town_pie_chart", "figure"),
        Input("player_selector", "value"),
        Input("day_slider", "value")
    )
    def update_town_pie(selected_players, selected_day):
        if df_players.empty or selected_day is None:
            return go.Figure()

        current = df_players[df_players["day"] == selected_day]
        filtered = current[current["player_color"].isin(selected_players)]

        if filtered.empty:
            return go.Figure()

        fig = px.pie(
            filtered,
            names="player_color",
            values="town_count",
            title=f"Town Ownership on Day {selected_day}",
            color="player_color",
            color_discrete_map=PLAYER_COLORS
        )

        return fig
    
    # Spell availability
    @app.callback(
        Output("spell_chart", "figure"),
        Input("player_selector", "value"),
        Input("spell_selector", "value")
    )
    def update_spell_chart(selected_players, selected_spell):
        if not selected_players or not selected_spell:
            return go.Figure()

        spell_names = {
            "has_dd": "Dimension Door",
            "has_fly": "Fly",
            "has_tp": "Town Portal"
        }

        df = df_heroes.copy()

        # Prepare data
        records = []
        for day in sorted(df["day"].dropna().unique()):
            daily = df[df["day"] <= day]
            for player in selected_players:
                player_daily = daily[daily["player_color"] == player]
                has_spell = player_daily[selected_spell].any()
                records.append({
                    "day": day,
                    "player_color": player,
                    "available": int(has_spell)
                })

        df_spells = pd.DataFrame(records)

        # Plot
        fig = go.Figure()

        for player in selected_players:
            group = df_spells[df_spells["player_color"] == player]
            if group.empty:
                continue

            color = PLAYER_COLORS.get(player, "#000000")

            fig.add_trace(go.Scatter(
                x=group["day"],
                y=group["available"],
                mode="lines+markers",
                name=player,
                line=dict(shape="hv", color=color),
                marker=dict(color=color)
            ))

        fig.update_layout(
            title=f"{spell_names[selected_spell]} Availability Over Time",
            xaxis_title="Game Day",
            yaxis=dict(
                title="Availability",
                tickmode="array",
                tickvals=[0, 1],
                ticktext=["Not Available", "Available"]
            ),
            hovermode="x unified"
        )

        return fig

    @app.callback(
        Output("heatmap_chart", "figure"),
        Input("player_selector", "value"),
        Input("heatmap_metric_selector", "value")
    )
    def update_heatmap(selected_players, selected_metric):
        if not selected_players or not selected_metric:
            return go.Figure()

        # Filter data
        df_filtered = df_players[df_players["player_color"].isin(selected_players)]

        # Pivot data to get a matrix: player_color x day
        pivot = df_filtered.pivot_table(
            index="player_color",
            columns="day",
            values=selected_metric,
            fill_value=0
        ).reindex(PLAYER_ORDER).dropna(how="all")  # Keep color order

        # Create heatmap
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale="YlGnBu",
            hoverongaps=False,
            colorbar=dict(title=selected_metric.capitalize())
        ))

        fig.update_layout(
            title=f"{selected_metric.capitalize()} Timeline Heatmap",
            xaxis_title="Game Day",
            yaxis_title="Player",
            yaxis=dict(autorange="reversed")  # Top = Red
        )

        return fig

    @app.callback(
        Output("utopia_pie_chart", "figure"),
        Input("player_selector", "value"),
        Input("day_slider", "value")
    )
    def update_utopia_pie(selected_players, selected_day):
        if df_players.empty or selected_day is None:
            return go.Figure()
    
        # Use the data for the selected day
        current = df_players[df_players["day"] == selected_day]
    
        # Exclude 'None' player and filter selected players
        filtered = current[
            (current["player_color"] != "None") &
            (current["player_color"].isin(selected_players))
        ]
    
        if filtered.empty:
            return go.Figure()
    
        # Sum visited utopias per player
        utopia_counts = filtered[["player_color", "visited_utopias"]].groupby("player_color").sum().reset_index()
    
        # Calculate percentages
        total_utopias = game_info.get("total_utopias", 0)
        if total_utopias == 0:
            total_utopias = utopia_counts["visited_utopias"].sum()  # fallback to avoid divide-by-zero
    
        utopia_counts["percentage"] = 100 * utopia_counts["visited_utopias"] / total_utopias
        utopia_counts["label"] = utopia_counts.apply(
            lambda row: f"{row['player_color']} ({row['visited_utopias']}/{total_utopias}, {row['percentage']:.1f}%)",
            axis=1
        )
    
        # Build pie chart
        fig = px.pie(
            utopia_counts,
            names="label",
            values="visited_utopias",
            title=f"Utopias Visited by Day {selected_day} (Total: {total_utopias})",
            color="player_color",
            color_discrete_map=PLAYER_COLORS
        )
    
        return fig



    app.run(debug=True, port=port)


def main():
    parser = argparse.ArgumentParser(description="Heroes 3 Savegame Dashboard")
    parser.add_argument(
        "input_dir",
        help="Directory containing combined_player_data.json"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port to run the dashboard (default: 8050)"
    )
    args = parser.parse_args()

    data = load_combined_data(args.input_dir)
    df_heroes, df_players, game_info = parse_data(data)

    run_dashboard(df_heroes, df_players, game_info, args.port)


if __name__ == "__main__":
    main()
