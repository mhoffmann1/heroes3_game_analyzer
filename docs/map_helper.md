# Map Helper: user guide

Map Helper is a standalone browser app for a processed Heroes III game. It
shows the selected player's explored map from the latest processed save, with
pins for places you want to remember. It is launched separately and does not
appear in the dashboard.

## Start the app

1. From the repository root, [set up the Python environment](../README.md#environment-setup)
   if you have not already done so.
2. Start [the desktop launcher](../README.md#desktop-launcher-and-live-dashboard)
   with `venv_heroes/bin/python launcher.py`. Point it at the **raw savegame
   directory**, enable **Monitor for new or changed save files**, and select
   **Process and start dashboard**. Leave the launcher running in the background
   during play. Its output directory under `processed_games/` must contain
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
from the original map, such as portals, bonus sites, Dragon Utopias, and creatures. Town
pins still come from the processed saves. Run
`venv_heroes/bin/python map_helper_app.py --help` for all startup options.

## Use the map and pins

- Choose **Surface** or **Underground** in the Level menu. Drag the map to pan
  and use the mouse wheel to zoom. Covered tiles remain hidden.
- The **Pins** list is on the right. Every category starts collapsed. Open a
  category to see its pins and count. A row reads, for example,
  `Dragon Utopia - Underground (114/100)`. Click a row to switch to its level
  and center the map on that pin. Portal pins are ordered by color, so portals
  of the same color appear together across both map levels.
- Open a category and use **Show on map** to show or hide all its pins on
  the map. The category and its entries stay in the list, and the choice is
  remembered for this browser session. Hiding Town also hides town name labels.
  Terrain and object graphics remain visible.
- Open **Creature** to see level 1–7 subcategories. Each level has its own
  **Show on map** checkbox, so you can hide one level while keeping the others.
  All creature pins use the same color.
- Choose a hero in **Track stat visits for hero**. Open **Stat increase** and
  select a discovered automatic site, or click its map marker, then use **Mark
  visited**. Marked sites have an open-circle pin and a visited label in the
  list. **Hide objects already visited by this hero** removes those pins from
  the map while leaving them in the list so you can select and unmark them.
  Changing heroes shows that hero's own marked visits. Manual Stat increase
  pins cannot be marked visited.
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
| Morale and Luck | Visit sites that affect morale, luck, or both; each pin's notes identify its effect |
| Dragon Utopia | Dragon Utopia locations in the matched map |
| Creature | Neutral creature stacks still present in the latest processed save; nested level 1–7 groups contain base and upgraded creatures of the same level |

When map graphics are available, towns, Dragon Utopias, and Stat increase sites
also appear with their game sprites on the rendered terrain. Town sprites are
matched against the towns in the latest save; their name pins still come from
processed saves. Fog still covers every
unexplored tile, including any hidden part of a sprite. Hiding a pin leaves its
terrain object visible. These sprites come from the original map, so a
one-time Scholar may still appear after it has been collected.

The original map does not tell the app whether a Dragon Utopia has been
cleared in the current game. Some objects have conditional or random rewards;
their pin names identify the site, rather than promising a specific outcome.
Creature pins disappear after their stacks are removed from a processed save.
Their names identify the original creature type; the pin does not show stack
size or whether the creatures will join a hero. Random creature placeholders
whose type cannot be identified are omitted. Special neutral dragons are shown
with level 7 so every known stack fits the seven-level view. Creatures with an
unknown level appear under **Unknown level** inside Creature.
Custom event rewards, Pandora's Boxes, and random-reward Scholars are not
detected automatically. You can mark other points of interest with a manual
pin.

Manual pins are stored in `map_pins.json` in the processed game's directory.
They are separate for each player and survive app restarts. Automatic pins are
generated from the latest data and are not saved in that file.
Hero stat-site visits are stored separately in `map_stat_visits.json` in the
same directory. These are **user-confirmed marks**: the processed saves do not
contain a reliable per-hero visit history. An unmarked site means its visit
status is unknown, not that the hero definitely has not visited it. New heroes
appear in the dropdown when a new processed turn is loaded.

## New turns and missing updates

There are two steps to an automatic update: the running desktop launcher watches
the **raw savegame directory** and processes a new or changed `.GM*` save into
`combined_player_data.json`; Map Helper checks that processed file every five
seconds and then updates the explored map and visible pins, including current
creature stacks. Map Helper does
**not** process raw saves itself. If the launcher is closed or monitoring is
disabled, run the save processor again manually before expecting Map Helper to
advance.

If the map does not advance, check that the processed game's
`combined_player_data.json` has been updated. If the app shows only an
exploration grid or omits automatic map-object pins, check the startup message
for a missing installation or unmatched `.h3m` map. Pass `--game-dir` if the
installation was not found automatically.
