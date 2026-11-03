"""Exploration-safe map annotations for the standalone Map Helper."""

import json
import math
import os
import tempfile
import threading
import uuid
from collections import defaultdict
from html import escape
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update


CATEGORY_COLORS = {
    "Portal": "#AF4CF5",
    "Artifact": "#E6AD00",
    "Joining units": "#00BE8A",
    "Stat increase": "#F24589",
    "Mana replenishment": "#04C7DD",
    "Dragon Utopia": "#F04D45",
    "Obelisk": "#547A39",
    "Creature": "#4B91FF",
    "Favourites": "#FFD700",
    "Morale and Luck": "#826BFF",
    "Town": "#FF8C24",
    "Underground gate": "#637BFA",
    "Resource": "#1BAB9E",
    "Other": "#A0AAB5",
}
CATEGORIES = [category for category in CATEGORY_COLORS
              if category not in ("Portal", "Dragon Utopia", "Obelisk", "Morale and Luck",
                                  "Mana replenishment", "Town", "Underground gate",
                                  "Creature", "Favourites")]
CREATURE_LEVEL_KEYS = tuple(f"Creature level {level}" for level in range(1, 8))
UNKNOWN_CREATURE_LEVEL_KEY = "Creature (unknown level)"
_PIN_LOCK = threading.Lock()
_STAT_VISIT_LOCK = threading.Lock()
_FAVOURITES_LOCK = threading.RLock()
PRIMARY_STATS = ("Attack", "Defense", "Power", "Knowledge")
STAT_FIELDS = dict(zip(PRIMARY_STATS, ("attack", "defense", "spell_power", "knowledge")))
# Choice sites contribute to each possible stat's individual ceiling. These
# ceilings cannot necessarily all be reached by the same set of choices.
STAT_SITE_BONUSES = {
    "Arena": {"Attack": 2, "Defense": 2},
    "Marletto Tower": {"Defense": 1},
    "Garden of Revelation": {"Knowledge": 1},
    "Library of Enlightenment": dict.fromkeys(PRIMARY_STATS, 2),
    "School of Magic": {"Power": 1, "Knowledge": 1},
    "Mercenary Camp": {"Attack": 1},
    "Star Axis": {"Power": 1},
    "School of War": {"Attack": 1, "Defense": 1},
    "Colosseum of the Magi": {"Power": 2, "Knowledge": 2},
    **{f"Scholar ({stat})": {stat: 1} for stat in PRIMARY_STATS},
}
STAT_AREA_VALUES = {"Library of Enlightenment": 3,
                    "Arena": 2, "Colosseum of the Magi": 2}
STAT_AREA_MAX_SITES = 6


def stat_site_key(pin):
    return f"{pin['level']}:{pin['x']}:{pin['y']}"


def read_stat_visits(path):
    """Read user-confirmed visits; invalid or unavailable files yield no visits."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)
            and all(isinstance(item.get(key), str) for key in ("player", "hero", "site"))]


def write_stat_visits(path, visits):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".map_stat_visits_", suffix=".tmp",
                                         delete=False) as output:
            temporary = output.name
            json.dump(visits, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def visited_stat_sites(visits, player, hero):
    return {item["site"] for item in visits
            if item["player"] == player and item["hero"] == hero}


def stat_site_progress(hero, pins, visited):
    """Summarize discovered stat sites and each primary stat's possible ceiling."""
    skills = hero.get("primary_skills") or {}
    current = {stat: skills.get(field) if isinstance(skills.get(field), int)
               and not isinstance(skills.get(field), bool) else None
               for stat, field in STAT_FIELDS.items()}
    potential = current.copy()
    by_type = defaultdict(lambda: {"visited": 0, "total": 0})
    seen = set()
    for pin in pins:
        if pin.get("category") != "Stat increase" or not pin.get("automatic"):
            continue
        site = stat_site_key(pin)
        if site in seen:
            continue
        seen.add(site)
        title = pin.get("title", "Unknown site")
        counts = by_type[title]
        counts["total"] += 1
        if site in visited:
            counts["visited"] += 1
        else:
            for stat, bonus in STAT_SITE_BONUSES.get(title, {}).items():
                if potential[stat] is not None:
                    potential[stat] += bonus
    return current, potential, dict(sorted(by_type.items()))


def hero_map_position(hero, map_size, levels):
    """Return a saved hero's valid (level, x, y) position, if present."""
    coords = hero.get("coords") if isinstance(hero, dict) else None
    if isinstance(coords, dict):
        x, y, z = coords.get("x"), coords.get("y"), coords.get("z")
    elif isinstance(coords, (list, tuple)) and len(coords) == 3:
        x, y, z = coords
    else:
        return None
    if any(isinstance(value, bool) for value in (x, y, z)):
        return None
    try:
        x, y = int(x), int(y)
        level = 0 if z in (0, "0", "Surface") else 1 if z in (1, "1", "Underground") else -1
    except (TypeError, ValueError):
        return None
    return (level, x, y) if 0 <= level < levels and 0 <= x < map_size and 0 <= y < map_size else None


def stat_area_interests(pins, visited, hero_position, map_size=None):
    """Merge nearby known sites into bounded regions and rank their value."""
    if hero_position is None:
        return []
    candidates = sorted((pin for pin in pins if pin.get("automatic")
                         and pin.get("category") == "Stat increase"
                         and stat_site_key(pin) not in visited),
                        key=lambda pin: (pin["level"], pin["y"], pin["x"], pin["title"]))
    sites, seen = [], set()
    for pin in candidates:
        key = stat_site_key(pin)
        if key not in seen:
            sites.append(pin)
            seen.add(key)
    if map_size is None:
        map_size = max((max(pin["x"], pin["y"]) + 1 for pin in sites), default=1)
    max_gap = min(40, max(12, map_size * 0.22))
    max_span = min(60, max(18, map_size * 0.36))
    parents = list(range(len(sites)))
    clusters = [[pin] for pin in sites]

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    edges = sorted((math.hypot(first["x"] - second["x"], first["y"] - second["y"]), i, j)
                   for i, first in enumerate(sites) for j, second in enumerate(sites[i + 1:], i + 1)
                   if first["level"] == second["level"]
                   and math.hypot(first["x"] - second["x"], first["y"] - second["y"]) <= max_gap)
    for _gap, i, j in edges:
        left, right = root(i), root(j)
        if left == right:
            continue
        joined = clusters[left] + clusters[right]
        if len(joined) > STAT_AREA_MAX_SITES:
            continue
        if (max(pin["x"] for pin in joined) - min(pin["x"] for pin in joined) > max_span
                or max(pin["y"] for pin in joined) - min(pin["y"] for pin in joined) > max_span):
            continue
        parents[right] = left
        clusters[left] = joined
        clusters[right] = []
    ranked = []
    hero_level, hero_x, hero_y = hero_position
    for cluster in (cluster for cluster in clusters if cluster):
        level = cluster[0]["level"]
        center_x = sum(pin["x"] for pin in cluster) / len(cluster)
        center_y = sum(pin["y"] for pin in cluster) / len(cluster)
        spread = max(math.hypot(pin["x"] - center_x, pin["y"] - center_y)
                     for pin in cluster)
        nearest = min(cluster, key=lambda pin: math.hypot(pin["x"] - hero_x,
                                                         pin["y"] - hero_y))
        straight_distance = math.hypot(nearest["x"] - hero_x, nearest["y"] - hero_y)
        distance = straight_distance
        if level != hero_level:
            distance += 40  # Rough level-change penalty; no route or portal knowledge.
        value = sum(STAT_AREA_VALUES.get(pin["title"], 1) for pin in cluster)
        stat_gain = {stat: sum(STAT_SITE_BONUSES.get(pin["title"], {}).get(stat, 0)
                               for pin in cluster) for stat in PRIMARY_STATS}
        ranked.append({"level": level, "x": center_x, "y": center_y,
                       "min_x": min(pin["x"] for pin in cluster),
                       "max_x": max(pin["x"] for pin in cluster),
                       "min_y": min(pin["y"] for pin in cluster),
                       "max_y": max(pin["y"] for pin in cluster),
                       "nearest": nearest, "sites": cluster,
                       "value": value,
                       "stat_gain": stat_gain,
                       "unknown_stat_sites": sum(pin["title"] not in STAT_SITE_BONUSES
                                                 for pin in cluster),
                       "distance": distance,
                       "straight_distance": straight_distance,
                       "score": value * math.sqrt(len(cluster)) / (8 + distance + spread)})
    ranked.sort(key=lambda area: (-area["score"], area["distance"],
                                  area["level"], area["y"], area["x"]))
    for priority, area in enumerate(ranked, 1):
        area["priority"] = priority
    return ranked


def canonical_category(category):
    """Keep pins from earlier category layouts visible."""
    if category in ("Morale", "Luck", "Morale and luck"):
        return "Morale and Luck"
    return "Creature" if category in CREATURE_LEVEL_KEYS + (UNKNOWN_CREATURE_LEVEL_KEY,) else category


def creature_level_key(pin):
    """Use creature metadata, including levels encoded by earlier versions."""
    level = pin.get("creature_level")
    if isinstance(level, int) and 1 <= level <= 7:
        return f"Creature level {level}"
    category = pin.get("category")
    return category if category in CREATURE_LEVEL_KEYS else UNKNOWN_CREATURE_LEVEL_KEY


def normalized_hidden_categories(categories):
    """Apply saved visibility from earlier category layouts."""
    categories = categories or []
    hidden = {category if category in CREATURE_LEVEL_KEYS + (UNKNOWN_CREATURE_LEVEL_KEY,)
              else canonical_category(category)
              for category in categories if category != "Creature"}
    if "Creature" in categories:
        hidden.update(CREATURE_LEVEL_KEYS)
        hidden.add(UNKNOWN_CREATURE_LEVEL_KEY)
    return hidden


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
    return [{"id": f"auto:{item['level']}:{item['x']}:{item['y']}:{canonical_category(item['category'])}",
             "player": player, "level": item["level"], "x": item["x"], "y": item["y"],
             "title": item["title"], "category": canonical_category(item["category"]),
             "notes": item.get("notes", "Automatic marker"), "automatic": True,
             **({"creature_level": item["creature_level"]} if "creature_level" in item else
                {"creature_level": int(creature_level_key(item)[-1])}
                if item.get("category") in CREATURE_LEVEL_KEYS else {})}
            for item in objects
            if is_explored(mask, item["level"], item["x"], item["y"])]


def visible_transport_pins(transports, mask, player):
    return _visible_map_object_pins(transports, mask, player)


def visible_bonus_pins(bonuses, mask, player):
    """Expose bonus sites only after this player has explored their tile."""
    return _visible_map_object_pins(bonuses, mask, player)


def visible_obelisk_pins(obelisks, mask, player, obelisk_data=None):
    """Show discovered obelisks with visits from the matching save index."""
    data = obelisk_data if isinstance(obelisk_data, dict) else {}
    objects = data.get("objects")
    valid_table = (isinstance(objects, list) and data.get("total") == len(obelisks)
                   and len(objects) == len(obelisks)
                   and all(isinstance(item, dict) and isinstance(item.get("index"), int)
                           for item in objects)
                   and {item["index"] for item in objects}
                   == set(range(len(obelisks))))
    by_index = {item["index"]: item for item in objects} if valid_table else {}
    result = []
    for item in obelisks:
        if not is_explored(mask, item["level"], item["x"], item["y"]):
            continue
        index = item.get("obelisk_index")
        record = by_index.get(index) if isinstance(index, int) else None
        visitors = record.get("visited_by") if isinstance(record, dict) else None
        visited = isinstance(visitors, list) and player in visitors
        if visited:
            status = "Visited"
        elif record is not None and data.get("table_offset") is not None:
            status = "Unvisited"
        else:
            status = "Unknown"
        result.append({"id": f"auto:obelisk:{item['level']}:{item['x']}:{item['y']}",
                       "player": player, "level": item["level"],
                       "x": item["x"], "y": item["y"],
                       "title": "Obelisk", "category": "Obelisk",
                       "notes": f"{status} by {player}" if status != "Unknown"
                       else "Visit status unavailable from this save",
                       "visit_status": status, "automatic": True})
    return result


def clicked_stat_pin(point, pins, level):
    """Find the stat site under a clicked pin marker or rendered map tile."""
    if not isinstance(point, dict):
        return None
    pin_id = point.get("customdata")
    if pin_id:
        return next((pin for pin in pins if pin.get("id") == pin_id
                     and pin.get("level") == level and pin.get("automatic")
                     and pin.get("category") == "Stat increase"), None)
    if point.get("curveNumber") != 0:
        return None
    try:
        x, y = round(point["x"]), round(point["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return next((pin for pin in pins if pin.get("level") == level
                 and pin.get("x") == x and pin.get("y") == y
                 and pin.get("automatic") and pin.get("category") == "Stat increase"), None)


def selected_stat_pin(selected, pins):
    """Resolve a selected marker or its exact tile to a current automatic site."""
    if not isinstance(selected, dict):
        return None
    sites = [pin for pin in pins if pin.get("automatic")
             and pin.get("category") == "Stat increase"
             and pin.get("player") == selected.get("player")]
    pin_id = selected.get("id")
    if pin_id:
        match = next((pin for pin in sites if pin.get("id") == pin_id), None)
        if match:
            return match
    return next((pin for pin in sites if pin.get("level") == selected.get("level")
                 and pin.get("x") == selected.get("x")
                 and pin.get("y") == selected.get("y")), None)


def visible_utopia_pins(utopias, mask, player):
    """Expose Dragon Utopias only after this player has explored their tile."""
    return _visible_map_object_pins(utopias, mask, player)


def visible_creature_pins(creatures, mask, player):
    """Expose current creature stacks only within this player's explored area."""
    return _visible_map_object_pins(creatures, mask, player)


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


def read_creature_favourites(path):
    """Read player-scoped creature preferences; ignore malformed records."""
    return [item for item in read_pins(path)
            if isinstance(item, dict)
            and all(isinstance(item.get(key), str)
                    for key in ("player", "creature_id", "title"))]


def active_creature_favourites(path, player, creatures):
    """Drop favourites for stacks no longer present in the latest snapshot."""
    identities = {(pin["id"], pin["title"]) for pin in creatures}
    with _FAVOURITES_LOCK:
        entries = read_creature_favourites(path)
        active = [item for item in entries
                  if item["player"] != player
                  or (item["creature_id"], item["title"]) in identities]
        if len(active) != len(entries):
            try:
                write_pins(path, active)
            except OSError:
                pass  # Still hide missing stacks; retry pruning on the next refresh.
    return {item["creature_id"]: item for item in active if item["player"] == player}


def favourite_creature_pins(creatures, favourites):
    """Move active favourite stacks into their own gold category."""
    return [{**pin, "category": "Favourites",
             "favourite_quantity": favourites[pin["id"]].get("quantity"),
             "favourite_gold": favourites[pin["id"]].get("gold")}
            if pin["id"] in favourites and favourites[pin["id"]].get("title") == pin["title"]
            else pin for pin in creatures]


def favourite_gold_summary(pins):
    priced = [pin["favourite_gold"] for pin in pins
              if pin.get("category") == "Favourites"
              and isinstance(pin.get("favourite_gold"), int)
              and not isinstance(pin.get("favourite_gold"), bool)
              and pin["favourite_gold"] >= 0]
    return sum(priced), len(priced)


def optional_favourite_number(value, label, minimum):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number of at least {minimum}.")
    try:
        number = int(value)
        if number != float(value) or number < minimum:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a whole number of at least {minimum}.") from None
    return number


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


def grouped_pin_list(pins, hidden_categories=None, visited_stats=None, hero=None):
    """Build closed-by-default, clickable sections for visible pins."""
    sections = []
    hidden_categories = normalized_hidden_categories(hidden_categories)
    visited_stats = visited_stats or set()

    def pin_buttons(group, color, category):
        def pin_row(pin):
            choose = html.Button(
                f"{pin['title']} - "
                f"{'Surface' if pin['level'] == 0 else 'Underground'} "
                f"({pin['x']}/{pin['y']})" +
                (f" · {pin['visit_status']}" if pin.get("category") == "Obelisk" else "") +
                (f" · Visited by {hero}" if hero and pin.get("automatic")
                 and pin.get("category") == "Stat increase"
                 and stat_site_key(pin) in visited_stats else ""),
                id={"type": "map_pin_button", "pin_id": pin["id"]},
                n_clicks=0,
                style={"display": "block", "width": "100%", "textAlign": "left",
                       "border": "0", "borderLeft": f"4px solid {color}",
                       "background": "#fffaf0", "padding": "7px 9px",
                       "marginBottom": "4px", "cursor": "pointer"},
            )
            if category == "Creature":
                return html.Div([choose, html.Button(
                    "☆ Add to Favourites",
                    id={"type": "map_favourite_add", "pin_id": pin["id"]},
                    n_clicks=0, style={"margin": "0 0 8px 8px"})])
            if category == "Favourites":
                return html.Div([
                    choose,
                    html.Div([
                        html.Div([
                            html.Label("Count", style={"display": "block", "fontSize": "12px"}),
                            dcc.Input(id={"type": "map_favourite_quantity", "pin_id": pin["id"]},
                                      type="number", min=1, step=1,
                                      value=pin.get("favourite_quantity"),
                                      style={"width": "100%", "boxSizing": "border-box"}),
                        ]),
                        html.Div([
                            html.Label("Total gold", style={"display": "block", "fontSize": "12px"}),
                            dcc.Input(id={"type": "map_favourite_gold", "pin_id": pin["id"]},
                                      type="number", min=0, step=1,
                                      value=pin.get("favourite_gold"),
                                      style={"width": "100%", "boxSizing": "border-box"}),
                        ]),
                    ], style={"display": "grid", "gridTemplateColumns": "70px 95px",
                              "columnGap": "8px", "marginBottom": "6px"}),
                    html.Div([
                        html.Button("Save details",
                                    id={"type": "map_favourite_save", "pin_id": pin["id"]},
                                    n_clicks=0),
                        html.Button("Remove",
                                    id={"type": "map_favourite_remove", "pin_id": pin["id"]},
                                    n_clicks=0),
                    ], style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
                ], style={"padding": "5px 0 9px", "borderBottom": "1px solid #d9d1c3"})
            return choose

        return html.Div([pin_row(pin) for pin in group])

    # Keep older manually saved Town pins accessible for review and deletion.
    for category in CATEGORY_COLORS:
        def pin_sort_key(pin):
            title = pin["title"].casefold()
            if category == "Portal":
                return (title.partition(" ")[0], pin["level"], title,
                        pin["y"], pin["x"])
            return pin["level"], title

        group = sorted(
            (p for p in pins if p.get("category") == category),
            key=pin_sort_key,
        )
        if not group:
            continue
        color = CATEGORY_COLORS[category]
        if category == "Creature":
            levels = []
            for key in CREATURE_LEVEL_KEYS + (UNKNOWN_CREATURE_LEVEL_KEY,):
                members = [pin for pin in group if creature_level_key(pin) == key]
                if key == UNKNOWN_CREATURE_LEVEL_KEY and not members:
                    continue
                label = f"Level {key[-1]}" if key in CREATURE_LEVEL_KEYS else "Unknown level"
                levels.append(html.Details([
                    html.Summary(f"{label} ({len(members)})",
                                 style={"fontWeight": "bold", "cursor": "pointer",
                                        "padding": "6px 4px"}),
                    dcc.Checklist(
                        id={"type": "map_group_visibility", "category": key},
                        options=[{"label": "Show on map", "value": key}],
                        value=[] if key in hidden_categories else [key],
                        style={"padding": "2px 10px 8px", "fontSize": "13px"},
                        labelStyle={"cursor": "pointer"},
                    ),
                    pin_buttons(members, color, category),
                ], open=False, style={"marginLeft": "13px", "marginBottom": "3px"}))
            sections.append(html.Details([
                html.Summary([
                    html.Span(style={"display": "inline-block", "width": "10px", "height": "10px",
                                     "backgroundColor": color, "border": "1px solid #30271d",
                                     "borderRadius": "50%", "marginRight": "7px"}),
                    f"Creature ({len(group)})",
                ], style={"fontWeight": "bold", "cursor": "pointer", "padding": "8px 4px"}),
                html.Div(levels),
            ], open=False, style={"marginBottom": "4px"}))
            continue
        sections.append(html.Details([
            html.Summary([
                html.Span(style={"display": "inline-block", "width": "10px", "height": "10px",
                                 "backgroundColor": color, "border": "1px solid #30271d",
                                 "borderRadius": "50%", "marginRight": "7px"}),
                f"{category} ({len(group)})",
            ], style={"fontWeight": "bold", "cursor": "pointer", "padding": "8px 4px"}),
            dcc.Checklist(
                id={"type": "map_group_visibility", "category": category},
                options=[{"label": "Show on map", "value": category}],
                value=[] if category in hidden_categories else [category],
                style={"padding": "2px 10px 8px", "fontSize": "13px"},
                labelStyle={"cursor": "pointer"},
            ),
            pin_buttons(group, color, category),
        ], open=False, style={"marginBottom": "4px"}))
    return sections or [html.Div("No pins on explored tiles for this player.")]


def map_figure(mask, day, player, level, pins, selected=None, background=None, towns=None,
               hidden_categories=None, visited_stats=None, hide_visited_stats=False,
               stat_areas=None, hero_position=None):
    fig = go.Figure()
    if mask is None:
        fig.update_layout(title="No valid exploration data for this player")
        return fig
    size = mask.shape[1]
    hidden_categories = normalized_hidden_categories(hidden_categories)
    visited_stats = visited_stats or set()
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
    # Draw area fills as traces above the terrain, but below towns and pins.
    # Layout shapes on the "below" layer disappear behind the map image.
    for area in stat_areas or []:
        if area["level"] != level:
            continue
        first = area["priority"] == 1
        color = "#00E86B" if first else "#19B9F3"
        x0, x1 = area["min_x"] - 2, area["max_x"] + 2
        y0, y1 = area["min_y"] - 2, area["max_y"] + 2
        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0], y=[y0, y0, y1, y1, y0],
            mode="lines", fill="toself", name=f"Stat area #{area['priority']}",
            line={"color": color, "width": 4 if first else 3},
            fillcolor="rgba(0,232,107,0.22)" if first else "rgba(25,185,243,0.17)",
            hoverinfo="skip", showlegend=False,
        ))
    for town in [] if "Town" in hidden_categories else (towns or []):
        if town.get("level") != level or not is_explored(mask, level, town.get("x", -1), town.get("y", -1)):
            continue
        x, y = town["x"], town["y"]
        name = escape(str(town.get("name") or "Town"))
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers", name="Town",
            marker={"size": 16, "symbol": "square", "color": CATEGORY_COLORS["Town"],
                    "line": {"color": "#3b2b17", "width": 2}},
            hovertemplate=f"{name}<br>({x}, {y})<extra></extra>",
        ))
        fig.add_annotation(x=x, y=y, text=name, showarrow=False, yshift=20,
                           font={"size": 12, "color": "#fff8e2"},
                           bgcolor="rgba(40, 30, 20, 0.86)", bordercolor="#d8bd78",
                           borderwidth=1, borderpad=2)
    visible = [p for p in pins if p.get("player") == player and p.get("level") == level
               and not (p.get("automatic") and p.get("category") == "Town")
               and p.get("category") not in hidden_categories
               and not (p.get("category") == "Creature"
                        and creature_level_key(p) in hidden_categories)
               and not (hide_visited_stats and p.get("automatic")
                        and p.get("category") == "Stat increase"
                        and stat_site_key(p) in visited_stats)
               and is_explored(mask, level, p.get("x", -1), p.get("y", -1))]
    if visible:
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in visible], y=[p["y"] for p in visible], mode="markers",
            customdata=[p.get("id") for p in visible],
            marker={"size": 17, "color": [CATEGORY_COLORS.get(p.get("category"), CATEGORY_COLORS["Other"])
                                           for p in visible],
                    "symbol": ["circle-open" if p.get("automatic")
                               and ((p.get("category") == "Stat increase"
                                     and stat_site_key(p) in visited_stats)
                                    or (p.get("category") == "Obelisk"
                                        and p.get("visit_status") == "Visited"))
                               else "diamond"
                               for p in visible],
                    "line": {"color": "#222", "width": 1}},
            text=[f'{creature_level_key(p) if p["category"] == "Creature" else p["category"]}: '
                  f'{p["title"]}' +
                  ((f" · {p['visit_status']} by {player}"
                    if p["visit_status"] != "Unknown" else " · Visit status unknown")
                   if p.get("category") == "Obelisk" else '') +
                  (' · Visited by selected hero' if p.get("automatic")
                   and p.get("category") == "Stat increase"
                   and stat_site_key(p) in visited_stats else '') for p in visible],
            hovertemplate="%{text}<br>(%{x}, %{y})<extra></extra>",
        ))
    for area in stat_areas or []:
        if area["level"] != level:
            continue
        first = area["priority"] == 1
        color = "#00E86B" if first else "#19B9F3"
        gain = area["stat_gain"]
        fig.add_annotation(x=area["x"], y=area["y"],
                           text=(f"#{area['priority']} · {len(area['sites'])} sites<br>"
                                 f"A+{gain['Attack']} D+{gain['Defense']} "
                                 f"P+{gain['Power']} K+{gain['Knowledge']}"
                                 + ("*" if area["unknown_stat_sites"] else "")),
                           showarrow=False, yshift=26 if area["y"] > size / 2 else -26,
                           font={"size": 12, "color": "#061f16"},
                           bgcolor=color, bordercolor="#092d21", borderwidth=1,
                           borderpad=3)
    if hero_position is not None and hero_position[0] == level:
        fig.add_trace(go.Scatter(
            x=[hero_position[1]], y=[hero_position[2]], mode="markers",
            name="Selected hero", customdata=[None],
            marker={"symbol": "star", "size": 20, "color": "#FFFFFF",
                    "line": {"color": "#26394A", "width": 2}},
            hovertemplate="Selected hero<extra></extra>", showlegend=False,
        ))
    if (selected and selected.get("player") == player and selected.get("level") == level
            and is_explored(mask, level, selected.get("x", -1), selected.get("y", -1))):
        fig.add_trace(go.Scatter(
            x=[selected["x"]], y=[selected["y"]], mode="markers",
            name="Selected location", customdata=[selected.get("id")],
            marker={"symbol": "circle-open", "size": 44, "color": "#00FF66",
                    "line": {"color": "#003319", "width": 2}},
            hoverinfo="skip", showlegend=False,
        ))
        fig.add_annotation(x=selected["x"], y=selected["y"], text="SELECTED",
                           showarrow=True, ax=0, ay=-48, arrowhead=2,
                           arrowcolor="#00FF66", arrowwidth=3,
                           font={"size": 12, "color": "#003319"},
                           bgcolor="#baffcf", bordercolor="#00a645", borderwidth=2,
                           borderpad=4)
    focus = selected and selected.get("focus") and selected.get("level") == level
    width = min(24, size / 2)
    if focus:
        bounds = selected.get("focus_bounds")
        if bounds:
            x0, y0, x1, y1 = bounds
            width = max(12, (x1 - x0) / 2 + 4, (y1 - y0) / 2 + 4)
            center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
        else:
            center_x, center_y = selected["x"], selected["y"]
        x_range = [center_x - width, center_x + width]
        y_range = [center_y + width, center_y - width]
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
        dragmode="pan", uirevision=f"{player}:{level}:{selected.get('focus_request', 0) if selected else 0}",
        margin={"l": 45, "r": 15, "t": 50, "b": 45},
        paper_bgcolor="#f5f0e3", plot_bgcolor="#15171d", showlegend=False,
    )
    return fig


def register_map_helper(app, df_players, game_info, input_dir, graphics_provider=None,
                        default_player=None, data_provider=None, refresh_interval_ms=None,
                        lock_player=False, transport_provider=None, bonus_provider=None,
                        utopia_provider=None, creature_provider=None, obelisk_provider=None):
    size = int(game_info.get("map_size") or 0)
    levels = int(game_info.get("levels") or 1)
    path = Path(input_dir) / "map_pins.json"
    stat_visits_path = Path(input_dir) / "map_stat_visits.json"
    favourites_path = Path(input_dir) / "map_creature_favourites.json"

    def current_data():
        return data_provider() if data_provider else (df_players, 0)

    def available_players(rows):
        return [p for p in rows["player_color"].dropna().unique()
                if p != "None" and latest_fog(rows, p, size, levels)[1] is not None]

    def hero_names(rows, player):
        if player is None or "hero_summary" not in rows:
            return []
        matching = rows[rows["player_color"] == player]
        if matching.empty:
            return []
        names = matching.iloc[-1].get("hero_summary")
        return list(dict.fromkeys(name for name in names or [] if isinstance(name, str) and name))

    def selected_hero(rows, player, name):
        if not name or player is None or "hero_details" not in rows:
            return None
        matching = rows[rows["player_color"] == player]
        if matching.empty:
            return None
        details = matching.iloc[-1].get("hero_details")
        return next((item for item in details or [] if item.get("name") == name), None)

    def interest_data(rows, player, hero_name, mask):
        hero = selected_hero(rows, player, hero_name)
        position = hero_map_position(hero, size, levels)
        if position is None or mask is None:
            return position, []
        bonuses = bonus_provider() if bonus_provider else []
        pins = visible_bonus_pins(bonuses, mask, player)
        visited = visited_stat_sites(read_stat_visits(stat_visits_path), player, hero_name)
        return position, stat_area_interests(pins, visited, position, size)

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
    initial_heroes = hero_names(df_players, selected_player)

    def active_player(requested):
        return selected_player if lock_player else requested

    def current_pins(player, mask, towns=None):
        saved = [{**p, "category": canonical_category(p.get("category")),
                  **({"creature_level": int(creature_level_key(p)[-1])}
                     if creature_level_key(p) in CREATURE_LEVEL_KEYS else {})}
                 for p in read_pins(path) if p.get("player") == player and
                 is_explored(mask, p.get("level", -1), p.get("x", -1), p.get("y", -1))]
        transports = transport_provider() if transport_provider else []
        bonuses = bonus_provider() if bonus_provider else []
        utopias = utopia_provider() if utopia_provider else []
        obelisks = obelisk_provider() if obelisk_provider else []
        rows, _ = current_data()
        obelisk_data = None
        if "obelisk_data" in rows:
            player_rows = rows[rows["player_color"] == player]
            if not player_rows.empty:
                obelisk_data = player_rows.iloc[-1].get("obelisk_data")
        creatures = creature_provider() if creature_provider else []
        creature_pins = visible_creature_pins(creatures, mask, player)
        if creature_provider and mask is not None:
            favourites = active_creature_favourites(favourites_path, player, creature_pins)
            creature_pins = favourite_creature_pins(creature_pins, favourites)
        if towns is None:
            towns = visible_towns(rows, player, size, levels)
        return (saved + visible_transport_pins(transports, mask, player) +
                visible_bonus_pins(bonuses, mask, player) +
                visible_utopia_pins(utopias, mask, player) +
                visible_obelisk_pins(obelisks, mask, player, obelisk_data) +
                creature_pins + visible_town_pins(towns, player))

    layout = html.Div([
        html.H2("Map Helper"),
        html.P("Latest processed turn. Click an explored tile to add a pin or a stat-site marker "
               "to toggle its visit for the selected hero. Drag to pan; scroll to zoom."),
        dcc.Interval(id="map_poll", interval=refresh_interval_ms or 5000,
                     disabled=refresh_interval_ms is None),
        dcc.Store(id="map_data_revision", data=0),
        dcc.Store(id="map_hidden_categories", data=[], storage_type="session"),
        dcc.Store(id="map_selected"),
        dcc.Store(id="map_revision", data=0),
        dcc.Store(id="map_stat_revision", data=0),
        dcc.Store(id="map_favourites_revision", data=0),
        dcc.Store(id="map_stat_interest_enabled", data=False, storage_type="session"),
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
                html.Div([
                    html.Label("Track stat visits for hero"),
                    dcc.Dropdown(id="map_stat_hero", options=initial_heroes,
                                 value=initial_heroes[0] if initial_heroes else None,
                                 placeholder="Select a hero", clearable=True),
                    dcc.Checklist(id="map_hide_visited_stats",
                                  options=[{"label": "Hide objects already visited by this hero",
                                            "value": "hide"}],
                                  value=[], persistence=True, persistence_type="session",
                                  style={"marginTop": "7px"}),
                    html.Div("Visits are marked by you; the processed saves do not record "
                             "which hero visited each stat site.",
                             style={"fontSize": "12px", "opacity": 0.8}),
                ], style={"maxWidth": "430px", "marginTop": "10px"}),
                html.Div(id="map_stat_overview", style={"marginTop": "12px"}),
                html.Div([
                    html.Button("Stat area of interest: Off", id="map_stat_interest_toggle",
                                n_clicks=0),
                    html.Div(id="map_stat_interest_summary", style={"marginTop": "8px"}),
                ], style={"marginTop": "12px"}),
                html.Div([
                    html.Div(id="map_selected_caption", style={"fontWeight": "bold"}),
                    html.Button("Show selected on map", id="map_show_selected", n_clicks=0,
                                disabled=True),
                ], style={"display": "flex", "alignItems": "center", "gap": "12px",
                          "flexWrap": "wrap", "margin": "12px 0 6px"}),
                dcc.Graph(id="map_helper_graph", config={"scrollZoom": True, "displayModeBar": True},
                          style={"height": "min(82vh, 1000px)", "minHeight": "520px"}),
            ], style={"flex": "1 1 720px", "minWidth": "360px"}),
            html.Div([
                html.H3("Pins"),
                html.Div(id="map_favourites_total", style={"fontWeight": "bold",
                                                             "marginBottom": "10px"}),
                html.Div(id="map_pin_list", style={"maxHeight": "min(65vh, 800px)",
                                                   "overflowY": "auto"}),
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
                html.Button("Add creature to Favourites", id="map_favourite_selected",
                            n_clicks=0, disabled=True, style={"marginTop": "12px"}),
                html.Div(id="map_favourite_message", role="status",
                         style={"marginTop": "7px"}),
                html.Div([
                    html.Button("Mark visited", id="map_stat_visit_toggle",
                                n_clicks=0),
                    html.Button("Mark unvisited", id="map_stat_unvisit",
                                n_clicks=0),
                ], style={"display": "flex", "gap": "8px", "marginTop": "12px"}),
                html.Div(id="map_stat_target", style={"fontSize": "12px", "marginTop": "6px"}),
                html.Div(id="map_stat_message", role="status", style={"marginTop": "7px"}),
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

    @app.callback(Output("map_stat_hero", "options"), Output("map_stat_hero", "value"),
                  Input("map_player", player_property), Input("map_data_revision", "data"),
                  State("map_stat_hero", "value"))
    def update_hero_choices(player, _revision, selected_hero):
        names = hero_names(current_data()[0], active_player(player))
        return names, selected_hero if selected_hero in names else names[0] if names else None

    @app.callback(Output("map_stat_overview", "children"),
                  Input("map_player", player_property), Input("map_stat_hero", "value"),
                  Input("map_stat_revision", "data"), Input("map_data_revision", "data"))
    def update_stat_overview(player, hero_name, _stat_revision, _data_revision):
        player = active_player(player)
        if not hero_name or not player:
            return html.Div("Select a hero to see primary stats and stat-site progress.")
        rows, _ = current_data()
        matching = rows[rows["player_color"] == player]
        if matching.empty:
            return html.Div("No current hero data available.")
        details = matching.iloc[-1].get("hero_details")
        hero = next((item for item in details or [] if item.get("name") == hero_name), None)
        if hero is None:
            return html.Div("No current hero data available.")
        mask = latest_fog(rows, player, size, levels)[1]
        pins = visible_bonus_pins(bonus_provider() if bonus_provider else [], mask, player)
        visited = visited_stat_sites(read_stat_visits(stat_visits_path), player, hero_name)
        current, potential, by_type = stat_site_progress(hero, pins, visited)
        cards = [html.Div([
            html.Div(stat, style={"fontWeight": "bold"}),
            html.Div(f"{current[stat]} → {potential[stat]}" if current[stat] is not None
                     else "Unavailable", style={"fontSize": "20px"}),
        ], style={"flex": "1 1 130px", "padding": "8px 12px", "background": "#f5f0e3",
                  "borderRadius": "6px"}) for stat in PRIMARY_STATS]
        progress = []
        for title, counts in by_type.items():
            percent = round(100 * counts["visited"] / counts["total"])
            progress.append(html.Div([
                html.Div([html.Span(title), html.Span(
                    f"{counts['visited']}/{counts['total']} ({percent}%)")],
                    style={"display": "flex", "justifyContent": "space-between", "gap": "8px"}),
                html.Div(html.Div(style={"height": "100%", "width": f"{percent}%",
                                         "background": CATEGORY_COLORS["Stat increase"],
                                         "borderRadius": "4px"}),
                         role="progressbar", **{"aria-valuenow": percent,
                                                 "aria-valuemin": 0, "aria-valuemax": 100,
                                                 "aria-label": f"{title} visited"},
                         style={"height": "8px", "background": "#e5e5e5",
                                "borderRadius": "4px", "marginTop": "4px"}),
            ], style={"minWidth": "220px", "flex": "1 1 220px"}))
        return html.Div([
            html.H4(f"{hero_name}: primary stats", style={"margin": "0 0 6px"}),
            html.Div("Current → possible max from discovered, unmarked sites",
                     style={"fontSize": "12px", "marginBottom": "8px"}),
            html.Div(cards, style={"display": "flex", "gap": "8px", "flexWrap": "wrap"}),
            html.H4("Visited stat sites by type", style={"margin": "12px 0 6px"}),
            html.Div(progress, style={"display": "flex", "gap": "10px 16px", "flexWrap": "wrap"})
            if progress else html.Div("No discovered stat sites yet."),
            html.Div("Choice-site ceilings are separate estimates; level requirements and fees "
                     "are not checked. Unmarked visits are treated as available.",
                     style={"fontSize": "12px", "opacity": 0.8, "marginTop": "8px"}),
        ])

    @app.callback(Output("map_stat_interest_enabled", "data"),
                  Input("map_stat_interest_toggle", "n_clicks"),
                  State("map_stat_interest_enabled", "data"), prevent_initial_call=True)
    def toggle_stat_interest(_clicks, enabled):
        return not bool(enabled)

    @app.callback(Output("map_stat_interest_toggle", "children"),
                  Output("map_stat_interest_toggle", "style"),
                  Input("map_stat_interest_enabled", "data"))
    def stat_interest_button(enabled):
        return ("Stat area of interest: On" if enabled else "Stat area of interest: Off",
                {"background": "#baffcf" if enabled else "#f5f0e3",
                 "border": "2px solid #16874b" if enabled else "1px solid #776b58",
                 "borderRadius": "6px", "padding": "7px 12px", "cursor": "pointer"})

    @app.callback(Output("map_stat_interest_summary", "children"),
                  Input("map_stat_interest_enabled", "data"),
                  Input("map_player", player_property), Input("map_stat_hero", "value"),
                  Input("map_stat_revision", "data"), Input("map_data_revision", "data"))
    def show_stat_interests(enabled, player, hero_name, _stat_revision, _data_revision):
        if not enabled:
            return None
        player = active_player(player)
        if not hero_name:
            return "Choose a hero to rank stat areas."
        rows, _ = current_data()
        mask = latest_fog(rows, player, size, levels)[1]
        position, areas = interest_data(rows, player, hero_name, mask)
        if position is None:
            return f"No current map position is available for {hero_name}."
        if not areas:
            return "No discovered, unvisited stat sites remain for this hero."
        items = []
        for area in areas:
            nearest = area["nearest"]
            label = "Surface" if area["level"] == 0 else "Underground"
            site_names = ", ".join(f"{pin['title']} (weight {STAT_AREA_VALUES.get(pin['title'], 1)})"
                                   for pin in area["sites"])
            travel_note = (f"~{area['straight_distance']:.0f} tiles"
                           + (" + level penalty" if area["level"] != position[0] else ""))
            items.append(html.Li([
                html.Strong(f"#{area['priority']} · {label} ({nearest['x']}, {nearest['y']})"),
                f" — {len(area['sites'])} site{'s' if len(area['sites']) != 1 else ''}, "
                + ", ".join(f"{stat} +{area['stat_gain'][stat]}" for stat in PRIMARY_STATS)
                + (f" from known sites ({area['unknown_stat_sites']} unknown)"
                   if area['unknown_stat_sites'] else "")
                + f"; priority value {area['value']}; "
                f"ranking distance {travel_note}. ",
                html.Span(site_names, style={"opacity": 0.8}),
                html.Button("Show area", id={"type": "map_interest_area", "site": nearest["id"]},
                            n_clicks=0, style={"marginLeft": "8px"}),
            ], style={"marginBottom": "6px"}))
        return html.Div([
            html.Div(f"Suggested stat areas for {hero_name} from "
                     f"{'Surface' if position[0] == 0 else 'Underground'} "
                     f"({position[1]}, {position[2]})", style={"fontWeight": "bold"}),
            html.Ol(items, style={"paddingLeft": "20px", "margin": "6px 0",
                                  "maxHeight": "200px", "overflowY": "auto"}),
            html.Div("A/D/P/K on the map means Attack/Defense/Power/Knowledge. "
                     "Each stat shows its possible gain; choice-site gains are alternatives "
                     "and cannot all be earned together. "
                     "Priority weights: Library 3; Arena and Colosseum of the Magi 2; "
                     "other stat sites 1. "
                     "Priority favors multi-site clusters and also "
                     "uses straight-line distance and cluster spread. Obstacles, roads, "
                     "portals, visit requirements, "
                     "and fees are not included; other map levels get a fixed travel penalty.",
                     style={"fontSize": "12px", "opacity": 0.8}),
        ], style={"padding": "10px", "background": "#f5f0e3", "borderRadius": "6px"})

    @app.callback(Output("map_selected", "data"), Output("map_level", "value"),
                  Input("map_helper_graph", "clickData"),
                  Input({"type": "map_pin_button", "pin_id": ALL}, "n_clicks"),
                  Input({"type": "map_interest_area", "site": ALL}, "n_clicks"),
                  Input("map_player", player_property), Input("map_action", "data"),
                  Input("map_show_selected", "n_clicks"),
                  State("map_level", "value"), State("map_selected", "data"),
                  State("map_stat_hero", "value"))
    def select_pin(click, _pin_clicks, _area_clicks, player, action, show_clicks,
                   level, selected, hero_name):
        player = active_player(player)
        trigger = ctx.triggered_id
        if trigger == "map_player":
            return None, no_update
        if trigger == "map_show_selected":
            if selected and selected.get("player") == player:
                mask = latest_fog(current_data()[0], player, size, levels)[1]
                if is_explored(mask, selected.get("level", -1),
                               selected.get("x", -1), selected.get("y", -1)):
                    return {**selected, "focus": True, "focus_bounds": None,
                            "focus_request": show_clicks}, selected["level"]
            return no_update, no_update
        if (isinstance(trigger, dict) and trigger.get("type") == "map_interest_area"
                and any(_area_clicks or [])):
            rows, _ = current_data()
            mask = latest_fog(rows, player, size, levels)[1]
            pin = next((item for item in current_pins(player, mask)
                        if item.get("id") == trigger.get("site") and item.get("automatic")
                        and item.get("category") == "Stat increase"), None)
            if pin:
                _, areas = interest_data(rows, player, hero_name, mask)
                area = next((item for item in areas
                             if item["nearest"]["id"] == pin["id"]), None)
                bounds = ([area["min_x"] - 2, area["min_y"] - 2,
                           area["max_x"] + 2, area["max_y"] + 2] if area else None)
                return {**pin, "focus": True,
                        "focus_bounds": bounds,
                        "focus_request": (selected or {}).get("focus_request", 0) + 1}, pin["level"]
            return no_update, no_update
        if trigger == "map_action" and action:
            if action.get("id"):
                mask = latest_fog(current_data()[0], player, size, levels)[1]
                pin = next((p for p in current_pins(player, mask) if p.get("id") == action["id"]), None)
                if pin:
                    return {**pin, "focus": False,
                            "focus_request": (selected or {}).get("focus_request", 0)}, pin["level"]
            return None, no_update
        if (isinstance(trigger, dict) and trigger.get("type") == "map_pin_button"
                and any(_pin_clicks or [])):
            pin_id = trigger.get("pin_id")
            day, mask = latest_fog(current_data()[0], player, size, levels)
            pin = next((p for p in current_pins(player, mask) if p.get("id") == pin_id), None)
            if pin:
                if is_explored(mask, pin["level"], pin["x"], pin["y"]):
                    return {**pin, "focus": False,
                            "focus_request": (selected or {}).get("focus_request", 0)}, pin["level"]
        if trigger == "map_helper_graph" and not (click and click.get("points")):
            # Plotly may clear clickData when the figure redraws after a visit.
            # That is not a new selection and must not discard the active site.
            return no_update, no_update
        if trigger == "map_helper_graph" and click and click.get("points"):
            point = click["points"][0]
            x, y = round(point["x"]), round(point["y"])
            day, mask = latest_fog(current_data()[0], player, size, levels)
            if is_explored(mask, level, x, y):
                pin_id = point.get("customdata")
                if pin_id:
                    pin = next((pin for pin in current_pins(player, mask)
                                if pin.get("id") == pin_id and pin["level"] == level), None)
                    if pin:
                        return {**pin, "focus": False,
                                "focus_request": (selected or {}).get("focus_request", 0)}, no_update
                site = clicked_stat_pin(point, current_pins(player, mask), level)
                if site:
                    return {**site, "focus": False,
                            "focus_request": (selected or {}).get("focus_request", 0)}, no_update
                return {"player": player, "level": level, "x": x, "y": y,
                        "focus_request": (selected or {}).get("focus_request", 0)}, no_update
        return no_update, no_update

    @app.callback(Output("map_coordinates", "children"), Output("map_title", "value"),
                  Output("map_category", "value"), Output("map_notes", "value"),
                  Output("map_title", "disabled"), Output("map_category", "disabled"),
                  Output("map_notes", "disabled"), Output("map_save", "disabled"),
                  Output("map_delete", "disabled"), Output("map_show_selected", "disabled"),
                  Output("map_selected_caption", "children"),
                  Input("map_selected", "data"))
    def show_selected(selected):
        if not selected:
            return ("Click an explored tile or choose a pin.", "", "Other", "",
                    False, False, False, False, False, True, "No location selected")
        automatic = bool(selected.get("automatic"))
        label = (f"{'Surface' if selected['level'] == 0 else 'Underground'} "
                 f"({selected['x']}, {selected['y']})")
        if automatic:
            label += f" · Automatic {selected['category']} marker"
        category = selected.get("category")
        caption = (f"Selected: {selected.get('title') or 'Map tile'} · "
                   f"{'Surface' if selected['level'] == 0 else 'Underground'} "
                   f"({selected['x']}, {selected['y']})")
        return (label, selected.get("title", ""),
                category if category in CATEGORIES else None if automatic else "Other",
                selected.get("notes", ""), automatic, automatic, automatic,
                automatic, automatic, False, caption)

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

    @app.callback(Output("map_stat_target", "children"),
                  Input("map_selected", "data"), Input("map_stat_hero", "value"),
                  Input("map_stat_revision", "data"), State("map_player", player_property))
    def stat_visit_target(selected, hero, _revision, player):
        player = active_player(player)
        if not hero:
            return "Choose a hero, then select a discovered Stat increase site."
        rows, _ = current_data()
        mask = latest_fog(rows, player, size, levels)[1]
        site = selected_stat_pin(selected, current_pins(player, mask))
        if site is None:
            return "Select a discovered Stat increase site to change its visit status."
        visited = stat_site_key(site) in visited_stat_sites(
            read_stat_visits(stat_visits_path), player, hero)
        return f"{site['title']} · {hero}: {'visited' if visited else 'unvisited'}"

    @app.callback(Output("map_stat_revision", "data"), Output("map_stat_message", "children"),
                  Input("map_stat_visit_toggle", "n_clicks"),
                  Input("map_stat_unvisit", "n_clicks"),
                  Input("map_helper_graph", "clickData"),
                  State("map_selected", "data"), State("map_stat_hero", "value"),
                  State("map_player", player_property), State("map_stat_revision", "data"),
                  State("map_level", "value"),
                  prevent_initial_call=True)
    def toggle_stat_visit(_visit_clicks, _unvisit_clicks, click, selected, hero, player, revision, level):
        player = active_player(player)
        rows, _ = current_data()
        mask = latest_fog(rows, player, size, levels)[1]
        pins = current_pins(player, mask)
        if ctx.triggered_id == "map_helper_graph":
            points = (click or {}).get("points") or []
            point = points[0] if points else None
            selected = clicked_stat_pin(point, pins, level)
            if not selected:
                return no_update, no_update
        site_pin = selected_stat_pin(selected, pins)
        if not hero or hero not in hero_names(rows, player) or site_pin is None:
            return no_update, "Select a discovered stat site and a current hero."
        site = stat_site_key(site_pin)
        with _STAT_VISIT_LOCK:
            visits = read_stat_visits(stat_visits_path)
            visited = visited_stat_sites(visits, player, hero)
            trigger = ctx.triggered_id
            if trigger == "map_stat_visit_toggle" and site in visited:
                return no_update, f"{site_pin['title']} is already marked visited for {hero}."
            if trigger == "map_stat_unvisit" and site not in visited:
                return no_update, f"{site_pin['title']} is already marked unvisited for {hero}."
            if site in visited:
                visits = [item for item in visits if not (item["player"] == player
                          and item["hero"] == hero and item["site"] == site)]
                message = f"Marked {site_pin['title']} unvisited for {hero}."
            else:
                visits.append({"player": player, "hero": hero, "site": site})
                message = f"Marked {site_pin['title']} visited for {hero}."
            try:
                write_stat_visits(stat_visits_path, visits)
            except OSError as exc:
                return no_update, f"Could not save visit status: {exc}"
        return (revision or 0) + 1, message

    @app.callback(Output("map_favourite_selected", "children"),
                  Output("map_favourite_selected", "disabled"),
                  Input("map_selected", "data"), Input("map_favourites_revision", "data"),
                  Input("map_data_revision", "data"), State("map_player", player_property))
    def selected_favourite_action(selected, _revision, _data_revision, player):
        player = active_player(player)
        if selected and selected.get("player") == player:
            mask = latest_fog(current_data()[0], player, size, levels)[1]
            pin = next((item for item in current_pins(player, mask)
                        if item.get("id") == selected.get("id")
                        and item.get("category") in ("Creature", "Favourites")), None)
            if pin:
                return ("Remove from Favourites" if pin["category"] == "Favourites"
                        else "Add creature to Favourites"), False
        return "Add creature to Favourites", True

    @app.callback(Output("map_favourites_revision", "data"),
                  Output("map_favourite_message", "children"),
                  Input("map_favourite_selected", "n_clicks"),
                  Input({"type": "map_favourite_add", "pin_id": ALL}, "n_clicks"),
                  Input({"type": "map_favourite_remove", "pin_id": ALL}, "n_clicks"),
                  Input({"type": "map_favourite_save", "pin_id": ALL}, "n_clicks"),
                  State({"type": "map_favourite_quantity", "pin_id": ALL}, "value"),
                  State({"type": "map_favourite_quantity", "pin_id": ALL}, "id"),
                  State({"type": "map_favourite_gold", "pin_id": ALL}, "value"),
                  State({"type": "map_favourite_gold", "pin_id": ALL}, "id"),
                  State("map_selected", "data"), State("map_player", player_property),
                  State("map_favourites_revision", "data"), prevent_initial_call=True)
    def change_favourite(_selected_clicks, _add_clicks, _remove_clicks, _save_clicks,
                         quantities, quantity_ids, gold_values, gold_ids,
                         selected, player, revision):
        trigger = ctx.triggered_id
        player = active_player(player)
        action = ("toggle" if trigger == "map_favourite_selected" else
                  trigger.get("type", "").removeprefix("map_favourite_")
                  if isinstance(trigger, dict) else "")
        clicks = {"toggle": _selected_clicks, "add": _add_clicks,
                  "remove": _remove_clicks, "save": _save_clicks}.get(action)
        if not (any(clicks or []) if isinstance(clicks, list) else clicks):
            return no_update, no_update
        pin_id = (selected or {}).get("id") if action == "toggle" else trigger.get("pin_id")
        mask = latest_fog(current_data()[0], player, size, levels)[1]
        pin = next((item for item in current_pins(player, mask)
                    if item.get("id") == pin_id and item.get("automatic")
                    and item.get("category") in ("Creature", "Favourites")), None)
        if pin is None:
            return no_update, "That creature is no longer visible on the map."
        if action == "toggle":
            action = "remove" if pin["category"] == "Favourites" else "add"
        with _FAVOURITES_LOCK:
            entries = read_creature_favourites(favourites_path)
            existing = next((item for item in entries if item["player"] == player
                             and item["creature_id"] == pin_id
                             and item["title"] == pin["title"]), None)
            if action == "add":
                if existing:
                    return no_update, f"{pin['title']} is already a favourite."
                entries.append({"player": player, "creature_id": pin_id,
                                "title": pin["title"], "quantity": None, "gold": None})
                message = f"Added {pin['title']} to Favourites."
            elif action == "remove":
                if existing is None:
                    return no_update, f"{pin['title']} is not a favourite."
                entries.remove(existing)
                message = f"Removed {pin['title']} from Favourites."
            elif action == "save":
                if existing is None:
                    return no_update, "Add this creature to Favourites first."
                quantity = next((value for value, item_id in zip(quantities or [], quantity_ids or [])
                                 if item_id.get("pin_id") == pin_id), None)
                gold = next((value for value, item_id in zip(gold_values or [], gold_ids or [])
                             if item_id.get("pin_id") == pin_id), None)
                try:
                    existing["quantity"] = optional_favourite_number(quantity, "Creatures", 1)
                    existing["gold"] = optional_favourite_number(gold, "Joining gold", 0)
                except ValueError as exc:
                    return no_update, str(exc)
                message = f"Saved joining details for {pin['title']}."
            else:
                return no_update, no_update
            try:
                write_pins(favourites_path, entries)
            except OSError as exc:
                return no_update, f"Could not save Favourites: {exc}"
        return (revision or 0) + 1, message

    @app.callback(Output("map_favourites_total", "children"),
                  Input("map_player", player_property),
                  Input("map_favourites_revision", "data"),
                  Input("map_data_revision", "data"))
    def favourites_total(player, _revision, _data_revision):
        player = active_player(player)
        mask = latest_fog(current_data()[0], player, size, levels)[1]
        total, priced = favourite_gold_summary(current_pins(player, mask))
        return f"Favourite joining gold: {total:,} ({priced} priced stacks)"

    @app.callback(Output("map_pin_list", "children"),
                  Input("map_player", player_property), Input("map_revision", "data"),
                  Input("map_data_revision", "data"), Input("map_stat_hero", "value"),
                  Input("map_stat_revision", "data"), Input("map_favourites_revision", "data"),
                  State("map_hidden_categories", "data"))
    def pin_options(player, revision, data_revision, hero, stat_revision,
                    favourites_revision, hidden_categories):
        player = active_player(player)
        day, mask = latest_fog(current_data()[0], player, size, levels)
        visited = visited_stat_sites(read_stat_visits(stat_visits_path), player, hero) if hero else set()
        return grouped_pin_list(current_pins(player, mask), hidden_categories, visited, hero)

    @app.callback(Output("map_hidden_categories", "data"),
                  Input({"type": "map_group_visibility", "category": ALL}, "value"),
                  State({"type": "map_group_visibility", "category": ALL}, "id"),
                  State("map_hidden_categories", "data"), prevent_initial_call=True)
    def toggle_group(values, ids, hidden_categories):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or triggered.get("type") != "map_group_visibility":
            return no_update
        category = triggered.get("category")
        current = next((value for value, item_id in zip(values, ids)
                        if item_id.get("category") == category), None)
        if (category not in CATEGORY_COLORS
                and category not in CREATURE_LEVEL_KEYS + (UNKNOWN_CREATURE_LEVEL_KEY,)) or current is None:
            return no_update
        hidden = normalized_hidden_categories(hidden_categories)
        if category in current:
            hidden.discard(category)
        else:
            hidden.add(category)
        return sorted(hidden) if hidden != set(hidden_categories or []) else no_update

    @app.callback(Output("map_helper_graph", "figure"), Input("map_player", player_property),
                  Input("map_level", "value"), Input("map_revision", "data"),
                  Input("map_selected", "data"), Input("map_data_revision", "data"),
                  Input("map_favourites_revision", "data"),
                  Input("map_hidden_categories", "data"), Input("map_stat_hero", "value"),
                  Input("map_stat_revision", "data"), Input("map_hide_visited_stats", "value"),
                  Input("map_stat_interest_enabled", "data"))
    def update_map(player, level, revision, selected, data_revision, favourites_revision,
                   hidden_categories,
                   hero, stat_revision, hide_visited_stats, interest_enabled):
        player = active_player(player)
        if player is None or level is None:
            return go.Figure()
        rows, _ = current_data()
        day, mask = latest_fog(rows, player, size, levels)
        background = graphics_provider(mask, level, player) if graphics_provider and mask is not None else None
        towns = visible_towns(rows, player, size, levels)
        pins = current_pins(player, mask, towns)
        if (selected and selected.get("automatic")
                and selected.get("category") in ("Creature", "Favourites")
                and not any(pin["id"] == selected.get("id") for pin in pins)):
            selected = None
        visited = visited_stat_sites(read_stat_visits(stat_visits_path), player, hero) if hero else set()
        position, areas = interest_data(rows, player, hero, mask) if interest_enabled else (None, [])
        return map_figure(mask, day, player, level, pins,
                          selected, background, towns, hidden_categories, visited,
                          bool(hero and "hide" in (hide_visited_stats or [])), areas, position)

    return layout
