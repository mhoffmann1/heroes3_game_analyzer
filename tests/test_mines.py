import unittest

from read_save import extract_mine_data


def make_mine_record(owner, subtype, x, y, z=0):
    return bytes([owner, subtype, 0]) + bytes([0xFF]) * 28 + bytes(28) + bytes([x, y, z])


class MineExtractionTests(unittest.TestCase):
    def test_extracts_ownership_counts_and_weighted_score(self):
        records = [
            make_mine_record(0, 0, 10, 10),
            make_mine_record(0, 2, 20, 20),
            make_mine_record(0, 4, 30, 30),
            make_mine_record(1, 6, 40, 40),
            make_mine_record(0xFF, 5, 50, 50),
        ]
        raw = bytes(37) + b"".join(records) + bytes(20)

        result = extract_mine_data(raw, map_size=72, levels=1)

        self.assertEqual(5, result["total"])
        self.assertEqual(37, result["table_offset"])
        self.assertEqual(1, result["owned_by_player"]["Red"]["sawmills"])
        self.assertEqual(1, result["owned_by_player"]["Red"]["ore_pits"])
        self.assertEqual(1, result["owned_by_player"]["Red"]["crystal_caverns"])
        self.assertEqual(3, result["owned_by_player"]["Red"]["total_mines"])
        self.assertEqual(4, result["owned_by_player"]["Red"]["mine_score"])
        self.assertEqual(1, result["owned_by_player"]["Blue"]["gold_mines"])
        self.assertEqual(1, result["neutral"]["gem_ponds"])

    def test_rejects_an_ambiguous_pair_of_equal_tables(self):
        table = b"".join([
            make_mine_record(0, 0, 10, 10),
            make_mine_record(1, 2, 20, 20),
        ])

        result = extract_mine_data(table + bytes(17) + table, 72, 1)

        self.assertEqual(0, result["total"])
        self.assertIsNone(result["table_offset"])


if __name__ == "__main__":
    unittest.main()
