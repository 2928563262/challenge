from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_ACCEPTED_PATH = DATA_DIR / "processed" / "annotation" / "gold_standard_candidates.jsonl"
LEGACY_ACCEPTED_PATH = DATA_DIR / "processed" / "annotation" / "accepted_candidates.jsonl"
DEFAULT_OUTPUT_DIR = DATA_DIR / "processed" / "annotation" / "incremental"

ENTITY_TYPES = [
    "SYNDROME",
    "SYMPTOM",
    "FORMULA",
    "HERB",
    "THERAPY",
    "ADMINISTRATION",
]
NO_RELATION = "NO_RELATION"
ALLOWED_RELATIONS = [
    "SYNDROME_HAS_SYMPTOM",
    "SYNDROME_TO_FORMULA",
    "FORMULA_CONTAINS_HERB",
    "FORMULA_HAS_ADMINISTRATION",
]
RELATION_ENTITY_PAIRS = {
    "SYNDROME_HAS_SYMPTOM": ("SYNDROME", "SYMPTOM"),
    "SYNDROME_TO_FORMULA": ("SYNDROME", "FORMULA"),
    "FORMULA_CONTAINS_HERB": ("FORMULA", "HERB"),
    "FORMULA_HAS_ADMINISTRATION": ("FORMULA", "ADMINISTRATION"),
}
PAIR_TO_RELATION = {pair: relation for relation, pair in RELATION_ENTITY_PAIRS.items()}


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


def build_label_space() -> list[str]:
    labels = ["O"]
    for entity_type in ENTITY_TYPES:
        labels.append(f"B-{entity_type}")
        labels.append(f"I-{entity_type}")
    return labels


def entity_signature(entity: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(entity.get("type") or ""),
        str(entity.get("text") or ""),
        int(entity.get("start") or 0),
        int(entity.get("end") or 0),
    )


def relation_signature(relation: dict[str, Any]) -> tuple[Any, ...]:
    head = relation.get("head") or {}
    tail = relation.get("tail") or {}
    return (
        str(relation.get("type") or ""),
        str(head.get("type") or ""),
        str(head.get("text") or ""),
        int(head.get("start") or 0),
        int(head.get("end") or 0),
        str(tail.get("type") or ""),
        str(tail.get("text") or ""),
        int(tail.get("start") or 0),
        int(tail.get("end") or 0),
    )


def deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduplicated: list[dict[str, Any]] = []
    for entity in sorted(entities, key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0)), str(item.get("type", "")))):
        signature = entity_signature(entity)
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(entity)
    return deduplicated


def deduplicate_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduplicated: list[dict[str, Any]] = []
    for relation in relations:
        signature = relation_signature(relation)
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(relation)
    return deduplicated


def entity_to_bio_tags(text: str, entities: list[dict[str, Any]]) -> tuple[list[str], dict[str, int]]:
    tags = ["O"] * len(text)
    stats = {
        "accepted_entities": 0,
        "skipped_invalid_span": 0,
        "skipped_overlap": 0,
        "skipped_unknown_type": 0,
    }
    occupied = [False] * len(text)

    for entity in sorted(
        entities,
        key=lambda item: (int(item.get("start", 0)), -(int(item.get("end", 0)) - int(item.get("start", 0))), str(item.get("type", ""))),
    ):
        entity_type = str(entity.get("type") or "")
        start = int(entity.get("start") or 0)
        end = int(entity.get("end") or 0)
        entity_text = str(entity.get("text") or "")

        if entity_type not in ENTITY_TYPES:
            stats["skipped_unknown_type"] += 1
            continue
        if start < 0 or end > len(text) or start >= end or text[start:end] != entity_text:
            stats["skipped_invalid_span"] += 1
            continue
        if any(occupied[index] for index in range(start, end)):
            stats["skipped_overlap"] += 1
            continue

        tags[start] = f"B-{entity_type}"
        for index in range(start + 1, end):
            tags[index] = f"I-{entity_type}"
        for index in range(start, end):
            occupied[index] = True
        stats["accepted_entities"] += 1

    return tags, stats


def build_ner_examples(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    label_list = build_label_space()
    label_to_id = {label: index for index, label in enumerate(label_list)}
    processing_stats: defaultdict[str, int] = defaultdict(int)
    entity_counter: Counter[str] = Counter()
    bio_counter: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for record in records:
        text = str(record.get("source_text") or "")
        entities = deduplicate_entities(list(record.get("entities") or []))
        tags, stats = entity_to_bio_tags(text, entities)
        for key, value in stats.items():
            processing_stats[key] += value

        for tag in tags:
            if tag.startswith("B-"):
                entity_counter[tag[2:]] += 1
                bio_counter[tag] += 1
            elif tag.startswith("I-"):
                bio_counter[tag] += 1

        examples.append(
            {
                "id": str(record.get("record_id") or ""),
                "text": text,
                "tokens": list(text),
                "tags": tags,
                "tag_ids": [label_to_id[tag] for tag in tags],
                "source": "gold_standard",
                "meta": {
                    "status": record.get("status"),
                    "source_page": record.get("source_page"),
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                },
            }
        )

    manifest = {
        "label_list": label_list,
        "label_to_id": label_to_id,
        "record_count": len(examples),
        "token_count": sum(len(example["tokens"]) for example in examples),
        "entity_count_by_type": dict(sorted(entity_counter.items())),
        "bio_tag_count": dict(sorted(bio_counter.items())),
        "processing": dict(sorted(processing_stats.items())),
    }
    return examples, manifest


def build_relation_examples(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    processing_stats: defaultdict[str, int] = defaultdict(int)
    label_counter: Counter[str] = Counter()
    pair_counter: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for record in records:
        entities = deduplicate_entities(list(record.get("entities") or []))
        entity_lookup = {
            (str(entity.get("type") or ""), str(entity.get("text") or ""), int(entity.get("start") or 0), int(entity.get("end") or 0)): entity
            for entity in entities
        }
        relations = deduplicate_relations(list(record.get("relations") or []))
        record_id = str(record.get("record_id") or "")
        example_index = 0

        for relation in relations:
            relation_type = str(relation.get("type") or "")
            head = relation.get("head") or {}
            tail = relation.get("tail") or {}
            if relation_type not in ALLOWED_RELATIONS:
                processing_stats["skipped_invalid_relation_type"] += 1
                continue

            head_key = (str(head.get("type") or ""), str(head.get("text") or ""), int(head.get("start") or 0), int(head.get("end") or 0))
            tail_key = (str(tail.get("type") or ""), str(tail.get("text") or ""), int(tail.get("start") or 0), int(tail.get("end") or 0))
            canonical_head = entity_lookup.get(head_key)
            canonical_tail = entity_lookup.get(tail_key)
            if canonical_head is None or canonical_tail is None:
                processing_stats["skipped_missing_entities"] += 1
                continue

            expected_pair = RELATION_ENTITY_PAIRS[relation_type]
            actual_pair = (str(canonical_head.get("type") or ""), str(canonical_tail.get("type") or ""))
            if actual_pair != expected_pair:
                processing_stats["skipped_invalid_pair"] += 1
                continue

            example = {
                "id": f"{record_id}-accepted-rel-{example_index:03d}",
                "record_id": record_id,
                "text": str(record.get("source_text") or ""),
                "label": relation_type,
                "pair_type": f"{actual_pair[0]}->{actual_pair[1]}",
                "head": canonical_head,
                "tail": canonical_tail,
                "source": "gold_standard",
                "meta": {
                    "status": record.get("status"),
                    "source_page": record.get("source_page"),
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                    "negative_sample": False,
                },
            }
            examples.append(example)
            label_counter[relation_type] += 1
            pair_counter[example["pair_type"]] += 1
            example_index += 1

        processing_stats["records_processed"] += 1
        processing_stats["entities_considered"] += len(entities)

    manifest = {
        "label_list": ALLOWED_RELATIONS + [NO_RELATION],
        "example_count": len(examples),
        "positive_example_count": len(examples),
        "negative_example_count": 0,
        "label_count_by_type": dict(sorted(label_counter.items())),
        "pair_count_by_type": dict(sorted(pair_counter.items())),
        "processing": dict(sorted(processing_stats.items())),
    }
    return examples, manifest


def prepare_incremental_datasets(accepted_path: Path, output_dir: Path) -> dict[str, Any]:
    if not accepted_path.exists() and accepted_path == DEFAULT_ACCEPTED_PATH and LEGACY_ACCEPTED_PATH.exists():
        accepted_path = LEGACY_ACCEPTED_PATH
    records = load_jsonl(accepted_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    ner_examples, ner_manifest = build_ner_examples(records)
    relation_examples, relation_manifest = build_relation_examples(records)

    ner_path = output_dir / "ner_incremental.jsonl"
    relation_path = output_dir / "relation_incremental.jsonl"
    report_path = output_dir / "incremental_dataset_report.json"

    write_jsonl(ner_path, ner_examples)
    write_jsonl(relation_path, relation_examples)

    report = {
        "input": {
            "accepted_path": str(accepted_path),
            "dataset_tier": "gold_standard",
        },
        "output": {
            "ner_incremental_path": str(ner_path),
            "relation_incremental_path": str(relation_path),
        },
        "stats": {
            "accepted_record_count": len(records),
            "ner": ner_manifest,
            "relation": relation_manifest,
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare incremental NER/RE datasets from reviewed gold-standard candidates.")
    parser.add_argument("--accepted", type=Path, default=DEFAULT_ACCEPTED_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    report = prepare_incremental_datasets(accepted_path=args.accepted, output_dir=args.output_dir)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
