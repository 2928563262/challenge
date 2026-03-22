from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SILVER_PATH = DATA_DIR / "annotation" / "cleaned_silver_corpus.jsonl"
DEFAULT_GOLD_PATH = DATA_DIR / "annotation" / "gold_seed.jsonl"
DEFAULT_OUTPUT_DIR = DATA_DIR / "processed" / "ner"

ENTITY_TYPES = [
    "SYNDROME",
    "SYMPTOM",
    "FORMULA",
    "HERB",
    "THERAPY",
    "ADMINISTRATION",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def build_label_space() -> list[str]:
    labels = ["O"]
    for entity_type in ENTITY_TYPES:
        labels.append(f"B-{entity_type}")
        labels.append(f"I-{entity_type}")
    return labels


def sort_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entities,
        key=lambda item: (
            int(item["start"]),
            -(int(item["end"]) - int(item["start"])),
            item["type"],
        ),
    )


def entity_to_bio_tags(text: str, entities: list[dict[str, Any]]) -> tuple[list[str], dict[str, int]]:
    tags = ["O"] * len(text)
    stats = {
        "applied_entities": 0,
        "skipped_entities_invalid_span": 0,
        "skipped_entities_overlap": 0,
    }

    occupied = [False] * len(text)
    for entity in sort_entities(entities):
        entity_type = str(entity["type"])
        if entity_type not in ENTITY_TYPES:
            continue
        start = int(entity["start"])
        end = int(entity["end"])
        if start < 0 or end > len(text) or start >= end:
            stats["skipped_entities_invalid_span"] += 1
            continue
        if text[start:end] != str(entity["text"]):
            stats["skipped_entities_invalid_span"] += 1
            continue
        if any(occupied[index] for index in range(start, end)):
            stats["skipped_entities_overlap"] += 1
            continue

        tags[start] = f"B-{entity_type}"
        for index in range(start + 1, end):
            tags[index] = f"I-{entity_type}"
        for index in range(start, end):
            occupied[index] = True
        stats["applied_entities"] += 1

    return tags, stats


def record_to_example(record: dict[str, Any], source: str, label_to_id: dict[str, int]) -> tuple[dict[str, Any], dict[str, int], Counter[str]]:
    text = str(record["text"])
    tags, tag_stats = entity_to_bio_tags(text, list(record.get("entities", [])))
    tag_counter: Counter[str] = Counter(tag for tag in tags if tag != "O")
    example = {
        "id": str(record["id"]),
        "text": text,
        "tokens": list(text),
        "tags": tags,
        "tag_ids": [label_to_id[tag] for tag in tags],
        "source": source,
        "meta": record.get("meta", {}),
    }
    return example, tag_stats, tag_counter


def stable_bucket(record_id: str) -> float:
    digest = hashlib.md5(record_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def split_silver_examples(examples: list[dict[str, Any]], dev_ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_examples: list[dict[str, Any]] = []
    validation_examples: list[dict[str, Any]] = []
    for example in examples:
        bucket = stable_bucket(example["id"])
        if bucket < dev_ratio:
            validation_examples.append(example)
        else:
            train_examples.append(example)
    if not validation_examples and train_examples:
        validation_examples.append(train_examples.pop())
    return train_examples, validation_examples


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_split(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    entity_counter: Counter[str] = Counter()
    for row in rows:
        for tag in row["tags"]:
            if tag.startswith("B-"):
                entity_counter[tag[2:]] += 1
    return {
        "record_count": len(rows),
        "token_count": sum(len(row["tokens"]) for row in rows),
        "entity_count_by_type": dict(sorted(entity_counter.items())),
    }


def prepare_dataset(silver_path: Path, gold_path: Path, output_dir: Path, dev_ratio: float) -> dict[str, Any]:
    label_list = build_label_space()
    label_to_id = {label: index for index, label in enumerate(label_list)}

    silver_records = load_jsonl(silver_path)
    gold_records = load_jsonl(gold_path)
    gold_ids = {str(record["id"]) for record in gold_records}

    processed_stats: defaultdict[str, int] = defaultdict(int)
    bio_counter: Counter[str] = Counter()

    silver_examples: list[dict[str, Any]] = []
    for record in silver_records:
        if str(record["id"]) in gold_ids:
            continue
        example, tag_stats, tag_counter = record_to_example(record, source="silver", label_to_id=label_to_id)
        silver_examples.append(example)
        for key, value in tag_stats.items():
            processed_stats[key] += value
        bio_counter.update(tag_counter)

    gold_examples: list[dict[str, Any]] = []
    for record in gold_records:
        example, tag_stats, tag_counter = record_to_example(record, source="gold", label_to_id=label_to_id)
        gold_examples.append(example)
        for key, value in tag_stats.items():
            processed_stats[key] += value
        bio_counter.update(tag_counter)

    train_rows, validation_rows = split_silver_examples(silver_examples, dev_ratio=dev_ratio)
    test_rows = gold_examples

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "train.jsonl", train_rows)
    write_jsonl(output_dir / "validation.jsonl", validation_rows)
    write_jsonl(output_dir / "test.jsonl", test_rows)

    manifest = {
        "label_list": label_list,
        "label_to_id": label_to_id,
        "id_to_label": {str(index): label for label, index in label_to_id.items()},
        "input": {
            "silver_path": str(silver_path),
            "gold_path": str(gold_path),
        },
        "splits": {
            "train": summarize_split("train", train_rows),
            "validation": summarize_split("validation", validation_rows),
            "test": summarize_split("test", test_rows),
        },
        "processing": {
            **dict(sorted(processed_stats.items())),
            "bio_tag_count": dict(sorted(bio_counter.items())),
            "silver_record_count": len(silver_records),
            "gold_record_count": len(gold_records),
            "silver_examples_used": len(silver_examples),
        },
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare char-level BIO NER datasets from silver/gold annotation files.")
    parser.add_argument("--silver", type=Path, default=DEFAULT_SILVER_PATH)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    args = parser.parse_args()

    manifest = prepare_dataset(args.silver, args.gold, args.output_dir, args.dev_ratio)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
