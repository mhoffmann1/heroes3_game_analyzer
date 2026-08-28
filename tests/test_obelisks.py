import unittest

from read_save import extract_obelisk_data


def make_native_obelisk_table(total, masks, offset=37, layout_bytes=None):
    raw = bytearray(offset)
    raw.append(total)
    raw.extend(masks)
    raw.extend(bytes(48 - len(masks)))
    raw.extend(layout_bytes or bytes(13))
    raw.extend(bytes.fromhex("000300000000ff03ff3fff"))
    raw.extend(bytes(20))
    return raw


class ObeliskExtractionTests(unittest.TestCase):
    def test_extracts_total_masks_and_player_counts(self):
        # Ten Obelisks: Red visited 0/1, Blue 3/4, Tan 9, Green 5/6/7.
        masks = [0x01, 0x01, 0x00, 0x02, 0x02, 0x08, 0x08, 0x08, 0x00, 0x04]
        result = extract_obelisk_data(
            make_native_obelisk_table(10, masks)
        )

        self.assertEqual(10, result["total"])
        self.assertEqual(37, result["table_offset"])
        self.assertEqual(2, result["visited_by_player"]["Red"])
        self.assertEqual(2, result["visited_by_player"]["Blue"])
        self.assertEqual(1, result["visited_by_player"]["Tan"])
        self.assertEqual(3, result["visited_by_player"]["Green"])
        self.assertEqual(["Tan"], result["objects"][9]["visited_by"])

    def test_accepts_hota_1_8_layout_bytes(self):
        result = extract_obelisk_data(
            make_native_obelisk_table(
                1,
                [0x02],
                layout_bytes=bytes.fromhex("0008ffc0b9511cbeb63f58c226"),
            )
        )

        self.assertEqual(1, result["visited_by_player"]["Blue"])

    def test_returns_empty_result_for_ambiguous_data(self):
        table = make_native_obelisk_table(1, [0x01])
        result = extract_obelisk_data(table + table)

        self.assertEqual(0, result["total"])
        self.assertIsNone(result["table_offset"])


if __name__ == "__main__":
    unittest.main()
