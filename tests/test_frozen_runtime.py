import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from frozen_runtime import SOURCE_DIR, app_directory, worker_command


class FrozenRuntimeTests(unittest.TestCase):
    def test_source_worker_uses_python_script(self):
        with patch.object(sys, "frozen", False, create=True):
            command = worker_command("process-saves", "read_save.py", python="python")

        self.assertEqual(["python", "-u", str(SOURCE_DIR / "read_save.py")], command)

    def test_bundled_worker_relaunches_the_executable(self):
        with TemporaryDirectory() as directory:
            executable = str(Path(directory) / "Heroes3Dashboard.exe")
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "executable", executable
            ):
                self.assertEqual(Path(directory), app_directory())
                self.assertEqual(
                    [executable, "--worker-dashboard"],
                    worker_command("dashboard", "dashboard.py"),
                )


if __name__ == "__main__":
    unittest.main()
