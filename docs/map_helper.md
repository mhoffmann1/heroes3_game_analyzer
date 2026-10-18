# Map Helper: user guide

Map Helper is a standalone browser app for a processed Heroes III game. It
shows the selected player's explored map from the latest processed save, with
pins for places you want to remember. It is launched separately and does not
appear in the dashboard.

## Start the app

1. From the repository root, [set up the Python environment](../README.md#environment-setup)
   if you have not already done so.
2. Process the game's saves. The [desktop launcher](../README.md#desktop-launcher-and-live-dashboard)
   can do this and monitor the save folder for new turns. Find the resulting
   directory under `processed_games/`; it must contain
   `combined_player_data.json`.
3. Start Map Helper with the player you are playing:

   ```bash
   venv_heroes/bin/python map_helper_app.py "processed_games/YOUR_GAME" --player Blue
   ```

4. Open <http://127.0.0.1:8051/> in your browser. Stop the app with `Ctrl+C`
   in the terminal.

`--player` is required and accepts the player's color without regard to case.
That player stays selected for the whole session. To view another player, stop
the app and start it again with a different `--player` value. If port 8051 is
in use, add `--port 8052` and open the corresponding address.

For map graphics and automatic map-object pins, Map Helper needs the matching
original `.h3m` map and the Heroes III installation's `Data` archives. It
searches the installation's `random_maps/` and `Maps/` folders. If it cannot
find the installation from the processed game's source-save location, supply
it explicitly:

```bash
venv_heroes/bin/python map_helper_app.py "processed_games/YOUR_GAME" \
  --player Blue --game-dir "/path/to/HoMM 3 Complete"
```

The map editor is not required. If graphics are unavailable, the app shows an
exploration grid. `--no-graphics` forces that grid; it also disables pins read
from the original map, such as portals, bonus sites, and Dragon Utopias. Town
pins still come from the processed saves. Run
`venv_heroes/bin/python map_helper_app.py --help` for all startup options.

## Use the map and pins

- Choose **Surface** or **Underground** in the Level menu. Drag the map to pan
  and use the mouse wheel to zoom. Covered tiles remain hidden.
- The **Pins** list is on the right. Every category starts collapsed. Open a
  category to see its pins and count. A row reads, for example,
  `Dragon Utopia - Underground (114/100)`. Click a row to switch to its level
  and center the map on that pin.
- To add a manual pin, click an **explored** map tile, enter a title, choose a
  type, optionally add notes, and select **Save pin**. Manual types are
  **Artifact**, **Joining units**, **Stat increase**, **Resource**, and
  **Other**. Each type has a fixed color.
- To change or remove a manual pin, open its category and click its row. Edit
  its details and select **Save pin**, or select **Delete pin**. Clicking the
  map chooses a tile for a new pin; use the sidebar row to edit an existing one.

Automatic pins are read-only. The app adds them only on tiles explored by the
chosen player:

| Category | Where it comes from |
| --- | --- |
| Town | Towns in processed saves, including discovered neutral and rival towns |
| Portal, Underground gate | Monoliths, portals, and gates in the matched map; portal names include their color |
| Stat increase | Primary-stat visit sites, including Colosseum of the Magi and specified primary-stat Scholars |
| Morale, Luck, Morale and luck | Visit sites with those effects |
| Dragon Utopia | Dragon Utopia locations in the matched map |

The original map does not tell the app whether a Dragon Utopia has been
cleared in the current game. Some objects have conditional or random rewards;
their pin names identify the site, rather than promising a specific outcome.
Custom event rewards, Pandora's Boxes, and random-reward Scholars are not
detected automatically. You can mark other points of interest with a manual
pin.

Manual pins are stored in `map_pins.json` in the processed game's directory.
They are separate for each player and survive app restarts. Automatic pins are
generated from the latest data and are not saved in that file.

## New turns and missing updates

Map Helper checks `combined_player_data.json` every five seconds. When the
analyzer processes a new save, the explored map and visible pins update
automatically. The app does **not** process raw `.GM*` saves itself. Keep the
desktop launcher's save monitoring enabled, or process the game again after a
new save is created.

If the map does not advance, check that the processed game's
`combined_player_data.json` has been updated. If the app shows only an
exploration grid or omits automatic map-object pins, check the startup message
for a missing installation or unmatched `.h3m` map. Pass `--game-dir` if the
installation was not found automatically.
