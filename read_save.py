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
from h3tools.lib.utopias import Utopia, UtopiaTracker



logger = logging.getLogger('h3_analyzer')

#logger = logging.getLogger(__name__)
#logging.basicConfig(filename='h3parser.log', encoding='utf-8', level=logging.DEBUG)


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
        "towns": [],
        "total_utopias": 0
    }
    
    # Parse mapdata['name'] for player names, game date, and template
    name_data = mapdata.get("name", "")
    if name_data:
        try:
            # Split on control chars, keep meaningful text
            parts = re.split(r'\x01|\x02', name_data)
            parts = [p.strip() for p in parts if p.strip() and p != '\x12']
    
            if len(parts) >= 3:
                # Last two fields are always date and template
                game_info["template"] = parts[-1]
                game_info["game_date"] = parts[-2].replace(";", ":")
                game_info["player_names"] = parts[:-2]  # Everything before is player names
            elif parts:
                game_info["player_names"] = parts
        except (AttributeError, TypeError):
            pass
    
    # Parse mapdata['desc'] for map name and other details
    desc_data = mapdata.get("desc", "")
    if desc_data:
        print(f"Game info: {desc_data}")
        # Extract map name
        try:
            map_name_match = re.search(r"Template was[^,]*", desc_data)
            if map_name_match:
                game_info["map_name"] = map_name_match.group(0)
        except (AttributeError, TypeError):
            pass
        
        # Extract number of human and computer players
        game_info["human_players"] = mapdata.get("humans")
        game_info["computer_players"] = mapdata.get("computers")
        #try:
        #    human_match = re.search(r'humans (\d+)', desc_data, re.IGNORECASE)
        #    if human_match:
        #        game_info["human_players"] = int(human_match.group(1))
        #    comp_match = re.search(r'computers (\d+)', desc_data, re.IGNORECASE)
        #    if comp_match:
        #        game_info["computer_players"] = int(comp_match.group(1))
        #except (AttributeError, TypeError):
        #    pass
        
        # Extract player town choices (e.g., 'red town choice is tower')
        try:
            matches = re.findall(r"(red|blue) town choice is (\w+)", desc_data, re.IGNORECASE)
            game_info["player_towns"] = {player.lower(): faction.capitalize() for player, faction in matches}
        except (AttributeError, TypeError):
            pass
        
        # Extract other details
        game_info["map_size"] = mapdata.get("size")
        game_info["levels"] = mapdata.get("levels")
        game_info["water"] = mapdata.get("water")
        game_info["monsters"] = mapdata.get("monsters")
        try:
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

def extract_game_data(save, ai_values, dragon_utopia_state):
    """Extract stats for all heroes and towns in the savegame."""
    heroes = []

    #print(f"Test what I have: {save.maptiles}")

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
    
    # Utopia data:
    # If dragon_utopia_state is empty - then extract info from map tiles and put into dragon_utopia_state
    # If dragon_utopia_state is not empty, extract only the tiles from map that contain dragon utopias and update dragon_utopia_state

    tracker = UtopiaTracker()

    if not dragon_utopia_state:
        logger.info(f"Extracting Dragon Utopias from map files...")
        
        if not save.maptiles:
            logger.info("No valid map tiles found.")
        else:
            logger.debug(f"Checking {len(save.maptiles)} tiles.")
        for idx, (offset, tile, size) in enumerate(save.maptiles):
            #logger.debug(f"Tile {idx} @ offset {offset} ({size} bytes): {tile.hex()}")
            if Utopia.is_dragon_utopia(tile):
                utopia = Utopia(idx,tile,save.mapdata['size'])
                dragon_utopia_state.append(utopia)

        game_info['total_utopias'] = len(dragon_utopia_state)

        logger.info(f"Utopias found: {len(dragon_utopia_state)}")

        # Run this to see Dragon Utopia details on map
        # Should go to logs
        for utopia in dragon_utopia_state:
            logger.debug(f"Utopia: {utopia.get_info()}")
    else:
        for index, utopia in enumerate(dragon_utopia_state):

        # Check if Utopia become conquered, if yes check the visited status (if changed from previous state). If unganched and visited by only 1 player: assign this player
        # Otherwise mark Utopia as conquered by unknown (the 9th player)
        # Logic for applying Player to Utopia if he concuered it

        #Continue from here!!!
            visited_this_turn = Utopia.get_visited_players(save.maptiles[utopia.offset][1])
            conquered = Utopia.check_utopia_status(save.maptiles[utopia.offset][1])
            if conquered != utopia.conquered:
                logger.info(f"Utopia at {utopia.x_coord}, {utopia.y_coord} was looted this turn.")
                dragon_utopia_state[index].conquered = conquered
                # Check who conquered utopia:
                # 1. Was there new visitor?
                if visited_this_turn != utopia.visited_bitmask:
                    new_visitor =  find_single_new_bit(utopia.visited_bitmask, visited_this_turn)
                    if new_visitor < 8:
                        tracker.increment(new_visitor)
                        dragon_utopia_state[index].conqueredby = new_visitor
                        logger.info(f"Player {new_visitor} conquered Utopia at {utopia.x_coord}, {utopia.y_coord}")
                    else:
                        logger.info(f"Two or more players visited same Utopia in the same turn, unable to determine who conquered it")
                    dragon_utopia_state[index].visited_bitmask = visited_this_turn
                else:
                # 2. If no new visitor, check if there is only one visitor
                    old_visitor = find_single_one(utopia.visited_bitmask)
                    if old_visitor < 8:
                        tracker.increment(old_visitor)
                        dragon_utopia_state[index].conqueredby = old_visitor
                        logger.info(f"Player {old_visitor} conquered Utopia at {utopia.x_coord}, {utopia.y_coord}")
                    else:
                        logger.info(f"There are 2 or more players that already had access to conquered Utopia, unable to determine who conquered it")
                 
    # Return both heroes and game info
    return {"heroes": heroes, "game_info": game_info, "resources": resources}, tracker 

def find_single_one(bitmask: str) -> int | None:
    """
    Takes an 8-character string of '0' and '1'.
    If there's exactly one '1', returns its index (0-based).
    Otherwise, returns 8.
    """
    count = bitmask.count('1')
    if count == 1:
        return bitmask.index('1')
    return 8

def find_single_new_bit(previous: str, current: str) -> int | None:
    """
    Returns the index where a single bit changed from '0' to '1'.
    If more than one such change occurred, return None.

    :param previous: Original 8-bit string (e.g., '00101000')
    :param current: New 8-bit string (e.g., '10111000')
    :return: Index of the new '1' or None
    """
    diffs = [i for i in range(8) if previous[i] == '0' and current[i] == '1']
    return diffs[0] if len(diffs) == 1 else 8


def spell_known(spell, spell_source):
    return spell in spell_source

def save_to_json(data, output_file):
    """Save hero stats and game info to a JSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logger.info("Hero stats, game info, and town data saved to '%s'", output_file)

def aggregate_player_data(json_data, utopia_tracker):

# ----->>>> You are here
    # include data from utopa_tracker to player instance so it is written as json

    players = {}
    colors = ['Red', 'Blue', 'Tan', 'Green', 'Orange', 'Purple', 'Teal', 'Pink', 'None']

    
    visited_utopias_summary = utopia_tracker.as_dict()
    logger.info(f"Tracker data acquired for players: {visited_utopias_summary}")
    
    # Initialize player data structure
    for color in colors:
        players[color] = {
            'heroes': [],
            'towns': [],
            'visited_utopias': 0,
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
    
    # Aggregate resources and map exploration info by color
    for resource in json_data['resources']:
        color = resource['color']
        if color in players:
            players[color]['resources'] = resource['resources']
            players[color]['tiles_explored'] = resource['tiles_explored']
            players[color]['fog_of_war'] = resource['fog_of_war']
    
    # Preserve game_info header and add total towns count
    game_info = {k: v for k, v in json_data['game_info'].items() if k != 'towns'}
    game_info['total_towns'] = len(json_data['game_info']['towns'])

    # Count number of controlled towns per player
    for player in colors:
        players[player]['town_count'] = len(players[player]['towns'])
        players[player]['total_strength'] = get_army_strenght(players[player])
        if player != 'None':
            players[player]['visited_utopias'] = visited_utopias_summary[player]
    
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

def setup_logger(logfile):
    logger = logging.getLogger('h3_analyzer')
    logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)

    # File handler
    file_handler = logging.FileHandler(logfile, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # Add handlers if not already added
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger

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

    logger = setup_logger('h3_analyzer.log')
    #logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    #logger = logging.getLogger(__name__)

    utopia_tracker = UtopiaTracker()

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
        dragon_utopia_state = []

        if os.path.isfile(input_path):
            # Single file mode
            logger.info(f"Processing single savegame: {input_path}")
            raw_data, player_data = process_file(input_path, ai_values, dragon_utopia_state, args.output, utopia_tracker)

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
            #dragon_utopia_state = []

            for filename in tqdm(files, desc="Processing saves"):
                filepath = os.path.join(input_path, filename)
                try:
                    raw_data, player_data = process_file(
                        filepath,
                        ai_values,
                        dragon_utopia_state,
                        os.path.join(args.output, filename + ".json"),
                        utopia_tracker,
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


def process_file(filepath, ai_values, dragon_utopia_state, output_file, utopia_tracker, save_individual=True):
    logger.debug(f"Loading save: {filepath}")
    save = load_savegame(filepath)
    logger.debug(f"Extracting game data...")
    raw_data, tracker_update = extract_game_data(save, ai_values, dragon_utopia_state)
    utopia_tracker.merge(tracker_update)
    player_data = aggregate_player_data(raw_data, utopia_tracker)

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