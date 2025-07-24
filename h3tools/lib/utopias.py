import os
import re
import sys


class Utopia():
    def __init__(self, offset, tile, map_size):
        self.offset = offset
        self.tile = tile
        self.underground = True if offset//(map_size*map_size) else False
        self.visited_bitmask = self.get_visited_players(tile)
        self.conquered = self.check_utopia_status(tile)
        coords = offset - (map_size*map_size) if self.underground else offset
        self.x_coord = coords % map_size
        self.y_coord = coords // map_size
        self.conqueredby = None

    def get_info(self):
        info = {
            "X": self.x_coord,
            "Y": self.y_coord,
            "underground": self.underground,
            "visitedby": self.visited_bitmask,
            "conquered": self.conquered,
            "conqueredby": self.conqueredby,
        }
        return info

    def get_visited_players(self, utopia_bytes):
        def byte_to_bits_le(byte):
            return ''.join(str((byte >> i) & 1) for i in range(8))    
        le_byte1, le_byte2 = byte_to_bits_le(utopia_bytes[14]), byte_to_bits_le(utopia_bytes[15])
        visited_bitmask = (le_byte1+le_byte2)[5:-3]
        return visited_bitmask
                            
    def check_utopia_status(self, utopia_bytes):
        conquered = True if utopia_bytes[17] == 0xfe else False
        return conquered
    
    def get_new_visits(self, previous_visited, new_visited):
        changed_indices = []
        for i in range(8):
            if previous_visited[i] == '0' and new_visited[i] == '1':
                changed_indices.append(i)
        return changed_indices
    
    @staticmethod
    def is_dragon_utopia(tile: bytes) -> bool:
        if len(tile) >= 26:
            if tile[7] in [0x10] and tile[8] in [0x19]\
            and tile[24] == 0x01 and tile[25] == 0x01:
                return True
            else:
                return False

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


        
def find_tile_block_start(data: bytes) -> int:
    # Compile pattern
    pattern = re.compile(
        b'[\x00-\x0b].\x00\x00\x00\x00.\x00\x00\x00\xff\xff\xff\xff'
    )
    
    match = pattern.search(data)
    if match:
        return match.start()
    else:
        return -1  # Not found

def find_rumor_section(data: bytes, min_ascii_len: int = 20, min_zero_block_len: int = 32):
    """
    Scans binary data for a block of readable ASCII (likely the rumor string),
    followed by a long 0x00 block. Returns offset of the string and estimated
    offset after the 0x00 block (likely start of map tiles).

    :param data: Full binary data from save file.
    :param min_ascii_len: Minimum length of readable ASCII string to count as rumor.
    :param min_zero_block_len: Minimum length of 0x00 block after string.
    :return: (rumor_offset, rumor_string, map_start_candidate_offset), or None
    """

    ascii_pattern = rb'[\x20-\x7E]{' + str(min_ascii_len).encode() + rb',}'
    for match in re.finditer(ascii_pattern, data):
        rumor_str = match.group().decode(errors='ignore')
        start = match.start()
        end = match.end()

        # Check for long block of 0x00 following
        zero_count = 0
        i = end
        while i < len(data) and data[i] == 0x00:
            zero_count += 1
            i += 1

        if zero_count >= min_zero_block_len:
            return start, rumor_str, i  # rumor offset, string, first byte after 0s

    return None

def main():
    if len(sys.argv) != 2:
        print("Usage: python extract_tiles.py <filename>")
        return

    with open(sys.argv[1], 'rb') as f:
        data = f.read()

    
    # Uncomment for full functionality
    save = load_savegame(sys.argv[1])
    #mapdata = getattr(save, "mapdata", {})
    #game_info = parse_game_info(mapdata)
    #map_size = int(game_info['map_size'])
    #map_levels = int(game_info['levels'])
    
    
    # Temp hardcoded value
    map_size = 36
    map_levels = 1

    tile_section_start = find_tile_block_start(save.raw)

    print(f"Map section starts at {tile_section_start}")
    #print(f"Map section starts alt at {test}")


    tiles = extract_tiles(save.raw, map_size, map_levels, tile_section_start)

    if not tiles:
        print("❌ No valid tiles found.")
    else:
        print(f"✅ Found {len(tiles)} tiles:")
        #last_offset = None
        utopias = []
        for idx, (offset, tile, size) in enumerate(tiles):
            print(f"Tile {idx} @ offset {offset} ({size} bytes): {tile.hex()}")
            if is_dragon_utopia(tile):
                utopia = {
                    'offset': idx,
                    'tile': tile,
                    'underground': True if idx//(map_size*map_size) else False,
                    'visited_bitmask': get_visited_players(tile),
                    'conquered': check_utopia_status(tile)
                }
                utopias.append(utopia)


    #print(f"Map info:\n {game_info}")
    print(f"\n🐉 Total Dragon Utopias found: {len(utopias)}")
    for utopia in utopias:
        #print(f"Utopia offset: {utopia['offset']}, mapsize: {map_size}")
        coords = utopia['offset'] - (map_size*map_size) if utopia['underground'] else utopia['offset']
        x_coord = coords % map_size
        y_coord = coords // map_size
        #visited = get_visited_players(utopia['tile'])
        print(
            f"Utopia at offset {utopia['offset']:06d} | "
            f"X: {x_coord:03d} | "
            f"Y: {y_coord:03d} | "
            f"Underground: {str(utopia['underground']):<5} | "
            f"Tile: {utopia['tile'].hex():<60}"
            f"Visited by players: {utopia['visited_bitmask']} "
            f"Conquered: {utopia['conquered']}"
        )

    for utopia in utopias:
        print(f"Extracted from tiles: {get_visited_players(tiles[utopia['offset']][1])}, status: {check_utopia_status(tiles[utopia['offset']][1])}\n")

if __name__ == "__main__":
    main()
