"""Build the dashboard's player- and day-specific Fog of War figure."""

import numpy as np
import plotly.graph_objects as go

OVERVIEW_TILE_SIZE = 8


def fog_of_war_figure(player, day, fog, towns, utopias, size, levels,
                      player_color, visibility_offset="unknown", renderer=None):
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

    figure = go.Figure(data=traces)
    figure.update_layout(
        title=f"Fog of War - {player} - Day {day} "
              f"(map size: {size}, visibility offset: {visibility_offset})",
        yaxis=dict(scaleanchor="x", autorange="reversed", visible=False),
        xaxis=dict(visible=False), annotations=annotations,
        dragmode="pan", margin=dict(t=50, l=0, r=0, b=0),
        width=1000, height=800,
    )
    return figure
