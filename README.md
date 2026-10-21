

## How to run

### Environment setup

The analyzer requires Python 3.10 or newer. Create the project environment and
install its direct runtime dependencies from the repository root:

```bash
python3 -m venv venv_heroes
venv_heroes/bin/python -m pip install --upgrade pip
venv_heroes/bin/python -m pip install -r requirements.txt
```

The desktop launcher also uses Python's standard `tkinter` module. On Ubuntu or
Debian systems, install it separately if it is not already available:

```bash
sudo apt install python3-tk
```

### Desktop launcher and live dashboard

Start the GUI from the repository root with the project's Python environment:

```bash
venv_heroes/bin/python launcher.py
```

In the launcher:

1. Choose the directory where Heroes III writes the game's save files.
2. Give the processed game a name and, if needed, change the dashboard port.
3. Leave **Monitor for new or changed save files** enabled for live play.
4. Click **Process and start dashboard**.

The launcher processes the existing saves and starts the dashboard. Click
**Open dashboard** when you want to view it in your browser. While monitoring
is enabled, the launcher detects new or overwritten turn saves and waits briefly
for Heroes III to finish writing the file. Newly appended turns are processed
incrementally: unchanged historical saves are read
from the cache and only the new save is parsed. If an older save is overwritten,
removed, or inserted out of order, the analyzer automatically performs a safe
full rebuild. The first run after upgrading from an older analyzer version also
builds the incremental cache once.

After processing, the launcher restarts the dashboard and open dashboard tabs
reload automatically. Use **Stop** or close the GUI to stop both monitoring and
the dashboard server.

Enable **Show Fog of War Exploration** in the dashboard to draw terrain, roads,
rivers, and static obstacles from the matching `.h3m` map and installed game
assets. Choose a player and day to see only the area explored by that player
on that day. Drag to pan and scroll to zoom. Autoplay advances one day every
1.5 seconds. When a matching map or assets are unavailable, the view falls back
to its colored exploration grid. The terrain and scenery come from the original
map, so changes to map objects during play may not appear. The standalone Map
Helper remains a separate app.

To decompress single save for manual analysys:

```bash
python decompress_gm.py saves/red_3cities.GM2 --output-bin saves/red_3cities.bin
python3.10 read_save.py /mnt/c/Users/hoffm/local_games/HoMM\ 3\ Complete/games/HotA\ Random/addy1986/2025.10.28\ 20\;45\ kerberos_x3_adv/ --output Addy_Marcin_kerbos
```

To generate json files from single savefile:

```bash
python3 read_save.py saves/244.GM2
```

To generate json files for entire game:

```bash
python3 read_save.py games/2024.11.05_2139_default -o 2024_11_05
```

To run dashboard:

```bash
python3.10 dashboard.py processed_games/Addy_Marcin_kerbos/

```

### Map Helper

Map Helper is a standalone browser app that shows one player's explored map
from a processed game. It no longer appears in the dashboard. Start it from
the repository root:

```bash
venv_heroes/bin/python map_helper_app.py "processed_games/YOUR_GAME" --player Blue
```

Open <http://127.0.0.1:8051/>. The `--player` option is required and stays
fixed until you restart the app. For automatic updates, keep `launcher.py`
running in the background with **Monitor for new or changed save files** enabled
and pointed at the **raw savegame directory**. The launcher processes each new
save into `processed_games/YOUR_GAME`; Map Helper checks that processed data
every five seconds. Running Map Helper alone does not process new saves. A
matching original map and local game assets enable terrain graphics and
automatic pins for transports, stat and morale/luck sites, and Dragon Utopias.
Town pins come from processed saves. Covered tiles stay hidden.

See the [Map Helper user guide](docs/map_helper.md) for setup, map controls,
adding and editing pins, automatic categories, startup options, and
troubleshooting. The [graphics feasibility notes](docs/map_graphics_feasibility.md)
describe how the map renderer works and its current limits.

## Transfer heroes between save files

`swap_hero.py` copies one hero from a source Heroes III: Horn of the Abyss save
into a target save. It transfers the hero's stats, army, artifacts, inventory,
spells, skills, experience, and other data, then assigns the requested owner and
places the hero on the adventure map.

The original files are not modified. The result is written to the path supplied
with `--out`.

### Requirements

- Run the script from the repository root.
- Use the project's Python environment. In this repository it is
  `venv_heroes`.
- Source and target saves should come from the same compatible HoTA/game
  version. The script refuses to copy records of different sizes.
- Hero hiring must be enabled in the target scenario, and the heroes you plan
  to import must be available in its hero pool.
- The destination map tile must be empty.
- Only surface placement (`--set-z 0`) is currently supported.

Back up important saves before testing modified files in the game.

The repository includes `arena.GM4`, a known-good target save with hero hiring
enabled. It was successfully tested with heroes assigned to Red, Blue, and Tan
for three consecutive playable turns. Keep this file unchanged and write each
result to a different `--out` path.

### Basic command

```bash
venv_heroes/bin/python swap_hero.py \
  --input SOURCE_SAVE.GM4 \
  --output TARGET_SAVE.GM4 \
  --hero "Hero name" \
  --set-owner Red \
  --set-x 10 \
  --set-y 10 \
  --set-z 0 \
  --out MODIFIED_SAVE.GM4
```

Arguments:

- `--input` is the source save containing the developed hero.
- `--output` is the target or base save that will receive the hero.
- `--hero` is the hero's name, matched case-insensitively.
- `--set-owner` accepts `Red`, `Blue`, `Tan`, `Green`, `Orange`, `Purple`,
  `Teal`, or `Pink`.
- `--set-x`, `--set-y`, and `--set-z` select the destination tile. All three
  must be supplied together. Coordinates are zero-based.
- `--out` is the new save file to create.

Despite its name, `--output` is an input file: it is the unmodified base save.
Only `--out` is written.

### Import multiple heroes

The script transfers one hero per run. To import several heroes, use the output
from each command as the target of the next command. Give every hero a different
empty tile.

This example uses the included `arena.GM4` target and imports Gelu, Solmyr, and
Rissa at `(10,10)`, `(11,10)`, and `(12,10)`:

```bash
venv_heroes/bin/python swap_hero.py \
  --input debug_saves/kerberos.GM2 \
  --output arena.GM4 \
  --hero Gelu --set-owner Red \
  --set-x 10 --set-y 10 --set-z 0 \
  --out arena_step1.GM4

venv_heroes/bin/python swap_hero.py \
  --input debug_saves/lipcowka.GM2 \
  --output arena_step1.GM4 \
  --hero Solmyr --set-owner Blue \
  --set-x 11 --set-y 10 --set-z 0 \
  --out arena_step2.GM4

venv_heroes/bin/python swap_hero.py \
  --input debug_saves/kerberos.GM2 \
  --output arena_step2.GM4 \
  --hero Rissa --set-owner Tan \
  --set-x 12 --set-y 10 --set-z 0 \
  --out arena_with_heroes.GM4
```

Copy the final file into the Heroes III saves directory and load it in HoTA.
The intermediate files are useful for diagnosing which transfer failed.

### Troubleshooting

- `Hero ... not found`: check the spelling and confirm that the source save
  contains that hero.
- `Hero record length mismatch`: the saves likely use incompatible game or
  HoTA versions.
- `target tile already contains object`: choose another empty coordinate.
- `variable size ... refusing to resize`: the selected tile contains additional
  map data; choose a normal empty tile.
- `already active`: that hero has already been placed in the target save.
- Save crashes while loading: confirm that hero hiring is enabled in the target
  scenario, that the hero is available there, and that every destination tile
  was empty.

Run the transfer tests with:

```bash
venv_heroes/bin/python -m unittest tests/test_swap_hero.py
```

### Hero transfer GUI

Start the graphical front end from the repository root:

```bash
venv_heroes/bin/python swap_hero_gui.py
```

Choose the source save containing the developed hero, type the hero name, and
select the new owner and an empty surface tile. The included `arena.GM4` is the
default base save. The result is always written to a separate file. To add more
than one hero, continue in the same window: after a successful transfer, the
result becomes the next arena/base save, the X coordinate advances by one, and
the GUI proposes a new numbered result filename.

## Current state

Working for single and multiplayer games.


## To do


## issues


## Ideas
