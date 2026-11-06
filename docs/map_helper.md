# Map Helper: user guide

Map Helper is a standalone browser app for a processed Heroes III game. It
shows the selected player's explored map from the latest processed save, with
pins for places you want to remember. It is launched separately and does not
appear in the dashboard.

## Start the app

On Windows, use `Heroes3MapHelper.exe` from the
[Windows build](../README.md#windows-executables). Choose a processed game folder
containing `combined_player_data.json`, select the player, and click
**Start Map Helper**. Click **Open map** to view it. Leave the dashboard launcher
running if you want new saves processed automatically.

For the Python version:

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
  `Dragon Utopia - Underground (114/100)`. Click a row to select its pin and
  switch to its level without centering the map. Use **Show selected on map**
  above the map to center the map on that location. Portal pins are ordered by color, so portals
  of the same color appear together across both map levels.
  The selected location has a bright green ring and **SELECTED** label when
  it is within the current view. Its name and coordinates also appear above
  the map, so you can use **Show selected on map** if it is outside the view.
- Open a category and use **Show on map** to show or hide all its pins on
  the map. The category and its entries stay in the list, and the choice is
  remembered for this browser session. Hiding Town also hides town name labels.
  Terrain and object graphics remain visible.
- Open **Creature** to see level 1–7 subcategories. Each level has its own
  **Show on map** checkbox, so you can hide one level while keeping the others.
  All creature pins use the same color.
- Choose a hero in **Track site visits for hero**. Click a discovered automatic
  **Stat increase** or **Level increase** marker on the map to toggle its visited
  status immediately. You can also select it from either category and use the **Mark visited**
  or **Mark unvisited** button below the list. A status line names the target
  site and shows whether that hero has marked it visited. If no eligible site is
  selected, the buttons explain what to select. Marked sites have an open-circle pin and a visited label in the
  list. **Hide objects already visited by this hero** removes those pins from
  the map while leaving them in the list so you can select and unmark them.
  Changing heroes shows that hero's own marked visits. Manual pins cannot be
  marked visited.
- The selected hero's **Primary stats** panel shows current values from the
  latest processed save and a possible maximum from discovered automatic stat
  sites still unmarked for that hero. **Visited sites by type** shows
  visited/known counts and percentage bars for stat sites and Trees of Knowledge.
  Trees do not add to the primary-stat maximum. Both update after a visit is
  marked or new processed save data is loaded. Sites offering a choice count
  toward each eligible stat's individual maximum; those maxima cannot all
  necessarily be reached together. Level requirements and fees are not
  checked, and an unmarked visit is treated as available.
- Select a hero and click **Stat area of interest: Off** to turn on ranked stat
  areas. The map draws rectangles around nearby groups of discovered stat sites
  that are still unmarked for that hero; green is priority #1, blue marks later priorities,
  and a white star marks the hero's latest saved position. The list above the
  map shows each area's nearest site, site count, possible combined gain for
  Attack, Defense, Power, and Knowledge separately, priority value, and
  estimated distance. The map label shows the same gains as A/D/P/K. At choice
  sites such as Arena, the possible gains for different stats are alternatives;
  they cannot all be earned together. A site with no known bonus is excluded
  from the gains and flagged as unknown. **Show area**
  switches to its map level and frames the full cluster. Click the toggle again
  to remove the overlay. Areas are
  recomputed when the selected hero, visit marks, or processed save changes.
  Sites are merged into local clusters of up to six, with limits on the gap
  between sites and the rectangle's size. A very isolated site can remain on
  its own. Library of Enlightenment has value 3; Arena and Colosseum of the
  Magi have value 2; other stat sites have value 1. Ranking favors clusters
  with more value and sites while accounting for straight-line distance and
  the cluster's spread. It cannot account for walkable routes, obstacles, roads,
  portals, fees, or level requirements; areas on another map level receive a
  fixed travel penalty. Only discovered automatic stat sites are included.
- To add a manual pin, click an **explored** map tile, enter a title, choose a
  type, optionally add notes, and select **Save pin**. Manual types are
  **Artifact**, **Joining units**, **Stat increase**, **Resource**, and
  **Other**. Each type has a fixed color.
- To change or remove a manual pin, open its category and click its row. Edit
  its details and select **Save pin**, or select **Delete pin**. Clicking the
  map chooses a tile for a new pin; use the sidebar row to edit an existing one.
- To track a creature stack, open its **Creature** level and select **Add to
  Favourites**, or click its map marker and use **Add creature to Favourites**.
  Its marker turns gold and moves to the separate **Favourites** category. Open
  that category to enter the number of creatures and the **total** gold they
  ask for joining, then select **Save details**. Both fields are optional.
  The total above the pin list adds entered gold amounts across active
  favourites; it does not multiply them by creature counts. Use **Remove** in
  the list or **Remove from Favourites** on a selected marker to move it back
  to Creature.
  Favourites have their own **Show on map** toggle. A favourite disappears when
  its stack is absent from the latest processed save; its stored details are
  also removed so a later stack at that location does not inherit them.

Automatic pin locations and names are read-only. The app adds them only on tiles explored by the
chosen player:

| Category | Where it comes from |
| --- | --- |
| Town | Towns in processed saves, including discovered neutral and rival towns |
| Portal, Underground gate | Monoliths, portals, and gates in the matched map; portal names include their color |
| Stat increase | Primary-stat visit sites, including Colosseum of the Magi and specified primary-stat Scholars |
| Level increase | Tree of Knowledge sites that grant one hero level, sometimes for gold or gems |
| Morale and Luck | Visit sites that affect morale, luck, or both; each pin's notes identify its effect |
| Mana replenishment | Magic Wells, Magic Springs, HotA Vials of Mana, and Altars of Mana from the matched map |
| Dragon Utopia | Dragon Utopia locations in the matched map |
| Obelisk | Discovered Obelisks from the matched map; each pin shows whether the chosen player has visited it in the latest processed save |
| Creature | Neutral creature stacks still present in the latest processed save; nested level 1–7 groups contain base and upgraded creatures of the same level |
| Favourites | Creature stacks marked by the user, with gold markers and optional quantity and joining cost |

When map graphics are available, towns, Dragon Utopias, Obelisks, Stat increase sites, Level increase sites,
and mana sites
also appear with their game sprites on the rendered terrain. Town sprites are
matched against the towns in the latest save; their name pins still come from
processed saves. Fog still covers every
unexplored tile, including any hidden part of a sprite. Hiding a pin leaves its
terrain object visible. These sprites come from the original map, so a
one-time Scholar may still appear after it has been collected.
Vial of Mana pins may likewise remain after the vial has been collected;
Altar of Mana requires sacrificing creatures to receive spell points.

Obelisk pins show **Visited** or **Unvisited** for the player chosen at startup.
Visited markers use an open circle. If the saved visit table cannot be matched
to the map, the pin shows **Unknown** rather than guessing. The status updates
after a new save is processed and Map Helper refreshes its data.

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
Creature favourites and their entered details are stored per player in
`map_creature_favourites.json` in the same directory.
Hero stat-site and Tree of Knowledge visits are stored in `map_stat_visits.json` in the
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
