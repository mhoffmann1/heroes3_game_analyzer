import argparse
import json
import os
import h3sed
import re
import math

# Hero-to-faction mapping (expanded for Horn of the Abyss)
HERO_FACTION_MAP = {
    "Adela": "Castle",
    "Cyra": "Tower",
    "Christian": "Castle",
    "Gelu": "Rampart",
    "Dracon": "Tower",
    "Orrin": "Castle",
    "Cuthbert": "Castle",
    "Tazar": "Fortress",
    "Alkin": "Fortress",
    "Corkes": "Cove",
    # Add more heroes as needed
}

def load_savegame(file_path):
    """Load a Heroes 3 savegame file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Savegame file '{file_path}' not found.")
    try:
        return h3sed.Savefile(file_path)
    except AttributeError:
        raise ImportError("Could not find Savefile class in h3sed. Check library version or installation.")

def parse_game_info(mapdata):
    """Parse mapdata['name'] and ['desc'] to extract game information."""
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
        "expansion": ""
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

def calculate_army_strength(army, attack_skill, defense_skill, ai_values):
    """Calculate army strength: sum(AI_Value * count) * H, where H = sqrt((1 + 0.05 * A) * (1 + 0.05 * D))."""
    # Calculate hero strength (H)
    H = math.sqrt((1 + 0.05 * attack_skill) * (1 + 0.05 * defense_skill))
    
    # Sum AI Values * counts
    total_ai_value = 0
    for unit in army:
        unit_name = unit.get("name", "")
        unit_count = unit.get("count", 0)
        ai_value = ai_values.get(unit_name, 0)  # Default to 0 if unit not found
        if ai_value == 0:
            print(f"Warning: AI Value not found for unit '{unit_name}'")
        total_ai_value += ai_value * unit_count
    
    # Army strength = total AI Value * H
    return round(total_ai_value * H, 2)

def extract_hero_stats(save, ai_values):
    """Extract stats for all heroes in the savegame."""
    heroes = []
    try:
        for i, hero in enumerate(save.heroes):
            try:
                # Get stats dictionary
                stats = getattr(hero, "stats", {})
                
                # Get hero name and faction
                hero_name = getattr(hero, "name", "Unknown")
                hero_faction = HERO_FACTION_MAP.get(hero_name, "Unknown")
                
                # Get army, filtering out empty slots
                army = [
                    {"name": unit["name"], "count": unit["count"]}
                    for unit in getattr(hero, "army", [])
                    if unit and unit.get("name")
                ]
                
                # Get primary skills for army strength calculation
                attack_skill = stats.get("attack", 0)
                defense_skill = stats.get("defense", 0)
                
                # Calculate army strength
                army_strength = calculate_army_strength(army, attack_skill, defense_skill, ai_values)
                
                hero_data = {
                    "name": hero_name,
                    "level": stats.get("level", 0),
                    "experience": stats.get("exp", 0),
                    "primary_skills": {
                        "attack": attack_skill,
                        "defense": defense_skill,
                        "spell_power": stats.get("power", 0),
                        "knowledge": stats.get("knowledge", 0)
                    },
                    "secondary_skills": [
                        {"name": skill.name, "level": skill.level}
                        for skill in getattr(hero, "skills", [])
                        if hasattr(skill, "name") and skill.name
                    ],
                    "faction": hero_faction,
                    "owner": "Unknown",
                    "army": army,
                    "army_strength": army_strength
                }
                heroes.append(hero_data)
            except AttributeError as e:
                print(f"Warning: Failed to extract data for hero {getattr(hero, 'name', 'Unknown')}: {e}")
                continue
    except AttributeError:
        raise AttributeError("Savefile object does not have 'heroes' attribute. Check h3sed library compatibility.")
    
    # Parse game info from mapdata
    mapdata = getattr(save, "mapdata", {})
    game_info = parse_game_info(mapdata)
    
    # Return both heroes and game info
    return {"heroes": heroes, "game_info": game_info}

def save_to_json(data, output_file):
    """Save hero stats and game info to a JSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Hero stats and game info saved to '{output_file}'")

def main():
    parser = argparse.ArgumentParser(description="Extract hero stats and game info from Heroes 3 savegame to JSON.")
    parser.add_argument("savegame", help="Path to the Heroes 3 savegame file")
    parser.add_argument("--output", "-o", default="hero_stats.json",
                        help="Output JSON file (default: hero_stats.json)")
    args = parser.parse_args()

    try:
        # Load AI values from creature_ai_values.json
        try:
            with open("creature_ai_values.json", "r") as f:
                ai_values = json.load(f)
        except FileNotFoundError:
            print("Error: creature_ai_values.json not found in current directory")
            exit(1)
        except json.JSONDecodeError:
            print("Error: creature_ai_values.json is not a valid JSON file")
            exit(1)

        # Load savegame
        save = load_savegame(args.savegame)
        
        # Extract hero stats and game info
        data = extract_hero_stats(save, ai_values)
        
        # Save to JSON
        save_to_json(data, args.output)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()