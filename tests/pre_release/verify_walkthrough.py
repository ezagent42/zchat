#!/usr/bin/env python3
"""Verify asciinema walkthrough output with lightweight assertions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_PATTERNS = [
    "zchat doctor",
    "zchat project create",
    "zchat template list",
    "zchat irc daemon start",
    "zchat agent create agent0",
    "zchat setup weechat --force",
    "zchat shutdown",
    "DONE",
]

ERROR_PATTERNS = [
    "Traceback (most recent call last):",
    "CommandNotFoundException",
    "No such file or directory",
]


def _load_cast_output_text(cast_file: Path) -> str:
    """Extract terminal output stream from asciinema cast file."""
    lines = cast_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines:
        return ""

    outputs: list[str] = []
    parsed_any_event = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, list) and len(event) >= 3:
            parsed_any_event = True
            if event[1] == "o" and isinstance(event[2], str):
                outputs.append(event[2])

    if parsed_any_event:
        return "".join(outputs)
    # Fallback: treat the full file as text when not in v2 event-line format.
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify pre-release walkthrough cast file.")
    parser.add_argument("cast_file", help="Path to .cast file")
    parser.add_argument(
        "--strict-errors",
        action="store_true",
        help="Fail if known error patterns are detected in output stream.",
    )
    args = parser.parse_args()

    cast_path = Path(args.cast_file)
    if not cast_path.is_file():
        print(f"[verify_walkthrough] cast file not found: {cast_path}", file=sys.stderr)
        return 1

    output_text = _load_cast_output_text(cast_path)
    missing = [pattern for pattern in REQUIRED_PATTERNS if pattern not in output_text]

    if missing:
        print("[verify_walkthrough] missing required patterns:", file=sys.stderr)
        for pattern in missing:
            print(f"  - {pattern}", file=sys.stderr)
        return 1

    found_errors = [pattern for pattern in ERROR_PATTERNS if pattern in output_text]
    if found_errors and args.strict_errors:
        print("[verify_walkthrough] detected error patterns:", file=sys.stderr)
        for pattern in found_errors:
            print(f"  - {pattern}", file=sys.stderr)
        return 1

    print(f"[verify_walkthrough] OK: {cast_path}")
    if found_errors:
        print("[verify_walkthrough] warning: error-like patterns found (non-strict mode):")
        for pattern in found_errors:
            print(f"  - {pattern}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
