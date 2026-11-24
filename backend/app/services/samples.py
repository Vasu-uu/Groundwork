"""Load the bundled sample interview sets (demo mode, tests, eval harness).

See `samples/README.md` for the on-disk layout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.models.hypothesis import Hypothesis
from app.services.corpus import Corpus, build_corpus
from app.services.segmentation import segment_transcript

DEFAULT_SAMPLES_DIR = Path(__file__).resolve().parents[3] / "samples"
_INTERVIEW_SUFFIXES = {".md", ".txt"}


class SampleSetInfo(BaseModel):
    id: str
    name: str
    description: str
    interview_count: int


class SampleSet(BaseModel):
    id: str
    name: str
    description: str
    product_idea: str = ""
    hypotheses: list[Hypothesis]
    corpus: Corpus


def _set_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if (p / "set.json").is_file())


def _interview_files(set_dir: Path) -> list[Path]:
    folder = set_dir / "interviews"
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in _INTERVIEW_SUFFIXES)


def list_sample_sets(root: Path = DEFAULT_SAMPLES_DIR) -> list[SampleSetInfo]:
    out = []
    for d in _set_dirs(root):
        meta = json.loads((d / "set.json").read_text(encoding="utf-8"))
        out.append(
            SampleSetInfo(
                id=meta["id"],
                name=meta["name"],
                description=meta["description"],
                interview_count=len(_interview_files(d)),
            )
        )
    return out


def _find(set_id: str, root: Path) -> Path:
    for d in _set_dirs(root):
        if json.loads((d / "set.json").read_text(encoding="utf-8"))["id"] == set_id:
            return d
    raise KeyError(f"Unknown sample set: {set_id}")


def load_sample_set(set_id: str, root: Path = DEFAULT_SAMPLES_DIR) -> SampleSet:
    d = _find(set_id, root)
    meta = json.loads((d / "set.json").read_text(encoding="utf-8"))
    transcripts = [
        segment_transcript(p.read_text(encoding="utf-8"), source_filename=p.name)
        for p in _interview_files(d)
    ]
    return SampleSet(
        id=meta["id"],
        name=meta["name"],
        description=meta["description"],
        product_idea=meta.get("product_idea", ""),
        hypotheses=[Hypothesis(**h) for h in meta["hypotheses"]],
        corpus=build_corpus(transcripts),
    )


def load_labels(set_id: str, root: Path = DEFAULT_SAMPLES_DIR) -> dict[str, Any]:
    """Hand-labelled ground truth for the eval harness."""
    return json.loads((_find(set_id, root) / "labels.json").read_text(encoding="utf-8"))
