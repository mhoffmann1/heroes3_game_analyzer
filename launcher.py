"""Desktop launcher and live save-directory monitor for the analyzer."""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # Allows helper tests and a useful CLI error on minimal Linux.
    tk = None
    filedialog = messagebox = ttk = None


PROJECT_DIR = Path(__file__).resolve().parent
SAVE_NAME_PATTERN = re.compile(r"^\d{3}\.GM\d$", re.IGNORECASE)
OUTPUT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]*$")


def save_directory_signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    """Return the save files and their write state for inexpensive polling."""
    result = []
    for path in directory.iterdir():
        if not path.is_file() or not SAVE_NAME_PATTERN.match(path.name):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        result.append((path.name.upper(), stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(result))


def valid_output_name(value: str) -> bool:
    """Keep processing output inside the project's processed_games folder."""
    return bool(OUTPUT_NAME_PATTERN.fullmatch(value.strip()))


def default_output_name(directory: Path) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_. -]+", "_", directory.name).strip(" .")
    return cleaned or "live_game"


class AnalyzerLauncher:
    POLL_MS = 1000
    SETTLE_SECONDS = 2.0

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple] = queue.Queue()
        self.processing_process: subprocess.Popen[str] | None = None
        self.dashboard_process: subprocess.Popen[str] | None = None
        self.processing = False
        self.active = False
        self.monitoring = False
        self.dirty = False
        self.changed_at = 0.0
        self.last_signature: tuple[tuple[str, int, int], ...] = ()
        self.dashboard_opened = False

        self.path_var = tk.StringVar()
        self.output_var = tk.StringVar(value="live_game")
        self.port_var = tk.StringVar(value="8050")
        self.live_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Choose a savegame directory to begin.")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_events)
        self.root.after(self.POLL_MS, self._poll_directory)

    def _build_ui(self) -> None:
        self.root.title("Heroes III Game Analyzer")
        self.root.minsize(720, 500)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        form = ttk.Frame(self.root, padding=16)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Savegame directory").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=5
        )
        ttk.Entry(form, textvariable=self.path_var).grid(
            row=0, column=1, sticky="ew", pady=5
        )
        ttk.Button(form, text="Browse…", command=self.choose_directory).grid(
            row=0, column=2, padx=(8, 0), pady=5
        )

        ttk.Label(form, text="Processed game name").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=5
        )
        ttk.Entry(form, textvariable=self.output_var).grid(
            row=1, column=1, sticky="ew", pady=5
        )

        ttk.Label(form, text="Dashboard port").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=5
        )
        ttk.Entry(form, textvariable=self.port_var, width=10).grid(
            row=2, column=1, sticky="w", pady=5
        )

        ttk.Checkbutton(
            form,
            text="Monitor for new or changed save files",
            variable=self.live_var,
        ).grid(row=3, column=1, sticky="w", pady=(8, 5))

        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.start_button = ttk.Button(
            buttons, text="Process and start dashboard", command=self.start
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            buttons, text="Stop", command=self.stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="Open dashboard", command=self.open_dashboard).pack(
            side="left"
        )

        log_frame = ttk.Frame(self.root, padding=(16, 0, 16, 16))
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        ttk.Label(log_frame, textvariable=self.status_var).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.log = tk.Text(log_frame, height=16, wrap="word", state="disabled")
        self.log.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def choose_directory(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose the Heroes III savegame directory",
            initialdir=self.path_var.get() or str(Path.home()),
        )
        if selected:
            directory = Path(selected)
            self.path_var.set(str(directory))
            self.output_var.set(default_output_name(directory))

    def _configuration(self) -> tuple[Path, str, int] | None:
        directory = Path(self.path_var.get().strip()).expanduser()
        output_name = self.output_var.get().strip()
        try:
            port = int(self.port_var.get())
        except ValueError:
            port = 0

        if not directory.is_dir():
            messagebox.showerror("Invalid directory", "Choose an existing savegame directory.")
            return None
        if not save_directory_signature(directory):
            messagebox.showerror(
                "No saves found",
                "The directory contains no turn saves named like 111.GM1.",
            )
            return None
        if not valid_output_name(output_name):
            messagebox.showerror(
                "Invalid game name",
                "Use letters, numbers, spaces, dots, hyphens, or underscores.",
            )
            return None
        if not 1 <= port <= 65535:
            messagebox.showerror("Invalid port", "The port must be between 1 and 65535.")
            return None
        return directory.resolve(), output_name, port

    def start(self) -> None:
        config = self._configuration()
        if config is None:
            return
        self.directory, self.output_name, self.port = config
        self.active = True
        self.last_signature = save_directory_signature(self.directory)
        self.monitoring = self.live_var.get()
        self.dirty = False
        self.dashboard_opened = False
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._append_log(f"Watching: {self.directory}\n")
        self._begin_processing()

    def _begin_processing(self) -> None:
        if self.processing:
            self.dirty = True
            return
        self.processing = True
        self.dirty = False
        self.status_var.set("Processing save files…")
        command = [
            sys.executable,
            "-u",
            str(PROJECT_DIR / "read_save.py"),
            str(self.directory),
            "--output",
            self.output_name,
        ]
        threading.Thread(
            target=self._run_processing, args=(command,), daemon=True
        ).start()

    def _run_processing(self, command: list[str]) -> None:
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.processing_process = process
            assert process.stdout is not None
            for line in process.stdout:
                self.events.put(("log", line))
            return_code = process.wait()
        except Exception as exc:
            self.events.put(("log", f"Could not run processor: {exc}\n"))
            return_code = -1
        finally:
            self.processing_process = None
        self.events.put(("processing_done", return_code))

    def _processing_done(self, return_code: int) -> None:
        self.processing = False
        if not self.active:
            return
        if return_code != 0:
            self.status_var.set("Processing failed. See the log for details.")
            if not self.monitoring:
                self.start_button.configure(state="normal")
            return

        self.status_var.set("Processing complete; starting dashboard…")
        self._restart_dashboard()
        if not self.monitoring:
            self.start_button.configure(state="normal")
        elif self.dirty:
            self.changed_at = time.monotonic()

    def _restart_dashboard(self) -> None:
        self._terminate(self.dashboard_process)
        output_dir = PROJECT_DIR / "processed_games" / self.output_name
        command = [
            sys.executable,
            "-u",
            str(PROJECT_DIR / "dashboard.py"),
            str(output_dir),
            "--port",
            str(self.port),
            "--live-reload",
        ]
        try:
            self.dashboard_process = subprocess.Popen(
                command,
                cwd=PROJECT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self._append_log(f"Could not start dashboard: {exc}\n")
            self.status_var.set("Dashboard failed to start.")
            return
        threading.Thread(target=self._read_dashboard_log, daemon=True).start()
        threading.Thread(target=self._wait_for_dashboard, daemon=True).start()

    def _read_dashboard_log(self) -> None:
        process = self.dashboard_process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.events.put(("log", f"[dashboard] {line}"))

    def _wait_for_dashboard(self) -> None:
        url = self.dashboard_url
        for _ in range(60):
            process = self.dashboard_process
            if process is None or process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(url, timeout=0.5):
                    self.events.put(("dashboard_ready", url))
                    return
            except Exception:
                time.sleep(0.25)
        self.events.put(("dashboard_failed",))

    @property
    def dashboard_url(self) -> str:
        port = getattr(self, "port", self.port_var.get() or "8050")
        return f"http://127.0.0.1:{port}"

    def open_dashboard(self) -> None:
        webbrowser.open(self.dashboard_url)
        self.dashboard_opened = True

    def _poll_directory(self) -> None:
        if self.monitoring:
            try:
                signature = save_directory_signature(self.directory)
            except OSError as exc:
                self._append_log(f"Could not scan save directory: {exc}\n")
            else:
                now = time.monotonic()
                if signature != self.last_signature:
                    self.last_signature = signature
                    self.changed_at = now
                    self.dirty = True
                    self.status_var.set("Save change detected; waiting for the file to settle…")
                elif (
                    self.dirty
                    and not self.processing
                    and now - self.changed_at >= self.SETTLE_SECONDS
                ):
                    self._append_log("New or changed save detected. Refreshing data…\n")
                    self._begin_processing()
        self.root.after(self.POLL_MS, self._poll_directory)

    def _drain_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "log":
                self._append_log(event[1])
            elif kind == "processing_done":
                self._processing_done(event[1])
            elif kind == "dashboard_ready":
                if not self.active:
                    continue
                self.status_var.set(
                    "Dashboard is running"
                    + (" and monitoring saves." if self.monitoring else ".")
                )
                if not self.dashboard_opened:
                    webbrowser.open(event[1])
                    self.dashboard_opened = True
            elif kind == "dashboard_failed":
                if self.active:
                    self.status_var.set("Dashboard did not become ready. See the log.")
        self.root.after(100, self._drain_events)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    @staticmethod
    def _terminate(process: subprocess.Popen[str] | None) -> None:
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    def stop(self) -> None:
        self.active = False
        self.monitoring = False
        self.dirty = False
        self._terminate(self.processing_process)
        self._terminate(self.dashboard_process)
        self.processing_process = None
        self.dashboard_process = None
        self.processing = False
        self.status_var.set("Stopped.")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def close(self) -> None:
        self.stop()
        self.root.destroy()


def main() -> None:
    if tk is None:
        raise SystemExit(
            "The launcher needs tkinter. Install python3-tk (Linux) or use a "
            "Python.org Windows installation, then run launcher.py again."
        )
    root = tk.Tk()
    AnalyzerLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
