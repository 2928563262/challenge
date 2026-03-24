from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "annotation" / "cleaned_silver_corpus.jsonl"
DEFAULT_OUTPUT = DATA_DIR / "annotation" / "gold_subset.jsonl"
DEFAULT_REPORT = DATA_DIR / "annotation" / "gold_subset_report.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_manual_gold_subset(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    manual_batch: str | None = None,
) -> dict[str, Any]:
    records = load_jsonl(input_path)

    selected: list[dict[str, Any]] = []
    for record in records:
        meta = record.get("meta") or {}
        is_manual = bool(meta.get("manual_override")) or str(record.get("id", "")).startswith("manual-")
        if not is_manual:
            continue
        if manual_batch and str(meta.get("manual_override_batch") or "") != manual_batch:
            continue

        row = dict(record)
        row_meta = dict(meta)
        row_meta["label_tier"] = "gold_standard"
        row_meta["gold_source"] = "manual_review"
        row["meta"] = row_meta
        selected.append(row)

    write_jsonl(output_path, selected)

    report = {
        "input": {
            "path": str(input_path),
            "manual_batch": manual_batch,
        },
        "output": {
            "path": str(output_path),
        },
        "stats": {
            "record_count": len(selected),
            "entity_count": sum(len(item.get("entities") or []) for item in selected),
            "relation_count": sum(len(item.get("relations") or []) for item in selected),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Export manually reviewed records as a standalone gold subset.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--manual-batch", type=str, default=None)
    args = parser.parse_args()

    report = export_manual_gold_subset(
        input_path=args.input,
        output_path=args.output,
        report_path=args.report,
        manual_batch=args.manual_batch,
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
