# -*- coding: utf-8 -*-
"""
Spells subplugin for hero-plugin, shows hero learned spells list.

------------------------------------------------------------------------------
This file is part of h3tools - Heroes3 Savegame Editor.
Released under the MIT License.

@created   20.03.2020
@modified  05.04.2025
------------------------------------------------------------------------------
"""
import logging

import h3tools
from .. import metadata


logger = logging.getLogger(__name__)


PROPS = {"name": "spells", "label": "Spells", "index": 5}
DATAPROPS = [{
    "type":       "checklist",
    "choices":    None, # Populated later
    "columns":    4,
    "vertical":   True,
}]


def props():
    """Returns props for spells-tab, as {label, index}."""
    return PROPS


def factory(parent, panel, version):
    """Returns a new spells-plugin instance."""
    return SpellsPlugin(parent, panel, version)

def parse(hero_bytes, version):
    """Returns h3tools.hero.Spells() parsed from hero bytearray spellbook section."""
    SPELL_POSES = {y: x[y] for x in [metadata.Store.get("ids", version=version)]
                   for y in metadata.Store.get("spells", version=version)}
    SPELLBOOK_POS = h3tools.version.adapt("hero_byte_positions", metadata.HERO_BYTE_POSITIONS,
                                        version=version)["spells_book"]

    spells = h3tools.hero.Spells.factory(version)
    for spell_name, spell_pos in SPELL_POSES.items():
        if hero_bytes[SPELLBOOK_POS + spell_pos]: spells.add(spell_name)
    return spells
