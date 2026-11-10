"""Per-hero visit masks for fixed Hero III adventure-map objects."""


# Each mask is a little-endian 32-bit integer in the hero save record. Its bit
# index follows the objects of that type in map order: level, row, column.
VISIT_MASK_TYPES = (
    "Learning Stone", "Marletto Tower", "Garden of Revelation",
    "Mercenary Camp", "Star Axis", "Tree of Knowledge",
    "Library of Enlightenment", "Arena", "School of Magic", "School of War",
)
MASK_START = 22
MASK_BYTES = 4


def visited_object_sites(hero_bytes, map_objects):
    """Return site keys visited by one hero, using the complete matched map.

    The map must include undiscovered objects: their positions determine the
    bit indexes of later objects even though the UI must not display them.
    """
    if len(hero_bytes) < MASK_START + len(VISIT_MASK_TYPES) * MASK_BYTES:
        raise ValueError("Hero record is too short for visit masks")
    sites = set()
    for index, title in enumerate(VISIT_MASK_TYPES):
        mask_at = MASK_START + index * MASK_BYTES
        bits = int.from_bytes(hero_bytes[mask_at:mask_at + MASK_BYTES], "little")
        objects = sorted((item for item in map_objects if item.get("title") == title),
                         key=lambda item: (item["level"], item["y"], item["x"]))
        for bit, item in enumerate(objects[:32]):
            if bits & (1 << bit):
                sites.add(f"{item['level']}:{item['x']}:{item['y']}")
    return sites
