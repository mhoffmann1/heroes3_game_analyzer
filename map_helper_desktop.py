"""Desktop launcher for the standalone Map Helper server."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from frozen_runtime import app_directory, worker_command

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None
    filedialog = messagebox = ttk = None


PROJECT_DIR = app_directory()
PLAYERS = ("Red", "Blue", "Tan", "Green", "Orange", "Purple", "Teal", "Pink")


class MapHelperDesktop:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple] = queue.Queue()
        self.directory_var = tk.StringVar()
        self.player_var = tk.StringVar(value="Blue")
        self.port_var = tk.StringVar(value="8051")
        self.game_dir_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a processed game directory.")

        root.title("Heroes III Map Helper")
        root.minsize(700, 390)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        form = ttk.Frame(root, padding=16)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        self._directory_row(form, 0, "Processed game", self.directory_var,
                            self.choose_directory)
        ttk.Label(form, text="Player").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(form, textvariable=self.player_var, values=PLAYERS,
                     state="readonly", width=14).grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(form, text="Port").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.port_var, width=10).grid(
            row=2, column=1, sticky="w", pady=5)
        self._directory_row(form, 3, "Game installation (optional)",
                            self.game_dir_var, self.choose_game_directory)
        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.start_button = ttk.Button(buttons, text="Start Map Helper", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop,
                                      state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="Open map", command=self.open_map).pack(side="left")

        log_frame = ttk.Frame(root, padding=(16, 0, 16, 16))
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        ttk.Label(log_frame, textvariable=self.status_var).grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self._drain_events)

    @staticmethod
    def _directory_row(parent, row, label, variable, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w",
                                           padx=(0, 10), pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1,
                                                       sticky="ew", pady=5)
        ttk.Button(parent, text="Browse…", command=command).grid(
            row=row, column=2, padx=(8, 0), pady=5)

    def choose_directory(self) -> None:
        candidate = PROJECT_DIR.parent / "Heroes3Dashboard" / "processed_games"
        initial = self.directory_var.get() or (str(candidate) if candidate.is_dir()
                                                else str(PROJECT_DIR))
        selected = filedialog.askdirectory(title="Choose a processed game",
                                           initialdir=initial)
        if selected:
            self.directory_var.set(selected)

    def choose_game_directory(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose the Heroes III installation",
            initialdir=self.game_dir_var.get() or str(PROJECT_DIR))
        if selected:
            self.game_dir_var.set(selected)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port_var.get()}"

    def start(self) -> None:
        directory = Path(self.directory_var.get().strip()).expanduser()
        if not (directory / "combined_player_data.json").is_file():
            messagebox.showerror("Invalid processed game",
                                 "Choose a folder containing combined_player_data.json.")
            return
        try:
            port = int(self.port_var.get())
        except ValueError:
            port = 0
        if not 1 <= port <= 65535:
            messagebox.showerror("Invalid port", "The port must be between 1 and 65535.")
            return
        game_dir = self.game_dir_var.get().strip()
        if game_dir and not Path(game_dir).expanduser().is_dir():
            messagebox.showerror("Invalid installation", "Choose an existing game folder.")
            return

        command = worker_command("map-helper", "map_helper_app.py") + [
            str(directory.resolve()), "--player", self.player_var.get(),
            "--port", str(port),
        ]
        if game_dir:
            command += ["--game-dir", str(Path(game_dir).expanduser().resolve())]
        try:
            process = subprocess.Popen(command, cwd=PROJECT_DIR,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True,
                                       bufsize=1)
        except OSError as exc:
            messagebox.showerror("Could not start Map Helper", str(exc))
            return
        self.process = process
        self.status_var.set("Starting Map Helper…")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        threading.Thread(target=self._read_log, args=(process,), daemon=True).start()
        threading.Thread(target=self._wait_for_server,
                         args=(process, self.url), daemon=True).start()

    def _read_log(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.events.put(("log", process, line))
        self.events.put(("done", process, process.wait()))

    def _wait_for_server(self, process: subprocess.Popen[str], url: str) -> None:
        for _ in range(60):
            if process.poll() is not None:
                return
            try:
                with urllib.request.urlopen(url, timeout=0.5):
                    self.events.put(("ready", process, url))
                    return
            except Exception:
                time.sleep(0.25)

    def _drain_events(self) -> None:
        while True:
            try:
                kind, process, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log.configure(state="normal")
                self.log.insert("end", value)
                self.log.see("end")
                self.log.configure(state="disabled")
            elif process is self.process and kind == "ready":
                self.status_var.set(f"Map Helper is running at {value}")
            elif process is self.process and kind == "done":
                self.process = None
                self.status_var.set("Map Helper stopped." if value == 0 else
                                    "Map Helper stopped. See the log for details.")
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
        self.root.after(100, self._drain_events)

    def open_map(self) -> None:
        webbrowser.open(self.url)

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        self.status_var.set("Map Helper stopped.")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def close(self) -> None:
        self.stop()
        self.root.destroy()


def main() -> None:
    if len(sys.argv) > 1:
        if sys.argv[1] == "--worker-map-helper":
            sys.argv.pop(1)
        from map_helper_app import main as run_map_helper

        run_map_helper()
        return
    if tk is None:
        raise SystemExit("The Map Helper launcher requires tkinter.")
    root = tk.Tk()
    MapHelperDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
