"""Standalone Map Helper for an already processed Heroes III game."""

import argparse
import hashlib
import json
import logging
import threading
from pathlib import Path

import dash
import pandas as pd
from dash import html

from map_helper import register_map_helper
from game_graphics import load_terrain_renderer


logger = logging.getLogger(__name__)


def day_from_save_name(filename):
    name = Path(filename).name.upper()
    if len(name) != 7 or name[3:6] != ".GM" or name[6] not in "12345678":
        return None
    date = name[:3]
    if not date.isdigit():
        return None
    month, week, day = map(int, date)
    if month < 1 or not 1 <= week <= 4 or not 1 <= day <= 7:
        return None
    return (month - 1) * 28 + (week - 1) * 7 + day


def load_latest_players(directory):
    """Read only the rows needed for the standalone map view."""
    source = Path(directory) / "combined_player_data.json"
    with source.open(encoding="utf-8") as handle:
        entries = json.load(handle)
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"No processed saves in {source}")
    game_info = next((entry.get("game_info") for entry in entries
                      if isinstance(entry, dict) and entry.get("game_info")), None)
    if not game_info or not game_info.get("map_size"):
        raise ValueError(f"Map dimensions are missing from {source}")
    rows = {}
    for entry in entries:
        day = day_from_save_name(entry.get("filename", ""))
        if day is None:
            continue
        for color, player in entry.get("players", {}).items():
            row = {"day": day, "player_color": color.capitalize(),
                   "fog_of_war": player.get("fog_of_war", ""),
                   "town_summary": [
                       {"town_name": town.get("name"), "coords": town.get("coords")}
                       for town in player.get("towns") or []
                   ]}
            previous = rows.get(color)
            if previous is None or day >= previous["day"]:
                rows[color] = row
    if not rows:
        raise ValueError(f"No player exploration data in {source}")
    return pd.DataFrame(rows.values()), game_info


class ProcessedGameData:
    """Reload complete processed snapshots when their source file changes."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.source = self.directory / "combined_player_data.json"
        self.lock = threading.Lock()
        before = self._signature()
        self.players, self.game_info = load_latest_players(self.directory)
        self.signature = self._signature()
        if before != self.signature:
            raise ValueError("Processed data changed during startup; please try again")
        self.revision = 0

    def _signature(self):
        stat = self.source.stat()
        return stat.st_mtime_ns, stat.st_size

    def get(self):
        with self.lock:
            try:
                signature = self._signature()
                if signature != self.signature:
                    players, game_info = load_latest_players(self.directory)
                    if self._signature() != signature:
                        raise ValueError("Processed data changed during reload")
                    if (int(game_info["map_size"]) != int(self.game_info["map_size"])
                            or int(game_info.get("levels") or 1) != int(self.game_info.get("levels") or 1)):
                        raise ValueError("Processed map dimensions changed; restart the Map Helper")
                    self.players = players
                    self.signature = signature
                    self.revision += 1
            except (OSError, ValueError, TypeError, KeyError) as exc:
                # A processor may be halfway through writing the JSON. Keep
                # the last complete snapshot and retry on the next poll.
                logger.warning("Map data refresh deferred: %s", exc)
            return self.players, self.revision


def create_app(directory, *, player, game_dir=None, graphics=True):
    directory = Path(directory).resolve()
    data = ProcessedGameData(directory)
    players, game_info = data.players, data.game_info
    renderer = None
    graphics_info = "Terrain graphics disabled."
    if graphics:
        renderer, source = load_terrain_renderer(directory, int(game_info["map_size"]),
                                                 int(game_info.get("levels") or 1), game_dir)
        graphics_info = (f"Terrain graphics: {Path(source).name}" if renderer else
                         f"Exploration grid: {source}")

    image_cache = {}
    cache_lock = threading.Lock()

    def graphics_provider(mask, level, player):
        if renderer is None:
            return None
        key = (level, hashlib.blake2b(mask[level].tobytes(), digest_size=16).digest())
        with cache_lock:
            if key not in image_cache:
                image_cache[key] = renderer.render_data_url(mask, level)
                if len(image_cache) > 4:
                    image_cache.pop(next(iter(image_cache)))
            return image_cache[key]

    app = dash.Dash(__name__, title="Heroes III Map Helper")
    app.layout = html.Div([
        html.Div([
            html.H1("Heroes III Map Helper", style={"marginBottom": "4px"}),
            html.Div(directory.name, style={"opacity": 0.8}),
            html.Div(graphics_info, style={"opacity": 0.8, "fontSize": "14px", "marginTop": "5px"}),
        ], style={"padding": "18px 24px", "background": "#342b21", "color": "#f6e9c9"}),
        html.Main(register_map_helper(app, players, game_info, directory,
                                      graphics_provider=graphics_provider,
                                      transport_provider=(lambda: renderer.transports) if renderer else None,
                                      bonus_provider=(lambda: renderer.bonuses) if renderer else None,
                                      utopia_provider=(lambda: renderer.utopias) if renderer else None,
                                      default_player=player, data_provider=data.get,
                                      refresh_interval_ms=5000, lock_player=True),
                  style={"width": "100%", "boxSizing": "border-box", "margin": "0 auto",
                         "padding": "18px 24px"}),
    ], style={"minHeight": "100vh", "background": "#e9e0cd", "color": "#30271d"})
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", help="Processed game directory containing combined_player_data.json")
    parser.add_argument("--port", type=int, default=8051, help="Port (default: 8051)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--game-dir", help="Heroes III installation directory containing Data/H3sprite.lod")
    parser.add_argument("--player", required=True,
                        help="Player shown throughout this session, for example Blue (case-insensitive)")
    parser.add_argument("--no-graphics", action="store_true", help="Use the exploration grid only")
    args = parser.parse_args()
    try:
        app = create_app(args.input_dir, game_dir=args.game_dir,
                         graphics=not args.no_graphics, player=args.player)
    except ValueError as exc:
        parser.error(str(exc))
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
