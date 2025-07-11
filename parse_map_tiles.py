import os
import re
import sys
import h3tools
import h3tools.metadata as metadata

BASE_TILE_SIZE = 22

MAP_SIZE = 72

def load_savegame(file_path):
    """Load a Heroes 3 savegame file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Savegame file '{file_path}' not found.")
    return h3tools.Savefile(file_path)

def parse_game_info(mapdata):
    """Parse mapdata['name'] and ['desc'] to extract game information, include towns."""
    game_info = {
        "map_name": "",
        "player_names": [],
        "game_date": "",
        "template": "",
        "human_players": 0,
        "computer_players": 0,
        "player_towns": {},
        "map_size": "",
        "levels": 0,
        "water": "",
        "monsters": 0,
        "expansion": "",
        "towns": []
    }
    
    # Parse mapdata['name'] for player names, game date, and template
    name_data = mapdata.get("name", "")
    if name_data:
        try:
            # Split on \x01 and \x02, filter out \x12
            parts = re.split(r'\x01|\x02', name_data)
            parts = [p.strip() for p in parts if p.strip() and p != '\x12']
            if len(parts) >= 4:
                game_info["player_names"] = [parts[0], parts[1]]  # e.g., ["Plejstocen", "addy1986"]
                game_info["game_date"] = parts[2].replace(";", ":")  # e.g., "2025.01.24 22:40"
                game_info["template"] = parts[3]  # e.g., "default"
            elif parts:
                game_info["player_names"] = parts[:2] if len(parts) >= 2 else parts
        except (AttributeError, TypeError):
            pass
    
    # Parse mapdata['desc'] for map name and other details
    desc_data = mapdata.get("desc", "")
    if desc_data:
        # Extract map name
        try:
            map_name_match = re.search(r'Template was 8XM8 Huge from pack Original template pack', desc_data)
            if map_name_match:
                game_info["map_name"] = "8XM8 Huge"
        except (AttributeError, TypeError):
            pass
        
        # Extract number of human and computer players
        try:
            human_match = re.search(r'humans (\d+)', desc_data, re.IGNORECASE)
            if human_match:
                game_info["human_players"] = int(human_match.group(1))
            comp_match = re.search(r'computers (\d+)', desc_data, re.IGNORECASE)
            if comp_match:
                game_info["computer_players"] = int(comp_match.group(1))
        except (AttributeError, TypeError):
            pass
        
        # Extract player town choices (e.g., 'red town choice is tower')
        try:
            matches = re.findall(r"(red|blue) town choice is (\w+)", desc_data, re.IGNORECASE)
            game_info["player_towns"] = {player.lower(): faction.capitalize() for player, faction in matches}
        except (AttributeError, TypeError):
            pass
        
        # Extract other details
        try:
            size_match = re.search(r'size (\d+)', desc_data, re.IGNORECASE)
            if size_match:
                game_info["map_size"] = size_match.group(1)
            levels_match = re.search(r'levels (\d+)', desc_data, re.IGNORECASE)
            if levels_match:
                game_info["levels"] = int(levels_match.group(1))
            water_match = re.search(r'water (\w+)', desc_data, re.IGNORECASE)
            if water_match:
                game_info["water"] = water_match.group(1).lower()
            monsters_match = re.search(r'monsters (\d+)', desc_data, re.IGNORECASE)
            if monsters_match:
                game_info["monsters"] = int(monsters_match.group(1))
            expansion_match = re.search(r'HotA (\d+\.\d+\.\d+)', desc_data, re.IGNORECASE)
            if expansion_match:
                game_info["expansion"] = f"Horn of the Abyss {expansion_match.group(1)}"
        except (AttributeError, TypeError):
            pass
    
    return game_info

def is_probable_tile(tile: bytes) -> bool:

    ALLOWED_TILE_6_VALUES = {
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
        0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,
        0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b,
        0x1c, 0x1d, 0x1e, 0x1f,
        0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x2b,
        0x2d, 0x2e,
        0x30, 0x32, 0x33, 0x34, 0x35, 0x37, 0x38, 0x39, 0x3a, 0x3b, 0x3c, 0x3e,
        0x40, 0x41, 0x42, 0x43,
        0x45, 0x46, 0x47, 0x48, 0x49,
        0x4a, 0x4b, 0x4d, 0x4f,
        0x50, 0x51, 0x52, 0x53, 0x55,
        0x59, 0x5a, 0x5b, 0x5c,
        0x60, 0x68,
        0x6b, 0x6c, 0x6d, 0x6e, 0x6f,
        0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f,
        0x80, 0x81, 0x82, 0x83,
        0x84, 0x85, 0x86, 0x87,
        0x89, 0x8b, 0x8c, 0x8d, 0x8e, 0x8f,
        0x90, 0x91, 0x92, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99,
        0x9a, 0x9b, 0x9c, 0x9d, 0x9e, 0x9f,
        0xa0, 0xa1, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9,
        0xaa, 0xab, 0xac, 0xae, 0xaf,
        0xb0, 0xb1, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb8, 0xb9, 0xba, 0xbb,
        0xbc, 0xbd, 0xbe, 0xbf,
        0xc0, 0xc1, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8,
        0xcb, 0xce, 0xcf,
        0xd0, 0xd1, 0xd2, 0xd3, 0xd6, 0xd7, 0xd8, 0xda, 0xdb, 0xdf,
        0xe0, 0xe1, 0xe2, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xeb, 0xec,
        0xed, 0xee, 0xef,
        0xf0, 0xf1, 0xf4, 0xf5, 0xf7, 0xf8, 0xfa, 0xfb, 0xfc, 0xfd, 0xfe, 0xff,
    }

    if len(tile) < BASE_TILE_SIZE:
        return False

    if tile[0] > 0x0F:
        return False
    if tile[1] == 0x00:
        return False
    if tile[2:6] != b'\x00\x00\x00\x00':
        if tile[7] != 0x03:
            return False
    if tile[6] not in ALLOWED_TILE_6_VALUES:
        if tile[6] == 0x00 and tile[7] == 0x01:
            return True
        else:
            if tile[6] != 0x00:
                print(f"Missing Byte 6 is {hex(tile[6])}")
            return False
    return True

def extract_tiles(data: bytes, map_size, levels, start_offset):
    BASE_TILE_SIZE = 22
    processed_tiles = 0
    max_tiles = map_size*map_size*levels
    tiles = []
    i = start_offset # 1600 offset is the minimum where the map tiles can start
    while processed_tiles < max_tiles:
        tile_base = data[i:i+BASE_TILE_SIZE]
        num_defs = tile_base[18]
        total_tile_size = BASE_TILE_SIZE + (num_defs * 4)
        tile_full = data[i:i+total_tile_size]
        tiles.append((i, tile_full, total_tile_size))
        i += total_tile_size
        processed_tiles += 1

    return tiles


def is_dragon_utopia(tile: bytes) -> bool:
    if len(tile) >= 26:
        if tile[7] == 0x10 and tile[8] in [0x19]\
            and tile[24] == 0x01 and tile[25] == 0x01:
            return True
        else:
            return False
        
def find_tile_section_start(data: bytes, min_ff_block=32) -> int:
    """
    Finds the first large block of consecutive 0xFF bytes and returns the offset
    of the first non-0xFF byte that follows it. Assumes that this marks the
    start of the map tile section.

    :param data: Raw binary data
    :param min_ff_block: Minimum number of consecutive 0xFF bytes to qualify as a block
    :return: Offset of first byte after the FF block (start of tile section)
    """
    i = 0
    length = len(data)
    while i < length:
        if data[i] == 0xFF:
            start = i
            while i < length and data[i] == 0xFF:
                i += 1
            if i - start >= min_ff_block:
                return i  # first non-FF byte after the block
        else:
            i += 1

    raise ValueError("Could not find a large FF block indicating start of map tile section.")


def main():
    if len(sys.argv) != 2:
        print("Usage: python extract_tiles.py <filename>")
        return

    with open(sys.argv[1], 'rb') as f:
        data = f.read()

    save = load_savegame(sys.argv[1])
    mapdata = getattr(save, "mapdata", {})
    game_info = parse_game_info(mapdata)
    map_size = int(game_info['map_size'])

    tile_section_start = find_tile_section_start(save.raw)
    print(f"Map section starts at {tile_section_start}")

    tiles = extract_tiles(save.raw, map_size, int(game_info['levels']), tile_section_start)

    if not tiles:
        print("❌ No valid tiles found.")
    else:
        print(f"✅ Found {len(tiles)} tiles:")
        last_offset = None
        utopias = []
        for idx, (offset, tile, size) in enumerate(tiles):
            print(f"Tile {idx} @ offset {offset} ({size} bytes): {tile.hex()}")
            if is_dragon_utopia(tile):
                utopia = {
                    'offset': idx,
                    'tile': tile,
                    'underground': True if idx//(map_size*map_size) else False
                }
                utopias.append(utopia)
            if last_offset is not None:
                expected_offset = last_offset + last_size
                if offset > expected_offset:
                    print(f"Tile {idx} @ offset {offset} ({size} bytes): {tile.hex()}")
                    print(f"⚠️  Gap of {offset - expected_offset} bytes detected between tile {idx-1} and tile {idx}!")
                    print(f'Gap bytes: {save.raw[last_offset+last_size:offset].hex()}')
            last_offset = offset
            last_size = size

    print(f"Map info:\n {game_info}")
    print(f"\n🐉 Total Dragon Utopias found: {len(utopias)}")
    for utopia in utopias:
        print(f"Utopia offset: {utopia['offset']}, mapsize: {map_size}")
        coords = utopia['offset'] - (map_size*map_size) if utopia['underground'] else utopia['offset']
        x_coord = coords % map_size
        y_coord = coords // map_size
        print(
            f"Utopia at offset {utopia['offset']:06d} | "
            f"X: {x_coord:03d} | "
            f"Y: {y_coord:03d} | "
            f"Underground: {str(utopia['underground']):<5} | "
            f"Tile: {utopia['tile'].hex():<60}"
        )

if __name__ == "__main__":
    main()
