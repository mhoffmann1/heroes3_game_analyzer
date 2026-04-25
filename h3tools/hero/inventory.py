# -*- coding: utf-8 -*-
"""
Inventory subplugin for hero-plugin, shows inventory artifacts list.

------------------------------------------------------------------------------
This file is part of h3tools - Heroes3 Savegame Editor.
Released under the MIT License.

@created   16.03.2020
@modified  06.04.2025
------------------------------------------------------------------------------
"""
import functools
import logging

import h3tools
from .. lib import util
from .. import conf
from .. import metadata


logger = logging.getLogger(__package__)



PROPS = {"name": "inventory", "label": "Inventory", "index": 4}
DATAPROPS = [{
    "type":        "itemlist",
    "orderable":   True,
    "nullable":    True,
    "min":         None, # Populated later
    "max":         None, # Populated later
    "item": [{
        "type":    "label",
        "label":   "Inventory slot",
      }, {
        "type":    "combo",
        "choices": None, # Populated later
    }]
}]



def props():
    """Returns props for inventory-tab, as {label, index}."""
    return PROPS


def factory(parent, panel, version):
    """Returns a new inventory-plugin instance."""
    return InventoryPlugin(parent, panel, version)


def parse(hero_bytes, version):
    """Returns h3tools.hero.Inventory() parsed from hero bytearray inventory section."""
    HERO_RANGES = metadata.Store.get("hero_ranges", version=version)
    IDS = metadata.Store.get("ids", version=version)
    ARTIFACTS = metadata.Store.get("artifacts", category="inventory", version=version)
    ID_TO_NAME = {IDS[n]: n for n in ARTIFACTS}
    BYTEPOS = h3tools.version.adapt("hero_byte_positions", metadata.HERO_BYTE_POSITIONS,
                                  version=version)

    def parse_id(hero_bytes, pos):
        binary, integer = hero_bytes[pos:pos + 4], util.bytoi(hero_bytes[pos:pos + 4])
        if all(x == metadata.BLANK for x in binary): return None # Blank
        if integer == IDS["Spell Scroll"]: return util.bytoi(hero_bytes[pos:pos + 8])
        return integer

    inventory = h3tools.hero.Inventory.factory(version)
    for i in range(HERO_RANGES["inventory"][1]):
        artifact_id = parse_id(hero_bytes, BYTEPOS["inventory"] + i*8)
        inventory[i] = ID_TO_NAME.get(artifact_id)
    return inventory
