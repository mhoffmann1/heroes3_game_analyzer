"""Paths and subprocess commands shared by source and bundled applications."""

from __future__ import annotations

import sys
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parent


def app_directory() -> Path:
    """Keep user-created files beside the executable in a frozen build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return SOURCE_DIR


def worker_command(worker: str, script: str, *, python: str | None = None) -> list[str]:
    """Run a bundled worker through its parent exe, or a script through Python."""
    executable = python or sys.executable
    if getattr(sys, "frozen", False):
        return [executable, f"--worker-{worker}"]
    return [executable, "-u", str(SOURCE_DIR / script)]
