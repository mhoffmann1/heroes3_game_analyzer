import argparse
import json
import os
import h3tools
import re
import math
import logging
import sys
from tqdm import tqdm

import h3tools.metadata as metadata

logger = logging.getLogger(__name__)
logging.basicConfig(filename='h3parser.log', encoding='utf-8', level=logging.DEBUG)

def load_savegame(file_path):
    """Load a Heroes 3 savegame file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Savegame file '{file_path}' not found.")
    return h3tools.Savefile(file_path)

def parse_game_info(mapdata, towns):
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
    
    # Add town data
    try:
        game_info["towns"] = towns
        #logger.debug("Parsed %d towns: %s", len(towns), [t["name"] for t in towns])
    except (AttributeError, TypeError, KeyError) as e:
        logger.warning("Failed to parse town data: %s", e)
    
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
            logger.warning("AI Value not found for unit '%s'", unit_name)
        total_ai_value += ai_value * unit_count
    
    # Army strength = total AI Value * H
    return round(total_ai_value * H, 2)

def extract_game_data(save, ai_values):
    """Extract stats for all heroes and towns in the savegame."""
    heroes = []

    try:
        for i, hero in enumerate(save.heroes):
            try:
                # Get stats dictionary
                stats = getattr(hero, "stats", {})
                # Get spells available in spell book
                spells = getattr(hero, "spells", {})

                ARTIFACT_SPELLS = metadata.Store.get("artifact_spells", version='hota')
                #artifact_spells0 = set(y for x in hero.original.get("equipment", {}).values()
                #           for y in ARTIFACT_SPELLS.get(x, [])) if hero else set()
                artifact_spells  = set(y for x in hero.equipment.values()
                           for y in ARTIFACT_SPELLS.get(x, [])) if hero else set()
                #print(artifact_spells)
                
                # Get hero name and faction
                hero_name = getattr(hero, "name", "Unknown")
                
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
                    "owner": hero.owner,
                    "army": army,
                    "army_strength": army_strength,
                    "spells": list(spells),
                    "artifact_spells": list(artifact_spells),
                    "has_dd": spell_known("Dimension Door", spells) or spell_known("Dimension Door", artifact_spells),
                    "has_fly": spell_known("Fly", spells) or spell_known("Fly", artifact_spells),
                    "has_tp": spell_known("Town Portal", spells) or spell_known("Town Portal", artifact_spells)                
                }
                heroes.append(hero_data)
            except AttributeError as e:
                logger.warning("Failed to extract data for hero %s: %s", getattr(hero, 'name', 'Unknown'), e)
                continue
    except AttributeError:
        raise AttributeError("Savefile object does not have 'heroes' attribute. Check h3tools library compatibility.")
    
    # Parse game info from mapdata and towns
    mapdata = getattr(save, "mapdata", {})
    towns = getattr(save, "towns", [])

    #print(f"towns: {towns}")
    for town in towns:
        army_strength = calculate_army_strength(town['garrison'], 0, 0, ai_values)
        town['army_strength'] = army_strength

    resources = getattr(save, "player_resources")
    #logger.debug("Retrieved %d towns from save.towns: %s", len(towns), [t["name"] for t in towns])
    game_info = parse_game_info(mapdata, towns)
    
    # Return both heroes and game info
    return {"heroes": heroes, "game_info": game_info, "resources": resources}

def spell_known(spell, spell_source):
    return spell in spell_source

def save_to_json(data, output_file):
    """Save hero stats and game info to a JSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logger.info("Hero stats, game info, and town data saved to '%s'", output_file)

def aggregate_player_data(json_data):
    players = {}
    colors = ['Red', 'Blue', 'Tan', 'Green', 'Orange', 'Purple', 'Teal', 'Pink', 'None']
    
    # Initialize player data structure
    for color in colors:
        players[color] = {
            'heroes': [],
            'towns': [],
            'resources': {}
        }
    
    # Aggregate heroes by owner
    for hero in json_data['heroes']:
        owner = hero['owner'] if hero['owner'] else 'None'
        if owner in players:
            players[owner]['heroes'].append(hero)
        else:
            players['None']['heroes'].append(hero)
    
    # Aggregate towns by owner
    for town in json_data['game_info']['towns']:
        owner = town['owner']
        if owner in players:
            players[owner]['towns'].append(town)
        else:
            players['None']['towns'].append(town)
    
    # Aggregate resources by color
    for resource in json_data['resources']:
        color = resource['color']
        if color in players:
            players[color]['resources'] = resource['resources']
    
    # Preserve game_info header and add total towns count
    game_info = {k: v for k, v in json_data['game_info'].items() if k != 'towns'}
    game_info['total_towns'] = len(json_data['game_info']['towns'])

    # Count number of controlled towns per player
    for player in colors:
        players[player]['town_count'] = len(players[player]['towns'])
        players[player]['total_strength'] = get_army_strenght(players[player])
    
    return {
        'game_info': game_info,
        'players': players
        
    }

def get_army_strenght(player):
    total_strength = 0.0

    for hero in player['heroes']:
        total_strength += hero['army_strength']
        
    for town in player['towns']:
        total_strength += town['army_strength']

    return round(total_strength, 2)


def main():
    parser = argparse.ArgumentParser(
        description="Extract hero stats, game info, and town data from Heroes 3 savegame(s) to JSON."
    )
    parser.add_argument(
        "input",
        help="Path to a Heroes 3 savegame file or a directory containing savegame files"
    )
    parser.add_argument(
        "--output", "-o",
        default="output_data.json",
        help="Output file prefix or directory (default: output_data)"
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    try:
        # Load AI unit values
        try:
            with open("creature_ai_values.json", "r") as f:
                ai_values = json.load(f)
        except FileNotFoundError:
            logger.error("creature_ai_values.json not found in current directory")
            sys.exit(1)
        except json.JSONDecodeError:
            logger.error("creature_ai_values.json is not a valid JSON file")
            sys.exit(1)

        input_path = args.input

        if os.path.isfile(input_path):
            # Single file mode
            logger.info(f"Processing single savegame: {input_path}")
            raw_data, player_data = process_file(input_path, ai_values, args.output)

            # Save raw data
            save_to_json(raw_data, args.output)
            logger.info(f"Raw data saved to {args.output}")

            # Save player aggregated data
            player_output = args.output.replace(".json", "_player.json")
            save_to_json(player_data, player_output)
            logger.info(f"Aggregated player data saved to {player_output}")

        elif os.path.isdir(input_path):
            # Batch processing mode
            logger.info(f"Processing savegame directory: {input_path}")
            pattern = re.compile(r"^\d{3}\.GM\d$", re.IGNORECASE)

            files = sorted([
                f for f in os.listdir(input_path)
                if pattern.match(f)
            ])

            if not files:
                logger.error("No valid savegame files found in the directory.")
                sys.exit(1)

            os.makedirs(args.output, exist_ok=True)

            all_raw_data = []
            all_player_data = []

            for filename in tqdm(files, desc="Processing saves"):
                filepath = os.path.join(input_path, filename)
                try:
                    raw_data, player_data = process_file(
                        filepath,
                        ai_values,
                        os.path.join(args.output, filename + ".json"),
                        save_individual=False
                    )

                    raw_data["filename"] = filename
                    player_data["filename"] = filename

                    all_raw_data.append(raw_data)
                    all_player_data.append(player_data)

                except Exception as e:
                    logger.error(f"Failed to process {filename}: {e}")

            combined_output = os.path.join(args.output, "combined_data.json")
            save_to_json(all_raw_data, combined_output)
            logger.info(f"Combined raw data saved to {combined_output}")

            combined_player_output = os.path.join(args.output, "combined_player_data.json")
            save_to_json(all_player_data, combined_player_output)
            logger.info(f"Combined player data saved to {combined_player_output}")

        else:
            logger.error("Input path is neither a file nor a directory.")
            sys.exit(1)

    except Exception as e:
        logger.error("Unhandled error: %s", str(e))
        sys.exit(1)


def process_file(filepath, ai_values, output_file, save_individual=True):
    save = load_savegame(filepath)
    raw_data = extract_game_data(save, ai_values)
    player_data = aggregate_player_data(raw_data)

    if save_individual:
        # Save raw data
        save_to_json(raw_data, output_file)
        #logging.info(f"Data saved to {output_file}")

        # Save player aggregated data
        player_output = output_file.replace(".json", "_player.json")
        save_to_json(player_data, player_output)
        #logging.info(f"Aggregated player data saved to {player_output}")

    return raw_data, player_data


def save_to_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    main()