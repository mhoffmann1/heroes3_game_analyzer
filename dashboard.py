import os
import json
import argparse
import pandas as pd
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px


def load_combined_data(directory):
    combined_path = os.path.join(directory, "combined_player_data.json")
    if not os.path.isfile(combined_path):
        raise FileNotFoundError(f"combined_player_data.json not found in {directory}")

    with open(combined_path, "r") as f:
        data = json.load(f)
    return data


def parse_data(data):
    rows = []
    game_info = None

    for entry in data:
        filename = entry.get("filename", "")
        day = parse_day_from_filename(filename)

        if not game_info:
            game_info = entry.get("game_info", {})

        players = entry.get("players", {})
        for player_color, player_data in players.items():
            heroes = player_data.get("heroes", {})
            if isinstance(heroes, list):
                for hero_data in heroes:
                    hero_name = hero_data.get("name", "Unknown")
                    row = {
                        "day": day,
                        "player_color": player_color.capitalize(),
                        "hero_name": hero_name,
                        "experience": hero_data.get("experience", 0),
                        "army_strength": hero_data.get("army_strength", 0),
                        "attack": hero_data.get("primary_skills", {}).get("attack", 0),
                        "defense": hero_data.get("primary_skills", {}).get("defense", 0),
                        "power": hero_data.get("primary_skills", {}).get("spell_power", 0),
                        "knowledge": hero_data.get("primary_skills", {}).get("knowledge", 0)
                    }
                    rows.append(row)
            elif isinstance(heroes, dict):
                for hero_name, hero_data in heroes.items():
                    row = {
                        "day": day,
                        "player_color": player_color.capitalize(),
                        "hero_name": hero_name,
                        "experience": hero_data.get("experience", 0),
                        "army_strength": hero_data.get("army_strength", 0),
                        "attack": hero_data.get("primary_skills", {}).get("attack", 0),
                        "defense": hero_data.get("primary_skills", {}).get("defense", 0),
                        "power": hero_data.get("primary_skills", {}).get("spell_power", 0),
                        "knowledge": hero_data.get("primary_skills", {}).get("knowledge", 0)
                    }
                    rows.append(row)
    df = pd.DataFrame(rows)
    return df, game_info


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


def run_dashboard(df, game_info, port):
    app = dash.Dash(__name__)
    server = app.server

    player_options = sorted(df["player_color"].dropna().unique())
    hero_options = sorted(df["hero_name"].dropna().unique())
    metric_options = ["experience", "army_strength", "attack", "defense", "power", "knowledge"]

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

            html.Label("Select Metrics"),
            dcc.Dropdown(
                id="metric_selector",
                options=[{"label": m.capitalize(), "value": m} for m in metric_options],
                value=["experience"],
                multi=True
            ),
        ], style={"width": "50%", "marginBottom": "30px"}),

        dcc.Graph(id="line_chart")
    ])

    @app.callback(
        Output("hero_selector", "options"),
        Output("hero_selector", "value"),
        Input("player_selector", "value")
    )
    def update_hero_selector(selected_players):
        filtered = df[df["player_color"].isin(selected_players)]
        heroes = sorted(filtered["hero_name"].dropna().unique())
        options = [{"label": h, "value": h} for h in heroes]
        return options, heroes

    @app.callback(
        Output("line_chart", "figure"),
        Input("player_selector", "value"),
        Input("hero_selector", "value"),
        Input("metric_selector", "value")
    )
    def update_chart(selected_players, selected_heroes, selected_metrics):
        if not selected_players or not selected_heroes or not selected_metrics:
            return px.line(title="No data selected")

        filtered = df[
            (df["player_color"].isin(selected_players)) &
            (df["hero_name"].isin(selected_heroes))
        ]

        fig = px.line()

        for metric in selected_metrics:
            for (player, hero), group in filtered.groupby(["player_color", "hero_name"]):
                fig.add_scatter(
                    x=group["day"],
                    y=group[metric],
                    mode="lines+markers",
                    name=f"{hero} ({player}) - {metric.capitalize()}"
                )

        fig.update_layout(
            title="Hero Progress Over Time",
            xaxis_title="Game Day",
            yaxis_title="Value",
            hovermode="x unified"
        )
        return fig

    app.run(debug=True, port=port)


def main():
    parser = argparse.ArgumentParser(description="Heroes 3 Savegame Dashboard")
    parser.add_argument(
        "input_dir",
        help="Directory containing combined_data.json"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port to run the dashboard (default: 8050)"
    )
    args = parser.parse_args()

    data = load_combined_data(args.input_dir)
    df, game_info = parse_data(data)

    run_dashboard(df, game_info, args.port)


if __name__ == "__main__":
    main()
