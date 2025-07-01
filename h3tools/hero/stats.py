# -*- coding: utf-8 -*-
"""
Main stats subplugin for hero-plugin, shows primary skills like attack-defense,
hero level, movement and experience and spell points, spellbook toggle,
and war machines.

------------------------------------------------------------------------------
This file is part of h3tools - Heroes3 Savegame Editor.
Released under the MIT License.

@created   16.03.2020
@modified  05.04.2025
------------------------------------------------------------------------------
"""
import functools
import logging

import h3tools
from .. lib import util
from .. import conf
from .. import metadata


logger = logging.getLogger(__package__)


PROPS = {"name": "stats", "label": "Main attributes", "index": 0}
## Valid raw values for primary stats range from 0..127.
## 100..127 is probably used as a buffer for artifact boosts;
## game will only show and use a maximum of 99.
## 128 or higher will cause overflow wraparound to 0.
DATAPROPS = [{
    "name":   "attack",
    "label":  "Attack",
    "type":   "number",
    "len":    1,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
    "info":   None,  # Populated later
}, {
    "name":   "defense",
    "label":  "Defense",
    "type":   "number",
    "len":    1,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
    "info":   None,  # Populated later
}, {
    "name":   "power",
    "label":  "Spell Power",
    "type":   "number",
    "len":    1,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
    "info":   None,  # Populated later
}, {
    "name":   "knowledge",
    "label":  "Knowledge",
    "type":   "number",
    "len":    1,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
    "info":   None,  # Populated later
}, {
    "name":   "exp",
    "label":  "Experience",
    "type":   "number",
    "len":    4,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
    "extra":  {
        "type":     "button",
        "label":    "Set from level",
        "tooltip":  "Recalculate experience points from hero level",
        "handler":  None,  # Populated later
    },
}, {
    "name":   "level",
    "label":  "Level",
    "type":   "number",
    "len":    1,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
    "extra":  {
        "type":     "button",
        "label":    "Set from experience",
        "tooltip":  "Recalculate level from hero experience points",
        "handler":  None,  # Populated later
    },
}, {
    "name":     "movement_total",
    "label":    "Movement points in total",
    "type":     "number",
    "len":      4,
    "min":      None,  # Populated later
    "max":      None,  # Populated later
    "readonly": True,
}, {
    "name":   "movement_left",
    "label":  "Movement points remaining",
    "type":   "number",
    "len":    4,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
}, {
    "name":   "mana_left",
    "label":  "Spell points remaining",
    "type":   "number",
    "len":    2,
    "min":    None,  # Populated later
    "max":    None,  # Populated later
}, {
    "name":   "spellbook",
    "type":   "check",
    "label":  "Spellbook",
    "value":  None, # Populated later
}, {
    "name":   "ballista",
    "type":   "check",
    "label":  "Ballista",
    "value":  None, # Populated later
}, {
    "name":   "ammo",
    "type":   "check",
    "label":  "Ammo Cart",
    "value":  None, # Populated later
}, {
    "name":   "tent",
    "type":   "check",
    "label":  "First Aid Tent",
    "value":  None, # Populated later
}]



def props():
    """Returns props for stats-tab, as {label, index}."""
    return PROPS


def factory(parent, panel, version):
    """Returns a new stats-plugin instance."""
    return StatsPlugin(parent, panel, version)

def parse(hero_bytes, version):
    """Returns h3tools.hero.Attributes() parsed from hero bytearray attribute sections."""
    IDS = metadata.Store.get("ids", version=version)
    ID_TO_SPECIAL = {IDS[n]: n for n in metadata.Store.get("special_artifacts", version=version)}
    BYTEPOS = h3tools.version.adapt("hero_byte_positions", metadata.HERO_BYTE_POSITIONS,
                                  version=version)

    def parse_special(hero_bytes, pos):
        binary, integer = hero_bytes[pos:pos + 4], util.bytoi(hero_bytes[pos:pos + 4])
        if all(x == ord(metadata.BLANK) for x in binary): return None # Blank
        return integer

    attributes = h3tools.hero.Attributes.factory(version)
    for prop in h3tools.version.adapt("hero.stats.DATAPROPS", DATAPROPS):
        pos = BYTEPOS[prop["name"]]
        if "check" == prop["type"]:
            value = parse_special(hero_bytes, pos) is not None
        elif "number" == prop["type"]:
            value = util.bytoi(hero_bytes[pos:pos + prop["len"]])
        elif "combo" == prop["type"]:
            value = ID_TO_SPECIAL.get(parse_special(hero_bytes, pos), "")
        else:
            continue # for prop
        attributes[prop["name"]] = value
    return attributes
