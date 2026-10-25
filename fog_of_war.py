"""Build the dashboard's player- and day-specific Fog of War figure."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

OVERVIEW_TILE_SIZE = 8


def hero_track_colors(heroes, player):
    """Assign each hero one color across all players in this processed game."""
    if heroes is None or not {"player_color", "hero_name"}.issubset(heroes.columns):
        return {}
    names = sorted({name for name in heroes["hero_name"]
                    if isinstance(name, str) and name})
    selected = {name for name in heroes.loc[
        heroes["player_color"] == player, "hero_name"]
                if isinstance(name, str) and name}
    return {name: f"hsl({(index * 137.508) % 360:.3f}, 85%, 48%)"
            for index, name in enumerate(names) if name in selected}


def _hero_position(coords, size, levels):
    if isinstance(coords, dict):
        values = coords.get("x"), coords.get("y"), coords.get("z")
    elif isinstance(coords, (list, tuple)) and len(coords) == 3:
        values = coords
    else:
        return None
    try:
        x, y = int(values[0]), int(values[1])
        z = 0 if values[2] == "Surface" else 1 if values[2] == "Underground" else int(values[2])
    except (TypeError, ValueError):
        return None
    return (x, y, z) if 0 <= x < size and 0 <= y < size and 0 <= z < levels else None


def _hero_track_traces(heroes, player, selected_day, selected_heroes, colors,
                       mask, pixel_size, gap):
    if (heroes is None or not selected_heroes or
            not {"player_color", "hero_name", "day", "coords"}.issubset(heroes.columns)):
        return []
    size, levels = mask.shape[1], mask.shape[0]
    days = pd.to_numeric(heroes["day"], errors="coerce")
    records = heroes[(heroes["player_color"] == player) &
                    (heroes["hero_name"].isin(selected_heroes)) &
                    (days <= selected_day)].copy()
    records = records.sort_values("day", kind="stable").drop_duplicates(
        ["hero_name", "day"], keep="last")
    traces = []
    for name in colors:
        if name not in selected_heroes:
            continue
        history = records[records["hero_name"] == name]
        if history.empty:
            continue
        points = []
        for _, row in history.iterrows():
            position = _hero_position(row["coords"], size, levels)
            if position is None:
                points.append(None)
                continue
            x, y, z = position
            points.append((int(row["day"]), x, y, z) if mask[z, y, x] else None)
        for level in range(levels):
            xs, ys, labels = [], [], []
            previous_day = None
            x_offset = level * (size * pixel_size + gap)
            for point in points:
                if point is None or point[3] != level:
                    previous_day = None
                    continue
                day, x, y, _ = point
                if previous_day is not None and day != previous_day + 1:
                    xs.append(None)
                    ys.append(None)
                    labels.append(None)
                elif previous_day is None and xs:
                    xs.append(None)
                    ys.append(None)
                    labels.append(None)
                xs.append(x_offset + x * pixel_size + pixel_size / 2)
                ys.append(y * pixel_size + pixel_size / 2)
                labels.append(f"{name} · Day {day} · "
                              f"{'Surface' if level == 0 else 'Underground'} ({x}, {y})")
                previous_day = day
            if xs:
                if any(xs[index - 1] is not None and xs[index] is not None
                       for index in range(1, len(xs))):
                    traces.append(go.Scatter(
                        x=xs, y=ys, mode="lines",
                        line=dict(color="rgba(0,0,0,0.85)", width=7),
                        hoverinfo="skip", connectgaps=False, showlegend=False,
                    ))
                traces.append(go.Scatter(
                    x=xs, y=ys, text=labels, mode="lines+markers",
                    line=dict(color=colors[name], width=3),
                    marker=dict(color=colors[name], size=9,
                                line=dict(color="#181818", width=1)),
                    hovertemplate="%{text}<extra></extra>",
                    connectgaps=False, showlegend=False,
                ))
    return traces


def fog_of_war_figure(player, day, fog, towns, utopias, size, levels,
                      player_color, visibility_offset="unknown", renderer=None,
                      hero_history=None, selected_heroes=None, hero_colors=None):
    """Render explored terrain safely, or use the original colored-grid view."""
    size, levels = int(size), int(levels)
    expected = size * size * levels
    if (size <= 0 or levels <= 0 or not isinstance(fog, str) or
            len(fog) != expected or set(fog) - {"0", "1"}):
        return go.Figure()

    mask = np.fromiter((value == "1" for value in fog), dtype=bool, count=expected)
    mask = mask.reshape((levels, size, size))
    pixel_size = OVERVIEW_TILE_SIZE if renderer is not None else 4
    gap = pixel_size * 5
    rgb = tuple(int(player_color.lstrip("#")[index:index + 2], 16)
                for index in (0, 2, 4))
    contrast = "white" if sum(a * b for a, b in zip(rgb, (0.299, 0.587, 0.114))) < 140 else "black"
    marker_color = "white" if renderer is not None else contrast
    marker_background = "rgba(0,0,0,0.65)" if renderer is not None else None
    traces = []
    annotations = []

    for level in range(levels):
        x_offset = level * (size * pixel_size + gap)
        if renderer is not None:
            # The renderer clips every terrain and scenery pixel to this mask
            # before encoding the PNG. The browser never receives hidden tiles.
            traces.append(go.Image(source=renderer.render_overview_data_url(
                                       mask, level, tile_size=pixel_size),
                                   x0=x_offset, y0=0, dx=1, dy=1,
                                   hoverinfo="skip"))
        else:
            grid = np.where(mask[level, :, :, None], rgb, (200, 200, 200)).astype(np.uint8)
            enlarged = np.repeat(np.repeat(grid, pixel_size, axis=0), pixel_size, axis=1)
            traces.append(go.Image(z=enlarged, x0=x_offset, y0=0, hoverinfo="skip"))

        def mark(x, y, symbol):
            if not (0 <= x < size and 0 <= y < size and mask[level, y, x]):
                return
            annotations.append(dict(
                x=x_offset + x * pixel_size + pixel_size / 2,
                y=y * pixel_size + pixel_size / 2,
                text=symbol, showarrow=False,
                font=dict(size=18, color=marker_color, family="Arial Black"),
                bgcolor=marker_background, borderpad=2,
                xanchor="center", yanchor="middle",
            ))

        if utopias is not None and not utopias.empty:
            level_utopias = utopias[utopias["underground"] == (level == 1)]
            for _, utopia in level_utopias.iterrows():
                try:
                    mark(int(utopia["X"]), int(utopia["Y"]), "X")
                except (TypeError, ValueError, KeyError):
                    continue

        for town in towns if isinstance(towns, list) else []:
            try:
                x, y, town_level = town["coords"]
                if ((town_level == "Surface" and level == 0) or
                        (town_level == "Underground" and level == 1)):
                    mark(int(x), int(y), "■")
            except (TypeError, ValueError, KeyError):
                continue

        annotations.append(dict(
            x=x_offset + size * pixel_size / 2, y=-15,
            text="Ground" if level == 0 else "Underground",
            showarrow=False, font=dict(size=16, color="black"),
            xanchor="center", yanchor="bottom",
        ))

    traces.extend(_hero_track_traces(hero_history, player, day, selected_heroes or [],
                                     hero_colors or hero_track_colors(hero_history, player),
                                     mask, pixel_size, gap))
    figure = go.Figure(data=traces)
    figure.update_layout(
        title=f"Fog of War - {player} - Day {day} "
              f"(map size: {size}, visibility offset: {visibility_offset})",
        yaxis=dict(scaleanchor="x", autorange="reversed", visible=False),
        xaxis=dict(visible=False), annotations=annotations,
        dragmode="pan", margin=dict(t=50, l=0, r=0, b=0),
        autosize=True,
    )
    return figure
