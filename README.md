

## How to run

To decompress single save for manual analysys:

```bash
python decompress_gm.py saves/red_3cities.GM2 -o saves/red_3cities.bin
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

## Current state

Working for single and multiplayer games.


## To do


## issues


## Ideas

