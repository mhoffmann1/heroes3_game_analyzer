import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from launcher import (
    AnalyzerLauncher,
    default_output_name,
    save_directory_signature,
    valid_output_name,
)


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

    def test_dashboard_ready_does_not_open_browser(self):
        launcher = AnalyzerLauncher.__new__(AnalyzerLauncher)
        launcher.active = True
        launcher.monitoring = False
        launcher.events = queue.Queue()
        launcher.events.put(("dashboard_ready",))
        launcher.status_var = Mock()
        launcher.root = Mock()

        with patch("launcher.webbrowser.open") as open_browser:
            launcher._drain_events()

        open_browser.assert_not_called()
        launcher.status_var.set.assert_called_once_with("Dashboard is running.")


if __name__ == "__main__":
    unittest.main()
