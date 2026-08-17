

## How to run

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

## Current state

Working for single and multiplayer games.


## To do


## issues


## Ideas
