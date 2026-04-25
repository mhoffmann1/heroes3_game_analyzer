# -*- coding: utf-8 -*-
"""
Skills subplugin for hero-plugin, shows skills list.

------------------------------------------------------------------------------
This file is part of h3tools - Heroes3 Savegame Editor.
Released under the MIT License.

@created   14.03.2020
@modified  04.04.2025
------------------------------------------------------------------------------
"""
import logging

import h3tools
#from .. lib import controls
from .. import metadata


logger = logging.getLogger(__package__)


PROPS = {"name": "skills", "label": "Skills", "index": 1}
DATAPROPS = [{
    "type":         "itemlist",
    "addable":      True,
    "removable":    True,
    "orderable":    True,
    "exclusive":    True,
    "min":          None, # Populated later
    "max":          None, # Populated later
    "choices":      None, # Populated later
    "item":         [{
        "name":     "name",
        "type":     "label",
    }, {
        "name":     "level",
        "type":     "combo",
        "choices":  None
    }],
}]
HINT = ("More than 8 skills can be added.\n"
        "Game will not show them on the hero screen,\n"
        "but they will be in effect.")



def props():
    """Returns props for skills-tab, as {label, index}."""
    return PROPS


def factory(parent, panel, version):
    """Returns a new skills-plugin instance."""
    return SkillsPlugin(parent, panel, version)


def parse(hero_bytes, version):
    """Returns h3tools.hero.Skills() parsed from hero bytearray skills section."""
    IDS = metadata.Store.get("ids", version=version)
    LEVEL_ID_TO_NAME = {IDS[n]: n for n in metadata.Store.get("skill_levels", version=version)}
    BYTEPOS = h3tools.version.adapt("hero_byte_positions", metadata.HERO_BYTE_POSITIONS,
                                  version=version)

    skills = h3tools.hero.Skills.factory(version)
    count = hero_bytes[BYTEPOS["skills_count"]]
    values = []
    for skill_name in metadata.Store.get("skills", version=version):
        skill_pos = IDS.get(skill_name)
        level, slot = (hero_bytes[BYTEPOS[k] + skill_pos] for k in ("skills_level", "skills_slot"))
        if not level or not slot or slot > count:
            continue # for skill_name
        values.append({"name": skill_name, "level": LEVEL_ID_TO_NAME[level], "slot": slot})

    skills.extend(sorted(values, key=lambda x: x.pop("slot")))
    return skills
