import tempfile
import unittest
from pathlib import Path

from launcher import (default_output_name, default_savegame_directory,
                      save_directory_signature, valid_output_name)


class LauncherHelpersTests(unittest.TestCase):
    def test_signature_contains_only_turn_save_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "111.GM1").write_bytes(b"save")
            (directory / "112.gm2").write_bytes(b"next save")
            (directory / "GAME_BEGIN.GM1").write_bytes(b"start")
            (directory / "notes.txt").write_text("ignore me")

            signature = save_directory_signature(directory)

        self.assertEqual(["111.GM1", "112.GM2"], [item[0] for item in signature])
        self.assertEqual([4, 9], [item[1] for item in signature])

    def test_output_name_cannot_escape_processed_games(self):
        self.assertTrue(valid_output_name("Friday game_01"))
        self.assertFalse(valid_output_name("../outside"))
        self.assertFalse(valid_output_name("nested/game"))
        self.assertFalse(valid_output_name(""))

    def test_default_output_name_replaces_path_punctuation(self):
        self.assertEqual("game_ one", default_output_name(Path("game: one")))

    def test_savegame_directory_comes_from_config(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "launcher_config.json"
            config_path.write_text(
                '{"default_savegame_directory": " /mnt/c/Heroes games/ "}',
                encoding="utf-8",
            )
            self.assertEqual("/mnt/c/Heroes games/",
                             default_savegame_directory(config_path))
            config_path.write_text("invalid JSON", encoding="utf-8")
            self.assertEqual("", default_savegame_directory(config_path))


if __name__ == "__main__":
    unittest.main()
