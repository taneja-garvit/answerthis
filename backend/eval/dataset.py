"""Load and save the labelled dataset. Labels live only in dataset.jsonl;
model predictions are written to eval/runs/ and never mixed into it."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import IssueType, Verdict

DATASET = Path(__file__).parent / "dataset.jsonl"
RUNS = Path(__file__).parent / "runs"
REVIEW_STATUSES = ("pending", "approved", "rejected")


class EvidenceItem(BaseModel):
    text: str
    location: str | None = None


class Record(BaseModel):
    id: str
    category: str
    claim: str
    evidence: list[EvidenceItem]
    source: dict[str, Any]
    expected_verdict: Verdict
    expected_issue_types: list[IssueType] = Field(default_factory=list)
    label_notes: str | None = None
    human_review_status: str = "pending"
    labelled_by: str | None = None
    reviewed_by: str | None = None


def load(path: Path = DATASET) -> list[Record]:
    records = [
        Record.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]
    ids = [r.id for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate record ids in dataset")
    for r in records:
        if r.human_review_status not in REVIEW_STATUSES:
            raise ValueError(f"{r.id}: invalid human_review_status {r.human_review_status!r}")
    return records


def save(records: list[Record], path: Path = DATASET) -> None:
    lines = [json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n")
