from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_NER_BASE_DIR = DATA_DIR / "processed" / "ner"
DEFAULT_RELATION_BASE_DIR = DATA_DIR / "processed" / "relation"
DEFAULT_INCREMENTAL_DIR = DATA_DIR / "processed" / "annotation" / "incremental"
DEFAULT_OUTPUT_ROOT = DATA_DIR / "processed" / "merged"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def deduplicate_rows(rows: list[dict[str, Any]], key_field: str) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get(key_field) or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduplicated.append(row)
    return deduplicated


def summarize_ner_split(rows: list[dict[str, Any]]) -> dict[str, Any]:
    entity_counter: Counter[str] = Counter()
    for row in rows:
        for tag in row.get("tags", []):
            if isinstance(tag, str) and tag.startswith("B-"):
                entity_counter[tag[2:]] += 1
    return {
        "record_count": len(rows),
        "token_count": sum(len(row.get("tokens", [])) for row in rows),
        "entity_count_by_type": dict(sorted(entity_counter.items())),
    }


def summarize_relation_split(rows: list[dict[str, Any]]) -> dict[str, Any]:
    label_counter: Counter[str] = Counter(str(row.get("label") or "") for row in rows)
    pair_counter: Counter[str] = Counter(str(row.get("pair_type") or "") for row in rows)
    source_counter: Counter[str] = Counter(str(row.get("source") or "") for row in rows)
    return {
        "example_count": len(rows),
        "positive_example_count": sum(1 for row in rows if row.get("label") != "NO_RELATION"),
        "negative_example_count": sum(1 for row in rows if row.get("label") == "NO_RELATION"),
        "label_count_by_type": dict(sorted(label_counter.items())),
        "pair_count_by_type": dict(sorted(pair_counter.items())),
        "source_count_by_type": dict(sorted(source_counter.items())),
    }


def merge_ner_dataset(base_dir: Path, incremental_dir: Path, output_dir: Path) -> dict[str, Any]:
    train_rows = load_jsonl(base_dir / "train.jsonl")
    validation_rows = load_jsonl(base_dir / "validation.jsonl")
    test_rows = load_jsonl(base_dir / "test.jsonl")
    incremental_rows = load_jsonl(incremental_dir / "ner_incremental.jsonl")

    merged_train_rows = deduplicate_rows([*train_rows, *incremental_rows], key_field="id")

    write_jsonl(output_dir / "train.jsonl", merged_train_rows)
    write_jsonl(output_dir / "validation.jsonl", validation_rows)
    write_jsonl(output_dir / "test.jsonl", test_rows)

    base_manifest = json.loads((base_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "label_list": base_manifest["label_list"],
        "label_to_id": base_manifest["label_to_id"],
        "id_to_label": base_manifest["id_to_label"],
        "input": {
            "base_dir": str(base_dir),
            "incremental_path": str(incremental_dir / "ner_incremental.jsonl"),
        },
        "splits": {
            "train": summarize_ner_split(merged_train_rows),
            "validation": summarize_ner_split(validation_rows),
            "test": summarize_ner_split(test_rows),
        },
        "merge": {
            "base_train_count": len(train_rows),
            "incremental_count": len(incremental_rows),
            "merged_train_count": len(merged_train_rows),
            "added_count": max(len(merged_train_rows) - len(train_rows), 0),
        },
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def merge_relation_dataset(base_dir: Path, incremental_dir: Path, output_dir: Path) -> dict[str, Any]:
    train_rows = load_jsonl(base_dir / "train.jsonl")
    validation_rows = load_jsonl(base_dir / "validation.jsonl")
    test_rows = load_jsonl(base_dir / "test.jsonl")
    incremental_rows = load_jsonl(incremental_dir / "relation_incremental.jsonl")

    merged_train_rows = deduplicate_rows([*train_rows, *incremental_rows], key_field="id")

    write_jsonl(output_dir / "train.jsonl", merged_train_rows)
    write_jsonl(output_dir / "validation.jsonl", validation_rows)
    write_jsonl(output_dir / "test.jsonl", test_rows)

    base_manifest = json.loads((base_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "label_list": base_manifest["label_list"],
        "input": {
            "base_dir": str(base_dir),
            "incremental_path": str(incremental_dir / "relation_incremental.jsonl"),
        },
        "splits": {
            "train": summarize_relation_split(merged_train_rows),
            "validation": summarize_relation_split(validation_rows),
            "test": summarize_relation_split(test_rows),
        },
        "merge": {
            "base_train_count": len(train_rows),
            "incremental_count": len(incremental_rows),
            "merged_train_count": len(merged_train_rows),
            "added_count": max(len(merged_train_rows) - len(train_rows), 0),
        },
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def merge_incremental_datasets(
    ner_base_dir: Path,
    relation_base_dir: Path,
    incremental_dir: Path,
    output_root: Path,
) -> dict[str, Any]:
    ner_output_dir = output_root / "ner"
    relation_output_dir = output_root / "relation"
    ner_output_dir.mkdir(parents=True, exist_ok=True)
    relation_output_dir.mkdir(parents=True, exist_ok=True)

    ner_manifest = merge_ner_dataset(ner_base_dir, incremental_dir, ner_output_dir)
    relation_manifest = merge_relation_dataset(relation_base_dir, incremental_dir, relation_output_dir)

    report = {
        "input": {
            "ner_base_dir": str(ner_base_dir),
            "relation_base_dir": str(relation_base_dir),
            "incremental_dir": str(incremental_dir),
        },
        "output": {
            "ner_dir": str(ner_output_dir),
            "relation_dir": str(relation_output_dir),
        },
        "stats": {
            "ner": ner_manifest["merge"],
            "relation": relation_manifest["merge"],
        },
    }
    (output_root / "merge_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge accepted incremental NER/RE datasets into existing training datasets.")
    parser.add_argument("--ner-base-dir", type=Path, default=DEFAULT_NER_BASE_DIR)
    parser.add_argument("--relation-base-dir", type=Path, default=DEFAULT_RELATION_BASE_DIR)
    parser.add_argument("--incremental-dir", type=Path, default=DEFAULT_INCREMENTAL_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    report = merge_incremental_datasets(
        ner_base_dir=args.ner_base_dir,
        relation_base_dir=args.relation_base_dir,
        incremental_dir=args.incremental_dir,
        output_root=args.output_root,
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
