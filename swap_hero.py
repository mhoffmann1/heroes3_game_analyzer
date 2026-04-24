#!/usr/bin/env python3
"""Swap a specific hero's data between two Heroes III (HoTA supported) save files.

Core workflow:
  1) Decompress both .GM2/.Gm1 (gzip) saves.
  2) Locate the hero record by hero name in both saves.
  3) Copy hero bytes 1:1 from input -> output.
  4) Patch owner and map coordinates in the output hero record.
  5) Write the output save back as gzip (.GM2-compatible).

This script relies on the project's h3tools package for version detection
and hero record discovery (regex-based), but performs the actual byte patching
itself.

Notes:
- HoMM3 saves are gzipped; HoTA saves are as well.
- Hero "core" struct in h3tools starts at movement_total; there is a 63-byte
  preamble before that which includes ownership and (likely) map placement.
- Owner byte offset in the 63-byte preamble is assumed to be 0x20 (as used in
  existing code).
- Coordinate offsets are auto-detected heuristically inside the 63-byte
  preamble (or, if needed, inside the whole copied hero block).

Usage:
  python3 swap_hero.py --input in.GM2 --output out.GM2 --hero "Rashka" \
    --set-owner Tan --set-x 10 --set-y 22 --set-z 0 --out out_modified.GM2

"""

from __future__ import annotations

import argparse
import gzip
import os
import sys
from dataclasses import dataclass
from typing import Optional, Tuple, List


# --- Ensure we can import h3tools when running standalone.
# If this script is placed in the repo root, h3tools should resolve naturally.
# If not, allow pointing --h3tools-path.


OWNER_NAME_TO_BYTE = {
    "red": 0,
    "blue": 1,
    "tan": 2,
    "green": 3,
    "orange": 4,
    "purple": 5,
    "teal": 6,
    "pink": 7,
    "none": 255,
}


@dataclass
class HeroSpan:
    """Span covering a hero record inside uncompressed save bytes."""

    name: str
    start: int  # inclusive
    end: int    # exclusive

    @property
    def length(self) -> int:
        return self.end - self.start


def _read_gzip_bytes(path: str) -> bytearray:
    with gzip.GzipFile(path, "rb") as f:
        return bytearray(f.read())


def _write_gzip_bytes(path: str, raw: bytearray) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with gzip.GzipFile(path, "wb") as f:
        f.write(bytes(raw))


def _load_savefile_with_h3tools(path: str, h3tools_path: Optional[str] = None):
    if h3tools_path:
        sys.path.insert(0, os.path.abspath(h3tools_path))

    import h3tools  # noqa: F401
    from h3tools.metadata import Savefile

    # parse_heroes=False keeps it faster; we call populate_heroes ourselves.
    return Savefile(path, parse_heroes=False)


def _get_hero_full_span(save, hero_name: str) -> HeroSpan:
    """Return the hero span including the 63-byte preamble used by existing code."""
    save.populate_heroes()

    target = None
    for h in save.heroes:
        if h.name.strip().lower() == hero_name.strip().lower():
            target = h
            break

    if not target:
        available = ", ".join([h.name for h in save.heroes[:25]])
        if len(save.heroes) > 25:
            available += f", ... (+{len(save.heroes)-25} more)"
        raise ValueError(f"Hero '{hero_name}' not found. Sample heroes: {available}")
    
    # Existing code in populate_heroes used start-63 to include ownership info.
    target.parse()
    print(f"Hero {hero_name.strip().lower()} properties:\n {target.properties}")
    #print(f"Hero bytes\n: {target.bytes}")

    # Existing code in populate_heroes used start-63 to include ownership info.
    start, end = target.span
    full_start = max(0, start - 63)
    full_end = end
    return HeroSpan(name=target.name, start=full_start, end=full_end)


def _parse_owner(owner: str) -> int:
    b = OWNER_NAME_TO_BYTE.get(owner.strip().lower())
    if b is None:
        raise ValueError(
            "Invalid --set-owner. Use one of: "
            + ", ".join(sorted({k.title() for k in OWNER_NAME_TO_BYTE.keys()}))
        )
    return b


def _find_coord_candidates(
    raw: bytearray,
    start: int,
    end: int,
    map_size: int,
) -> List[Tuple[int, Tuple[int, int, int]]]:
    """Find likely (x,y,z) triplets within [start,end). Returns list of (offset,(x,y,z))."""
    out = []
    if map_size <= 0:
        return out
    lim = min(end, len(raw))
    for off in range(start, max(start, lim - 2)):
        x = raw[off]
        y = raw[off + 1]
        z = raw[off + 2]
        if z not in (0, 1):
            continue
        if x >= map_size or y >= map_size:
            continue
        # Avoid obvious filler patterns
        if x == 0xFF and y == 0xFF:
            continue
        out.append((off, (x, y, z)))
    return out


def _choose_best_coord_offset(
    candidates: List[Tuple[int, Tuple[int, int, int]]],
    hero_full_start: int,
) -> Optional[int]:
    """Heuristic: prefer candidates close to hero_full_start + 0x24 (typical object coord area)."""
    if not candidates:
        return None
    preferred = hero_full_start + 0x24
    candidates_sorted = sorted(candidates, key=lambda t: abs(t[0] - preferred))
    return candidates_sorted[0][0]


def _patch_owner_and_coords(
    raw: bytearray,
    hero_span: HeroSpan,
    owner_byte: Optional[int],
    x: Optional[int],
    y: Optional[int],
    z: Optional[int],
    map_size: int,
) -> Tuple[Optional[int], Optional[int]]:
    """Patch owner and coords in-place. Returns (owner_offset, coord_offset_used_for_primary_xy).

    Coordinate patching is deterministic based on empirical header layout:

    - The hero record "span" starts at (original_start - 63). This is the same 63-byte preamble
      used by the existing parser to read ownership at offset 0x20.

    - The 58-byte "hero header" (where coordinates live) begins 58 bytes before original_start.
      Therefore, relative to hero_span.start (which is original_start-63), header58_start is +5.

    Within that 58-byte header:
      * primary X: header[0:2]  big-endian u16
      * primary Y: header[2:4]  big-endian u16
      * level   Z: header[4:6]  big-endian u16 (0=surface, 1=underground)
      * secondary X: header[8:10] little-endian u16
      * secondary Y+flags: header[10:12] little-endian u16, where low byte is Y and high byte contains flags.
        In observed saves, the underground bit is 0x04 in that high-byte flags.

    We patch BOTH primary and secondary encodings and toggle only the underground bit in flags.
    """
    owner_offset = None
    coord_offset = None

    # Owner offset derived from existing code: preamble byte at 0x20.
    if owner_byte is not None:
        owner_offset = hero_span.start + 0x20
        if owner_offset < len(raw):
            raw[owner_offset] = owner_byte
        else:
            raise ValueError("Owner offset beyond file length; unexpected save layout.")

    if x is None or y is None or z is None:
        return owner_offset, coord_offset

    if z not in (0, 1):
        raise ValueError("--set-z must be 0 (surface) or 1 (underground).")
    if map_size and (x >= map_size or y >= map_size or x < 0 or y < 0):
        raise ValueError(f"Coordinates out of map bounds (size={map_size}): x={x}, y={y}.")

    # header58_start = (original_start - 58) = (original_start - 63) + 5 = hero_span.start + 5
    header58_start = hero_span.start + 5
    if header58_start < 0 or header58_start + 58 > len(raw):
        raise ValueError("Cannot patch coords: computed hero header offsets out of bounds.")

    # Primary coords (big-endian u16)
    raw[header58_start + 0 : header58_start + 2] = int(x).to_bytes(2, "big")
    raw[header58_start + 2 : header58_start + 4] = int(y).to_bytes(2, "big")
    raw[header58_start + 4 : header58_start + 6] = int(z).to_bytes(2, "big")

    # Secondary coords
    raw[header58_start + 8 : header58_start + 10] = int(x).to_bytes(2, "little")

    # Secondary Y low byte + flags high byte
    y_low_off = header58_start + 10
    flags_off = header58_start + 11
    existing_flags = raw[flags_off]

    UNDERGROUND_FLAG = 0x04
    if z == 1:
        new_flags = existing_flags | UNDERGROUND_FLAG
    else:
        new_flags = existing_flags & (~UNDERGROUND_FLAG & 0xFF)

    raw[y_low_off] = int(y) & 0xFF
    raw[flags_off] = new_flags

    # For reporting/debugging, coord_offset points at the start of primary x
    coord_offset = header58_start

    return owner_offset, coord_offset



def swap_hero(
    input_path: str,
    output_path: str,
    hero_name: str,
    out_path: str,
    set_owner: Optional[str] = None,
    set_x: Optional[int] = None,
    set_y: Optional[int] = None,
    set_z: Optional[int] = None,
    h3tools_path: Optional[str] = None,
) -> None:
    in_save = _load_savefile_with_h3tools(input_path, h3tools_path=h3tools_path)
    out_save = _load_savefile_with_h3tools(output_path, h3tools_path=h3tools_path)

    in_raw = in_save.raw
    out_raw = out_save.raw

    in_span = _get_hero_full_span(in_save, hero_name)
    out_span = _get_hero_full_span(out_save, hero_name)

    if in_span.length != out_span.length:
        raise ValueError(
            f"Hero record length mismatch for '{in_span.name}'. "
            f"input_len={in_span.length}, output_len={out_span.length}. "
            "This typically indicates different game/mod versions or a changed hero record format."
        )

    # Copy hero bytes 1:1.
    out_raw[out_span.start:out_span.end] = in_raw[in_span.start:in_span.end]

    # Patch owner/coords in output.
    owner_byte = _parse_owner(set_owner) if set_owner is not None else None

    map_size = 0
    try:
        map_size = int(out_save.mapdata.get("size") or 0)
    except Exception:
        map_size = 0

    owner_off, coord_off = _patch_owner_and_coords(
        out_raw,
        out_span,
        owner_byte=owner_byte,
        x=set_x,
        y=set_y,
        z=set_z,
        map_size=map_size,
    )

    _write_gzip_bytes(out_path, out_raw)

    msg = [
        f"Copied hero '{in_span.name}' bytes: input[{in_span.start}:{in_span.end}] -> output[{out_span.start}:{out_span.end}]",
        f"Wrote modified save: {out_path}",
    ]
    if owner_off is not None:
        msg.append(f"Patched owner at 0x{owner_off:X} to {owner_byte}")
    if coord_off is not None:
        msg.append(f"Patched coords at 0x{coord_off:X} to ({set_x},{set_y},{set_z})")

    print("\n".join(msg))


def main() -> None:
    p = argparse.ArgumentParser(description="Copy a specific hero record from one HoMM3/HoTA save to another.")
    p.add_argument("--input", required=True, help="Input save (.GM2) to copy hero from")
    p.add_argument("--output", required=True, help="Output/base save (.GM2) to modify")
    p.add_argument("--hero", required=True, help="Existing hero name to copy (case-insensitive)")
    p.add_argument("--out", required=True, help="Path for modified output save (.GM2)")

    p.add_argument("--set-owner", default=None, help="New owner: Red/Blue/Tan/Green/Orange/Purple/Teal/Pink/None")
    p.add_argument("--set-x", type=int, default=None, help="New X coordinate")
    p.add_argument("--set-y", type=int, default=None, help="New Y coordinate")
    p.add_argument("--set-z", type=int, default=None, help="New Z level: 0 surface, 1 underground")

    p.add_argument(
        "--h3tools-path",
        default=None,
        help="Optional path to the project root (where the h3tools package is).",
    )

    args = p.parse_args()

    # If any of x/y/z is provided, require all three.
    coords = [args.set_x, args.set_y, args.set_z]
    if any(v is not None for v in coords) and not all(v is not None for v in coords):
        raise SystemExit("If setting coordinates, you must provide --set-x, --set-y, and --set-z together.")

    swap_hero(
        input_path=args.input,
        output_path=args.output,
        hero_name=args.hero,
        out_path=args.out,
        set_owner=args.set_owner,
        set_x=args.set_x,
        set_y=args.set_y,
        set_z=args.set_z,
        h3tools_path=args.h3tools_path,
    )


if __name__ == "__main__":
    main()
