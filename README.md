

## How to run

To decompress single save for manual analysys:

```bash
python decompress_gm.py saves/red_3cities.GM2 -o saves/red_3cities.bin
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
python dashboard.py 2024_11_05/ --port 8080
```

## Current state

244.GM2 - Reads player resources correct, but uses know offsets instead of dynamic ones. No other save file will work


## To do


## issues

Warning: AI Value not found for unit 'Leprechaun'



## Ideas

Percentage of map discovered
 - substract tiles that cannot be traversed
Map discovery animation
