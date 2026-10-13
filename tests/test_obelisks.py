import unittest

from read_save import extract_obelisk_data, reconcile_obelisk_data


def make_native_obelisk_table(
    total, masks, offset=37, layout_bytes=None, trailing_state=0xFF
):
    raw = bytearray(offset)
    raw.append(total)
    raw.extend(masks)
    raw.extend(bytes(48 - len(masks)))
    raw.extend(layout_bytes or bytes(13))
    raw.extend(bytes.fromhex("000300000000ff03ff3f"))
    raw.append(trailing_state)
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

    def test_ignores_stateful_byte_after_signature(self):
        result = extract_obelisk_data(
            make_native_obelisk_table(1, [0x01], trailing_state=0x07)
        )

        self.assertEqual(1, result["visited_by_player"]["Red"])

    def test_returns_empty_result_for_ambiguous_data(self):
        table = make_native_obelisk_table(1, [0x01])
        result = extract_obelisk_data(table + table)

        self.assertEqual(0, result["total"])
        self.assertIsNone(result["table_offset"])

    def test_preserves_last_valid_counts_when_table_is_unavailable(self):
        state = {}
        valid = extract_obelisk_data(make_native_obelisk_table(2, [0x01, 0x02]))
        reconcile_obelisk_data(valid, state)

        result = reconcile_obelisk_data(extract_obelisk_data(b""), state)

        self.assertEqual(1, result["visited_by_player"]["Red"])
        self.assertEqual(1, result["visited_by_player"]["Blue"])
        self.assertEqual("previous_save", result["source"])
        self.assertIsNone(result["table_offset"])

    def test_obelisk_visits_do_not_regress_between_valid_saves(self):
        state = {}
        first = extract_obelisk_data(make_native_obelisk_table(2, [0x01, 0x02]))
        reconcile_obelisk_data(first, state)
        regressed = extract_obelisk_data(make_native_obelisk_table(2, [0x00, 0x02]))

        result = reconcile_obelisk_data(regressed, state)

        self.assertEqual(1, result["visited_by_player"]["Red"])
        self.assertEqual(1, result["visited_by_player"]["Blue"])


if __name__ == "__main__":
    unittest.main()
