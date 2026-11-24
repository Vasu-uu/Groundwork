"""Preview how Groundwork segments a transcript file or a whole sample set.

Usage (from `backend/`):
    python -m scripts.segment path/to/interview.md
    python -m scripts.segment --set freelance-invoicing
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from app.models.transcript import Transcript
from app.services.corpus import parse_upload
from app.services.documents import DocumentError
from app.services.samples import load_sample_set


def show(t: Transcript, width: int = 90) -> None:
    roles = ", ".join(f"{s.label} ({s.role})" for s in t.speakers)
    print(f"\n== {t.id}: {t.title}  [{t.format}, {len(t.segments)} segments]")
    print(f"   speakers: {roles}")
    for w in t.warnings:
        print(f"   ! {w}")
    for s in t.segments:
        line = f"   S{s.number:>3} t{s.turn:<3} {s.speaker[:12]:<12} {s.text}"
        print(textwrap.shorten(line.replace("\n", " "), width=width))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--set", dest="set_id")
    args = parser.parse_args()

    if args.set_id:
        sample = load_sample_set(args.set_id)
        for t in sample.corpus.transcripts:
            show(t)
        for w in sample.corpus.warnings:
            print(f"\n! {w}")
        return 0
    if args.path:
        try:
            show(parse_upload(args.path.name, args.path.read_bytes()))
        except DocumentError as exc:
            print(f"error: {exc}")
            return 1
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
