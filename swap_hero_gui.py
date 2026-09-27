#!/usr/bin/env python3
"""Small Tkinter front end for transferring a hero into an arena save."""

from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # Keep imports useful on systems without the Tk package.
    tk = None
    filedialog = messagebox = ttk = None


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE_DIRECTORY = Path(
    "/mnt/c/Users/hoffm/local_games/HoMM 3 Complete/games"
)
DEFAULT_ARENA = PROJECT_DIR / "arena.GM4"
DEFAULT_RESULT = PROJECT_DIR / "arena_with_hero.GM4"
OWNERS = ("Red", "Blue", "Tan", "Green", "Orange", "Purple", "Teal", "Pink")
SAVE_FILE_TYPES = (
    ("Heroes III save files", "*.GM1 *.GM2 *.GM3 *.GM4 *.GM5 *.GM6 *.GM7 *.GM8"),
    ("All files", "*"),
)


def build_swap_command(
    python: str,
    source: Path,
    target: Path,
    hero: str,
    result: Path,
    owner: str,
    x: int,
    y: int,
) -> list[str]:
    """Build the CLI command used by the GUI."""
    return [
        python,
        "-u",
        str(PROJECT_DIR / "swap_hero.py"),
        "--input",
        str(source),
        "--output",
        str(target),
        "--hero",
        hero,
        "--set-owner",
        owner,
        "--set-x",
        str(x),
        "--set-y",
        str(y),
        "--set-z",
        "0",
        "--out",
        str(result),
    ]


def next_result_path(completed: Path) -> Path:
    """Return the first unused numbered filename after a completed arena save."""
    match = re.fullmatch(r"(.+)_([2-9][0-9]*)", completed.stem)
    if match:
        stem = match.group(1)
        index = int(match.group(2)) + 1
    else:
        stem = completed.stem
        index = 2

    while True:
        candidate = completed.with_name(f"{stem}_{index}{completed.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


class HeroTransferGUI:
    """Collect transfer settings and run swap_hero.py without blocking Tk."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.pending_result: Path | None = None

        self.source_var = tk.StringVar()
        self.target_var = tk.StringVar(value=str(DEFAULT_ARENA))
        self.hero_var = tk.StringVar()
        self.owner_var = tk.StringVar(value=OWNERS[0])
        self.x_var = tk.StringVar(value="10")
        self.y_var = tk.StringVar(value="10")
        self.result_var = tk.StringVar(value=str(DEFAULT_RESULT))
        self.status_var = tk.StringVar(value="Choose a source save and enter a hero name.")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_events)

    def _build_ui(self) -> None:
        self.root.title("Heroes III Arena Hero Transfer")
        self.root.minsize(760, 570)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        form = ttk.Frame(self.root, padding=16)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._path_row(
            form,
            row=0,
            label="Source save",
            variable=self.source_var,
            command=self.choose_source,
        )
        self._path_row(
            form,
            row=1,
            label="Arena/base save",
            variable=self.target_var,
            command=self.choose_target,
        )

        ttk.Label(form, text="Hero name").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=5
        )
        hero_entry = ttk.Entry(form, textvariable=self.hero_var)
        hero_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)

        ttk.Label(form, text="New owner").grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=5
        )
        ttk.Combobox(
            form,
            textvariable=self.owner_var,
            values=OWNERS,
            state="readonly",
            width=14,
        ).grid(row=3, column=1, sticky="w", pady=5)

        ttk.Label(form, text="Arena position").grid(
            row=4, column=0, sticky="w", padx=(0, 10), pady=5
        )
        coords = ttk.Frame(form)
        coords.grid(row=4, column=1, columnspan=2, sticky="w", pady=5)
        ttk.Label(coords, text="X").pack(side="left")
        ttk.Spinbox(coords, from_=0, to=255, textvariable=self.x_var, width=5).pack(
            side="left", padx=(5, 14)
        )
        ttk.Label(coords, text="Y").pack(side="left")
        ttk.Spinbox(coords, from_=0, to=255, textvariable=self.y_var, width=5).pack(
            side="left", padx=(5, 14)
        )
        ttk.Label(coords, text="Surface level").pack(side="left")

        self._path_row(
            form,
            row=5,
            label="Result save",
            variable=self.result_var,
            command=self.choose_result,
            button_text="Save as…",
        )

        self.run_button = ttk.Button(
            form, text="Transfer hero", command=self.start_transfer
        )
        self.run_button.grid(row=6, column=0, columnspan=3, sticky="w", pady=(14, 0))

        log_frame = ttk.Frame(self.root, padding=(16, 0, 16, 16))
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        ttk.Label(log_frame, textvariable=self.status_var).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.log = tk.Text(log_frame, height=14, wrap="word", state="disabled")
        self.log.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        hero_entry.focus_set()

    @staticmethod
    def _path_row(
        parent,
        row: int,
        label: str,
        variable,
        command,
        button_text: str = "Browse…",
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=5
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", pady=5
        )
        ttk.Button(parent, text=button_text, command=command).grid(
            row=row, column=2, padx=(8, 0), pady=5
        )

    def choose_source(self) -> None:
        current = self.source_var.get()
        initial_directory = self._initial_directory(current)
        if not current.strip() and DEFAULT_SOURCE_DIRECTORY.is_dir():
            initial_directory = str(DEFAULT_SOURCE_DIRECTORY)
        selected = filedialog.askopenfilename(
            title="Choose the save containing the hero",
            initialdir=initial_directory,
            filetypes=SAVE_FILE_TYPES,
        )
        if selected:
            self.source_var.set(selected)

    def choose_target(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose the arena or base save",
            initialdir=self._initial_directory(self.target_var.get()),
            filetypes=SAVE_FILE_TYPES,
        )
        if selected:
            target = Path(selected)
            self.target_var.set(str(target))
            self.result_var.set(str(next_result_path(target)))

    def choose_result(self) -> None:
        current = Path(self.result_var.get()).expanduser()
        selected = filedialog.asksaveasfilename(
            title="Choose where to write the modified save",
            initialdir=str(current.parent),
            initialfile=current.name,
            defaultextension=".GM4",
            filetypes=SAVE_FILE_TYPES,
        )
        if selected:
            self.result_var.set(selected)

    @staticmethod
    def _initial_directory(value: str) -> str:
        path = Path(value).expanduser()
        if path.is_dir():
            return str(path)
        if path.parent.is_dir():
            return str(path.parent)
        return str(PROJECT_DIR)

    def _configuration(self) -> tuple[Path, Path, str, Path, str, int, int] | None:
        source = Path(self.source_var.get().strip()).expanduser()
        target = Path(self.target_var.get().strip()).expanduser()
        result = Path(self.result_var.get().strip()).expanduser()
        hero = self.hero_var.get().strip()
        owner = self.owner_var.get()

        if not source.is_file():
            messagebox.showerror("Invalid source", "Choose an existing source save file.")
            return None
        if not target.is_file():
            messagebox.showerror("Invalid arena", "Choose an existing arena or base save file.")
            return None
        if not hero:
            messagebox.showerror("Missing hero", "Enter the hero name to transfer.")
            return None
        if owner not in OWNERS:
            messagebox.showerror("Invalid owner", "Choose one of the eight player colors.")
            return None
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
        except ValueError:
            messagebox.showerror("Invalid position", "X and Y must be whole numbers.")
            return None
        if x < 0 or y < 0:
            messagebox.showerror("Invalid position", "X and Y cannot be negative.")
            return None
        if not result.name or not result.parent.is_dir():
            messagebox.showerror("Invalid result", "Choose a result path in an existing folder.")
            return None

        source = source.resolve()
        target = target.resolve()
        result = result.resolve()
        if result in (source, target):
            messagebox.showerror(
                "Unsafe result path",
                "The result must be a new file; source and arena saves are never overwritten.",
            )
            return None
        if result.exists() and not messagebox.askyesno(
            "Replace result?", f"The result file already exists:\n\n{result}\n\nReplace it?"
        ):
            return None
        return source, target, hero, result, owner, x, y

    def start_transfer(self) -> None:
        if self.process is not None:
            return
        config = self._configuration()
        if config is None:
            return
        source, target, hero, result, owner, x, y = config
        command = build_swap_command(
            sys.executable, source, target, hero, result, owner, x, y
        )

        self._set_log("")
        self._append_log(f"Transferring {hero} into {target.name}…\n\n")
        self.status_var.set("Transfer in progress…")
        self.run_button.configure(state="disabled")
        self.pending_result = result
        threading.Thread(target=self._run_transfer, args=(command,), daemon=True).start()

    def _run_transfer(self, command: list[str]) -> None:
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.process = process
            assert process.stdout is not None
            for line in process.stdout:
                self.events.put(("log", line))
            return_code = process.wait()
        except Exception as exc:
            self.events.put(("log", f"Could not run transfer: {exc}\n"))
            return_code = -1
        finally:
            self.process = None
        self.events.put(("done", return_code))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(value))
            elif kind == "done":
                self.run_button.configure(state="normal")
                if value == 0:
                    self._prepare_next_transfer()
                    self.status_var.set(
                        "Transfer complete. Ready to add another hero to the new arena."
                    )
                    messagebox.showinfo(
                        "Transfer complete",
                        "The modified arena save was created and selected as the "
                        "base for the next hero.",
                    )
                else:
                    self.status_var.set("Transfer failed. See the log for details.")
                    self.pending_result = None
        self.root.after(100, self._drain_events)

    def _prepare_next_transfer(self) -> None:
        completed = self.pending_result
        self.pending_result = None
        if completed is None:
            return
        self.target_var.set(str(completed))
        self.result_var.set(str(next_result_path(completed)))
        self.hero_var.set("")
        try:
            self.x_var.set(str(int(self.x_var.get()) + 1))
        except ValueError:
            pass

    def _set_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", text)
        self.log.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def close(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
        self.root.destroy()


def main() -> None:
    if tk is None:
        raise SystemExit(
            "The hero transfer GUI needs tkinter. Install python3-tk (Linux) or "
            "use a Python.org Windows installation, then run swap_hero_gui.py again."
        )
    root = tk.Tk()
    HeroTransferGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
