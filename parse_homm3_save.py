import json
import os
import argparse
import struct

def parse_homm3_save(filename, output_json_path):
    """
    Parse a decompressed HoMM3 HotA 1.7.2 save file to extract hero and town data.
    
    Args:
        filename (str): Path to the decompressed .bin file
        output_json_path (str): Path to save the parsed data as JSON
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Verify input file exists
        if not os.path.isfile(filename):
            print(f"Error: Input file {filename} does not exist")
            return False

        # Read the decompressed file
        with open(filename, "rb") as f:
            data = f.read()

        # Verify HoMM3 header
        if len(data) < 4 or data[0:4] != b'H3SV':
            print("Error: Invalid HoMM3 save file, missing H3SV header")
            return False

        # Debug: Print first 256 bytes
        print(f"Debug: First 256 bytes:\n{data[:256].hex(' ', 16)}")

        # Parse player data (~0x46)
        players = []
        offset = 0x46
        color_map = {0: "Red", 1: "Blue", 2: "Brown", 3: "Purple", 4: "Orange", 5: "Pink", 6: "Green", 7: "Light Blue"}
        print(f"Debug: Parsing players at offset {hex(offset)}")
        for i in range(8):
            if offset >= len(data):
                print(f"Error: Truncated file at player data offset {hex(offset)}")
                break
            name = ""
            name_start = offset
            while offset < len(data) and data[offset] != 0:
                name += chr(data[offset])
                offset += 1
            offset += 1  # Skip null
            if not name:
                name = f"AI_Player_{i}"
            if offset + 1 > len(data):
                break
            color = data[offset] if data[offset] <= 7 else i
            offset += 1
            human = data[offset] if offset < len(data) else 0
            offset += 10  # Skip faction, AI settings (per h3sed)
            print(f"Debug: Found player {name}, color {color_map.get(color, color)}, human {human} at offset {hex(name_start)}")
            players.append({"name": name, "color": color, "color_name": color_map.get(color, str(color)), "index": i, "human": human})

        if not players:
            print("Warning: No players found, assuming default Red and Blue")
            players = [
                {"name": "Plejstocen", "color": 0, "color_name": "Red", "index": 0, "human": 1},
                {"name": "addy1986", "color": 1, "color_name": "Blue", "index": 1, "human": 1}
            ]
        print(f"Found {len(players)} players")

        # Map player indices
        player_colors = {p["index"]: p["color"] for p in players}
        player_names = {p["index"]: p["name"] for p in players}

        # Parse hero data (~0x2000)
        heroes = []
        offset = 0x2000
        max_heroes = 156
        creature_types = {
            0: "Pikeman", 1: "Halberdier", 10: "Centaur", 11: "Centaur Captain",
            12: "Dwarf", 13: "Battle Dwarf", 20: "Griffin", 21: "Royal Griffin",
            34: "Swordsman", 35: "Crusader", 36: "Monk", 37: "Zealot",
            40: "Cavalier", 41: "Champion", 50: "Imp", 51: "Familiar",
            60: "Skeleton", 61: "Skeleton Warrior", 144: "Nix", 145: "Nix Warrior",
            146: "Sea Serpent", 147: "Haspid", 148: "Pirate", 149: "Corsair"
        }

        print(f"Debug: Parsing heroes at offset {hex(offset)}")
        for i in range(max_heroes):
            if offset + 100 > len(data):
                print(f"Warning: Reached end of file at hero {i}, offset {hex(offset)}")
                break
            name = ""
            name_offset = offset
            while offset < len(data) and data[offset] != 0:
                try:
                    name += chr(data[offset])
                except UnicodeEncodeError:
                    break
                offset += 1
            if not name or len(name) > 30:
                print(f"Debug: Invalid hero name at offset {hex(name_offset)}")
                offset = name_offset + 100
                continue
            offset += 1
            offset += 20  # Skip to owner
            if offset + 1 > len(data):
                print(f"Error: Missing hero ownership at {hex(offset)}")
                break
            player_index = data[offset]
            if player_index > 7:
                print(f"Debug: Invalid player index {player_index} at {hex(name_offset)}")
                offset += 100
                continue
            player_color = player_colors.get(player_index, -1)
            player_name = player_names.get(player_index, "Unknown")
            offset += 1
            offset += 8  # Skip to stats
            if offset + 4 > len(data):
                print(f"Error: Missing hero stats at {hex(offset)}")
                break
            attack, defense, spell_power, knowledge = struct.unpack("BBBB", data[offset:offset+4])
            if attack > 100 or defense > 100:
                print(f"Debug: Invalid stats for hero {name} at {hex(name_offset)}")
                offset += 100
                continue
            offset += 4
            offset += 28  # Skip to army
            if offset + 28 > len(data):
                print(f"Error: Missing hero army at {hex(offset)}")
                break
            army = []
            for _ in range(7):
                if offset + 4 > len(data):
                    break
                creature_type, quantity = struct.unpack("<HH", data[offset:offset+4])
                if creature_type < 200 and quantity < 10000:
                    creature_name = creature_types.get(creature_type, f"Unknown ({creature_type})")
                    army.append({"type": creature_name, "quantity": quantity})
                offset += 4
            heroes.append({
                "name": name,
                "player_index": player_index,
                "player_name": player_name,
                "player_color": color_map.get(player_color, str(player_color)),
                "stats": {"attack": attack, "defense": defense, "spell_power": spell_power, "knowledge": knowledge},
                "army": army
            })
            offset += 20
            print(f"Debug: Found hero {name} for player {player_name} at {hex(name_offset)}")

        # Parse town data (~0x5000)
        towns = []
        offset = 0x5000
        max_towns = 48
        town_types = {0: "Castle", 1: "Rampart", 2: "Tower", 3: "Inferno", 4: "Necropolis", 5: "Dungeon", 6: "Stronghold", 7: "Fortress", 8: "Conflux", 9: "Cove"}
        print(f"Debug: Parsing towns at offset {hex(offset)}")
        for i in range(max_towns):
            if offset + 10 > len(data):
                print(f"Warning: Reached end of file at town {i}, offset {hex(offset)}")
                break
            owner = data[offset]
            if owner == 0xff:
                offset += 200
                continue
            if owner > 7:
                offset += 200
                continue
            town_type = data[offset + 1]
            towns.append({
                "owner_index": owner,
                "owner_name": player_names.get(owner, "Unknown"),
                "owner_color": color_map.get(owner, str(owner)),
                "type": town_types.get(town_type, f"Unknown ({town_type})")
            })
            offset += 200
            print(f"Debug: Found town type {town_types.get(town_type, town_type)} for owner {player_names.get(owner, owner)}")

        # Summarize
        red_heroes = [h for h in heroes if h["player_color"] == "Red"]
        blue_heroes = [h for h in heroes if h["player_color"] == "Blue"]
        other_heroes = [h for h in heroes if h["player_color"] not in ["Red", "Blue"]]
        red_towns = [t for t in towns if t["owner_color"] == "Red"]
        blue_towns = [t for t in towns if t["owner_color"] == "Blue"]
        other_towns = [t for t in towns if t["owner_color"] not in ["Red", "Blue"]]

        result = {
            "players": players,
            "heroes": {
                "red": red_heroes,
                "blue": blue_heroes,
                "others": other_heroes
            },
            "towns": {
                "red": red_towns,
                "blue": blue_towns,
                "others": other_towns
            },
            "file_size": len(data)
        }

        # Save JSON
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Parsed data saved to {output_json_path}")

        # Print summary
        print(f"Player 1 (Red, Plejstocen): {len(red_heroes)} heroes, {len(red_towns)} towns")
        for h in red_heroes:
            print(f"  Hero: {h['name']}, Stats: {h['stats']}, Army: {h['army']}")
        print(f"Player 2 (Blue, addy1986): {len(blue_heroes)} heroes, {len(blue_towns)} towns")
        for h in blue_heroes:
            print(f"  Hero: {h['name']}, Stats: {h['stats']}, Army: {h['army']}")
        if other_heroes:
            print(f"Other players: {len(other_heroes)} heroes")
            for h in other_heroes:
                print(f"  Hero: {h['name']}, Player: {h['player_name']}, Stats: {h['stats']}, Army: {h['army']}")
        if other_towns:
            print(f"Other towns: {len(other_towns)}")
            for t in other_towns:
                print(f"  Town: {t['type']}, Owner: {t['owner_name']}")
        return True

    except Exception as e:
        print(f"Error parsing: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse a decompressed HoMM3 HotA 1.7.2 save file")
    parser.add_argument("input_file", help="Path to the decompressed .bin file")
    parser.add_argument("--output-json", default="save_data.json", help="Path to save the parsed data as JSON")
    args = parser.parse_args()

    success = parse_homm3_save(args.input_file, args.output_json)
    if success:
        print("Parsing completed successfully.")
    else:
        print("Parsing failed.")