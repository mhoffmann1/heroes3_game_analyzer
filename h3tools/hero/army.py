# -*- coding: utf-8 -*-
"""
Army subplugin for hero-plugin, shows hero army creatures and counts.

------------------------------------------------------------------------------
This file is part of h3tools - Heroes3 Savegame Editor.
Released under the MIT License.

@created   21.03.2020
@modified  06.04.2025
------------------------------------------------------------------------------
"""
import logging

import h3tools
from .. lib import util
from .. import metadata


logger = logging.getLogger(__package__)


PROPS = {"name": "army", "label": "Army", "index": 2}
DATAPROPS = [{
    "type":        "itemlist",
    "orderable":   True,
    "nullable":    True,
    "min":         None,  # Populated later
    "max":         None,  # Populated later
    "item": [{
        "type":    "label",
        "label":   "Army slot",
      }, {
        "name":    "name",
        "type":    "combo",
        "choices": None,  # Populated later
      }, {
        "name":    "count",
        "type":    "number",
        "min":     None,  # Populated later
        "max":     None,  # Populated later
      }, {
        "name":    "placeholder",
        "type":    "window",
    }]
}]


def props():
    """Returns props for army-tab, as {label, index}."""
    return PROPS


def factory(parent, panel, version):
    """Returns a new army-plugin instance."""
    return ArmyPlugin(parent, panel, version)

def parse(hero_bytes, version):
    """Returns h3tools.hero.Army() parsed from hero bytearray army section."""
    HERO_RANGES = metadata.Store.get("hero_ranges", version=version)
    IDS = metadata.Store.get("ids", version=version)
    ID_TO_NAME = {IDS[n]: n for n in metadata.Store.get("creatures", version=version)}
    BYTEPOS = h3tools.version.adapt("hero_byte_positions", metadata.HERO_BYTE_POSITIONS,
                                  version=version)
    NAMES_POS, COUNT_POS = BYTEPOS["army_types"], BYTEPOS["army_counts"]

    army = h3tools.hero.Army.factory(version)
    for i in range(HERO_RANGES["army"][1]):
        stack = h3tools.hero.ArmyStack.factory(version)
        creature_id = util.bytoi(hero_bytes[NAMES_POS + i*4:NAMES_POS + i*4 + 4])
        count       = util.bytoi(hero_bytes[COUNT_POS + i*4:COUNT_POS + i*4 + 4])
        if count and creature_id in ID_TO_NAME:
            stack.update(name=ID_TO_NAME[creature_id], count=count)
        army[i] = stack
    return army
