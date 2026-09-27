import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from swap_hero_gui import PROJECT_DIR, build_swap_command, next_result_path


class SwapHeroGUICommandTests(unittest.TestCase):
    def test_builds_surface_transfer_command(self):
        command = build_swap_command(
            "/project/venv/bin/python",
            Path("/saves/source.GM2"),
            Path("/project/arena.GM4"),
            "Sir Mullich",
            Path("/tmp/result.GM4"),
            "Blue",
            12,
            15,
        )

        self.assertEqual("/project/venv/bin/python", command[0])
        self.assertEqual(str(PROJECT_DIR / "swap_hero.py"), command[2])
        self.assertEqual("Sir Mullich", command[command.index("--hero") + 1])
        self.assertEqual("Blue", command[command.index("--set-owner") + 1])
        self.assertEqual("12", command[command.index("--set-x") + 1])
        self.assertEqual("15", command[command.index("--set-y") + 1])
        self.assertEqual("0", command[command.index("--set-z") + 1])
        self.assertEqual("/tmp/result.GM4", command[command.index("--out") + 1])

    def test_suggests_unused_numbered_result_for_chained_transfer(self):
        with TemporaryDirectory() as directory:
            completed = Path(directory) / "test2709.GM4"
            completed.touch()
            (Path(directory) / "test2709_2.GM4").touch()

            self.assertEqual(
                Path(directory) / "test2709_3.GM4",
                next_result_path(completed),
            )

    def test_increments_existing_result_number(self):
        with TemporaryDirectory() as directory:
            completed = Path(directory) / "arena_2.GM4"
            completed.touch()

            self.assertEqual(
                Path(directory) / "arena_3.GM4",
                next_result_path(completed),
            )


if __name__ == "__main__":
    unittest.main()
