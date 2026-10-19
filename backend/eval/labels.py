"""Review evaluation labels (independently of any model predictions).

    python -m eval.labels list [--status pending]
    python -m eval.labels show hf-03
    python -m eval.labels approve hf-03 --reviewer "Your Name"
    python -m eval.labels set hf-05 --verdict UNSUPPORTED \\
        --issues FIGURE_MISMATCH,WORDING_STRENGTH --reviewer "Your Name" --note "odds vs prob"
    python -m eval.labels reject syn-08 --reviewer "Your Name" --note "ambiguous"

Changing a label resets nothing else; only approved labels count in official metrics."""

import argparse
import json

from app.domain.enums import IssueType, Verdict
from eval.dataset import load, save


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--status")
    sub.add_parser("show").add_argument("id")
    for name in ("approve", "reject", "set"):
        p = sub.add_parser(name)
        p.add_argument("id")
        p.add_argument("--reviewer", required=True)
        p.add_argument("--note")
        if name == "set":
            p.add_argument("--verdict", choices=[v.value for v in Verdict])
            p.add_argument("--issues", help="comma-separated issue types, or '' for none")
    args = parser.parse_args()

    records = load()
    if args.command == "list":
        for r in records:
            if not args.status or r.human_review_status == args.status:
                issues = ",".join(i.value for i in r.expected_issue_types) or "-"
                print(
                    f"{r.id:8} {r.human_review_status:9} {r.expected_verdict.value:20} "
                    f"{issues:35} {r.claim[:60]}"
                )
        return
    record = next((r for r in records if r.id == args.id), None)
    if record is None:
        raise SystemExit(f"unknown id {args.id}")
    if args.command == "show":
        print(json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    if args.command == "set":
        if args.verdict:
            record.expected_verdict = Verdict(args.verdict)
        if args.issues is not None:
            record.expected_issue_types = [
                IssueType(i.strip()) for i in args.issues.split(",") if i.strip()
            ]
    record.human_review_status = {"approve": "approved", "reject": "rejected", "set": "approved"}[
        args.command
    ]
    record.reviewed_by = args.reviewer
    if args.note:
        record.label_notes = f"{record.label_notes or ''} [review: {args.note}]".strip()
    save(records)
    print(f"{record.id}: {record.human_review_status} by {record.reviewed_by}")


if __name__ == "__main__":
    main()
