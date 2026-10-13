import unittest
from types import SimpleNamespace

from h3tools.hero import skills
from h3tools.version import hota


class HotALegacyHeroLayoutTests(unittest.TestCase):
    def test_selects_legacy_layout_before_hota_18(self):
        raw = bytearray(13)
        raw[12] = 9

        self.assertIs(hota.LEGACY_HERO_REGEX, hota.get_hero_regex(SimpleNamespace(raw=raw)))

    def test_selects_runes_layout_for_hota_18(self):
        raw = bytearray(13)
        raw[12] = 10

        self.assertIs(hota.HERO_REGEX, hota.get_hero_regex(SimpleNamespace(raw=raw)))

    def test_legacy_record_skips_absent_runes_slot(self):
        hero_bytes = bytearray(1090)

        parsed = skills.parse(hero_bytes, "hota")

        self.assertEqual([], list(parsed))


if __name__ == "__main__":
    unittest.main()
