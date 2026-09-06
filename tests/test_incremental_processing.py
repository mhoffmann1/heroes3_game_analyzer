import unittest

from h3tools.lib.utopias import UtopiaTracker
from read_save import (
    INCREMENTAL_CACHE_VERSION,
    restore_utopia_counts,
    restore_utopia_state,
    reusable_save_count,
    serialize_utopia_state,
)


def manifest(saves, source="/games/match", start_file=None):
    return {
        "version": INCREMENTAL_CACHE_VERSION,
        "source_directory": source,
        "start_file": start_file,
        "saves": saves,
    }


def save(filename, size=100, mtime_ns=1):
    return {"filename": filename, "size": size, "mtime_ns": mtime_ns}


class IncrementalProcessingTests(unittest.TestCase):
    def test_reuses_unchanged_prefix_when_save_is_appended(self):
        cached_saves = [save("111.GM2"), save("112.GM2")]
        current_saves = cached_saves + [save("113.GM2")]

        count = reusable_save_count(
            manifest(cached_saves),
            manifest(current_saves),
            ["111.GM2", "112.GM2"],
        )

        self.assertEqual(2, count)

    def test_rebuilds_if_an_old_save_changed(self):
        cached_saves = [save("111.GM2"), save("112.GM2")]
        current_saves = [save("111.GM2"), save("112.GM2", mtime_ns=2)]

        count = reusable_save_count(
            manifest(cached_saves),
            manifest(current_saves),
            ["111.GM2", "112.GM2"],
        )

        self.assertEqual(0, count)

    def test_rebuilds_if_cached_combined_filenames_do_not_match(self):
        saves = [save("111.GM2"), save("112.GM2")]

        count = reusable_save_count(
            manifest(saves), manifest(saves), ["111.GM2", "113.GM2"]
        )

        self.assertEqual(0, count)

    def test_restores_cumulative_utopia_counts(self):
        tracker = UtopiaTracker()

        restore_utopia_counts(tracker, {"Red": 4, "Blue": 2})

        self.assertEqual(4, tracker.counts["Red"])
        self.assertEqual(2, tracker.counts["Blue"])
        self.assertEqual(0, tracker.counts["Tan"])

    def test_round_trips_utopia_runtime_state(self):
        original = type("TrackedUtopia", (), {})()
        original.offset = 42
        original.underground = True
        original.x_coord = 7
        original.y_coord = 9
        original.visited_bitmask = "01000000"
        original.conquered = True
        original.conqueredby = 1

        restored = restore_utopia_state(serialize_utopia_state([original]))[0]

        self.assertEqual(42, restored.offset)
        self.assertTrue(restored.underground)
        self.assertEqual((7, 9), (restored.x_coord, restored.y_coord))
        self.assertEqual("01000000", restored.visited_bitmask)
        self.assertTrue(restored.conquered)
        self.assertEqual(1, restored.conqueredby)


if __name__ == "__main__":
    unittest.main()
