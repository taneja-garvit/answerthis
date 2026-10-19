"""Run the claim assessor over the evaluation dataset.

    python -m eval.run_eval                     # official: approved labels only
    python -m eval.run_eval --include-pending   # also report provisional metrics
    python -m eval.run_eval --ids hf-01,hf-03   # subset (saves free-tier quota)

Uses the configured provider (LLM_PROVIDER / LLM_MODEL). Evidence is taken from
the dataset, so this measures assessment only, not retrieval. Predictions go to
eval/runs/<timestamp>__<provider>__<model>.jsonl with a .summary.json next to it."""

import argparse
import asyncio
import json
import re
import uuid
from datetime import UTC, datetime

from app.ai.base import LLMError
from app.ai.factory import build_llm_provider
from app.core.config import get_settings
from app.domain.enums import IssueType
from app.services.claim_assessment import (
    EvidenceInput,
    SourceInput,
    assess_claim,
    rule_unverifiable,
)
from eval.dataset import RUNS, Record, load
from eval.metrics import compute


async def predict(provider, record: Record, max_retries: int) -> dict:
    base = {"id": record.id}
    if not record.evidence:
        result = rule_unverifiable(
            IssueType.EVIDENCE_UNAVAILABLE, "No evidence is available for this claim."
        )
    else:
        source = record.source
        try:
            result = await assess_claim(
                provider,
                claim_text=record.claim,
                original_sentence=record.claim,
                sources=[
                    SourceInput(
                        "[1]",
                        source.get("doi"),
                        source.get("title"),
                        source.get("journal"),
                        source.get("year"),
                        "abstract only",
                    )
                ],
                evidence=[
                    EvidenceInput(f"E{i}", uuid.uuid4(), "[1]", e.location, "ABSTRACT", e.text)
                    for i, e in enumerate(record.evidence, start=1)
                ],
                max_retries=max_retries,
            )
        except LLMError as exc:
            return {**base, "predicted_verdict": None, "error": f"{exc.code}: {exc}"}
    return {
        **base,
        "predicted_verdict": result.verdict.value,
        "predicted_issue_types": sorted({i.type.value for i in result.issues}),
        "confidence_level": result.confidence_level.value if result.confidence_level else None,
        "explanation": result.explanation,
        "suggested_revision": result.suggested_revision,
        "provider": result.provider,
        "model": result.model,
        "prompt_version": result.prompt_version,
        "usage": result.generation_metadata.get("usage"),
        "error": None,
    }


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    records = load()
    if args.ids:
        wanted = set(args.ids.split(","))
        records = [r for r in records if r.id in wanted]
    provider = build_llm_provider(settings)
    predictions = []
    try:
        for index, record in enumerate(records):
            if index and args.delay:
                await asyncio.sleep(args.delay)  # stay under free-tier request limits
            predictions.append(await predict(provider, record, settings.llm_max_retries))
            print(
                f"{record.id:8} expected {record.expected_verdict.value:20} "
                f"got {predictions[-1]['predicted_verdict']}"
            )
    finally:
        await provider.aclose()

    by_id = {p["id"]: p for p in predictions}
    labels = {r.id: r.model_dump(mode="json") for r in records}
    approved = [
        (labels[i], by_id[i]) for i in by_id if labels[i]["human_review_status"] == "approved"
    ]
    summary = {
        "run_at": datetime.now(UTC).isoformat(),
        "provider": provider.name,
        "model": provider.model,
        "records_run": len(predictions),
        "approved_labels": len(approved),
        "pending_labels": sum(1 for i in by_id if labels[i]["human_review_status"] == "pending"),
        "official": compute(approved) if approved else None,
    }
    if args.include_pending:
        usable = [
            (labels[i], by_id[i]) for i in by_id if labels[i]["human_review_status"] != "rejected"
        ]
        summary["provisional_including_unreviewed_labels"] = compute(usable)

    RUNS.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9.-]+", "-", f"{provider.name}__{provider.model or 'none'}".lower())
    stem = RUNS / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}__{slug}"
    stem.with_suffix(".jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in predictions)
    )
    stem.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if not approved:
        print(
            "\nNo approved labels yet: official metrics are not computed. "
            "Review labels with `python -m eval.labels`."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--include-pending", action="store_true")
    parser.add_argument("--ids", help="comma-separated record ids")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between records")
    asyncio.run(main(parser.parse_args()))
