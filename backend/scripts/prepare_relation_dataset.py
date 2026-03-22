from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SILVER_PATH = DATA_DIR / "annotation" / "cleaned_silver_corpus.jsonl"
DEFAULT_GOLD_PATH = DATA_DIR / "annotation" / "gold_seed.jsonl"
DEFAULT_OUTPUT_DIR = DATA_DIR / "processed" / "relation"
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


def stable_bucket(record_id: str) -> float:
    digest = hashlib.md5(record_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def stable_rank(seed: str) -> str:
    return hashlib.md5(seed.encode("utf-8")).hexdigest()


def entity_key(entity: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(entity.get("id") or ""),
        str(entity.get("type") or ""),
        str(entity.get("text") or ""),
        int(entity.get("start") or 0),
        int(entity.get("end") or 0),
    )


def normalize_relation(relation: dict[str, Any], entity_lookup: dict[str, dict[str, Any]]) -> tuple[str | None, str | None, str | None]:
    relation_type = str(relation.get("type") or "")
    head = str(relation.get("head") or "")
    tail = str(relation.get("tail") or "")

    if relation_type == "SYMPTOM_TO_SYNDROME":
        return "SYNDROME_HAS_SYMPTOM", tail, head
    if relation_type in ALLOWED_RELATIONS:
        return relation_type, head, tail
    return None, None, None


def deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduplicated: list[dict[str, Any]] = []
    for entity in sorted(entities, key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0)))):
        signature = entity_key(entity)
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(entity)
    return deduplicated


def build_positive_examples(record: dict[str, Any], source: str) -> tuple[list[dict[str, Any]], set[tuple[str, str, str]], dict[str, int]]:
    entities = deduplicate_entities(list(record.get("entities", [])))
    entity_lookup = {str(entity.get("id") or f"anon-{index}"): entity for index, entity in enumerate(entities)}
    stats = {
        "skipped_relations_missing_entities": 0,
        "skipped_relations_invalid_type": 0,
        "skipped_relations_invalid_pair": 0,
    }
    pair_labels: set[tuple[str, str, str]] = set()
    examples: list[dict[str, Any]] = []

    for relation_index, relation in enumerate(record.get("relations", [])):
        normalized_type, head_id, tail_id = normalize_relation(relation, entity_lookup)
        if not normalized_type or not head_id or not tail_id:
            stats["skipped_relations_invalid_type"] += 1
            continue

        head = entity_lookup.get(head_id)
        tail = entity_lookup.get(tail_id)
        if head is None or tail is None:
            stats["skipped_relations_missing_entities"] += 1
            continue

        expected_pair = RELATION_ENTITY_PAIRS[normalized_type]
        actual_pair = (str(head.get("type") or ""), str(tail.get("type") or ""))
        if actual_pair != expected_pair:
            stats["skipped_relations_invalid_pair"] += 1
            continue

        relation_key = (str(head.get("id") or ""), str(tail.get("id") or ""), normalized_type)
        if relation_key in pair_labels:
            continue
        pair_labels.add(relation_key)
        examples.append(
            {
                "id": f"{record['id']}-pos-{relation_index:03d}",
                "record_id": str(record["id"]),
                "text": str(record["text"]),
                "label": normalized_type,
                "pair_type": f"{actual_pair[0]}->{actual_pair[1]}",
                "head": head,
                "tail": tail,
                "source": source,
                "meta": {
                    "entry_type": record.get("meta", {}).get("entry_type"),
                    "line_number": record.get("meta", {}).get("line_number"),
                    "negative_sample": False,
                },
            }
        )

    return examples, pair_labels, stats


def build_negative_examples(
    record: dict[str, Any],
    entities: list[dict[str, Any]],
    positive_keys: set[tuple[str, str, str]],
    source: str,
    negative_ratio: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for head in entities:
        for tail in entities:
            if head is tail:
                continue
            pair = (str(head.get("type") or ""), str(tail.get("type") or ""))
            relation_type = PAIR_TO_RELATION.get(pair)
            if relation_type is None:
                continue
            relation_key = (str(head.get("id") or ""), str(tail.get("id") or ""), relation_type)
            if relation_key in positive_keys:
                continue
            candidates.append(
                {
                    "id": f"{record['id']}-neg-{len(candidates):03d}",
                    "record_id": str(record["id"]),
                    "text": str(record["text"]),
                    "label": NO_RELATION,
                    "pair_type": f"{pair[0]}->{pair[1]}",
                    "head": head,
                    "tail": tail,
                    "source": source,
                    "meta": {
                        "entry_type": record.get("meta", {}).get("entry_type"),
                        "line_number": record.get("meta", {}).get("line_number"),
                        "negative_sample": True,
                        "candidate_relation_type": relation_type,
                    },
                }
            )

    if not candidates:
        return []

    positive_count = max(len(positive_keys), 1)
    limit = min(len(candidates), max(1, positive_count * negative_ratio))
    ordered = sorted(candidates, key=lambda item: stable_rank(item["id"]))
    return ordered[:limit]


def split_examples(rows: list[dict[str, Any]], dev_ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    for row in rows:
        if stable_bucket(str(row["record_id"])) < dev_ratio:
            validation_rows.append(row)
        else:
            train_rows.append(row)
    if not validation_rows and train_rows:
        validation_rows.append(train_rows.pop())
    return train_rows, validation_rows


def summarize_split(rows: list[dict[str, Any]]) -> dict[str, Any]:
    label_counter: Counter[str] = Counter(row["label"] for row in rows)
    pair_counter: Counter[str] = Counter(row["pair_type"] for row in rows)
    source_counter: Counter[str] = Counter(row["source"] for row in rows)
    return {
        "example_count": len(rows),
        "positive_example_count": sum(1 for row in rows if row["label"] != NO_RELATION),
        "negative_example_count": sum(1 for row in rows if row["label"] == NO_RELATION),
        "label_count_by_type": dict(sorted(label_counter.items())),
        "pair_count_by_type": dict(sorted(pair_counter.items())),
        "source_count_by_type": dict(sorted(source_counter.items())),
    }


def prepare_relation_dataset(
    silver_path: Path,
    gold_path: Path,
    output_dir: Path,
    dev_ratio: float,
    negative_ratio: int,
) -> dict[str, Any]:
    silver_records = load_jsonl(silver_path)
    gold_records = load_jsonl(gold_path)
    gold_ids = {str(record["id"]) for record in gold_records}

    processing_stats: defaultdict[str, int] = defaultdict(int)

    def build_examples(records: list[dict[str, Any]], source: str, exclude_ids: set[str] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in records:
            if exclude_ids and str(record["id"]) in exclude_ids:
                continue
            entities = deduplicate_entities(list(record.get("entities", [])))
            positives, positive_keys, relation_stats = build_positive_examples(record, source)
            negatives = build_negative_examples(record, entities, positive_keys, source, negative_ratio)
            rows.extend(positives)
            rows.extend(negatives)
            processing_stats["records_processed"] += 1
            processing_stats["entities_considered"] += len(entities)
            processing_stats["positive_examples"] += len(positives)
            processing_stats["negative_examples"] += len(negatives)
            for key, value in relation_stats.items():
                processing_stats[key] += value
        return rows

    silver_examples = build_examples(silver_records, "silver", exclude_ids=gold_ids)
    gold_examples = build_examples(gold_records, "gold")

    train_rows, validation_rows = split_examples(silver_examples, dev_ratio)
    test_rows = gold_examples

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "train.jsonl", train_rows)
    write_jsonl(output_dir / "validation.jsonl", validation_rows)
    write_jsonl(output_dir / "test.jsonl", test_rows)

    manifest = {
        "label_list": ALLOWED_RELATIONS + [NO_RELATION],
        "input": {
            "silver_path": str(silver_path),
            "gold_path": str(gold_path),
        },
        "splits": {
            "train": summarize_split(train_rows),
            "validation": summarize_split(validation_rows),
            "test": summarize_split(test_rows),
        },
        "processing": {
            **dict(sorted(processing_stats.items())),
            "silver_record_count": len(silver_records),
            "gold_record_count": len(gold_records),
            "silver_examples_used": len(silver_examples),
            "gold_examples_used": len(gold_examples),
        },
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare relation classification datasets from cleaned Shanghanlun annotation files.")
    parser.add_argument("--silver", type=Path, default=DEFAULT_SILVER_PATH)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dev-ratio", type=float, default=0.1)
    parser.add_argument("--negative-ratio", type=int, default=2)
    args = parser.parse_args()

    manifest = prepare_relation_dataset(
        silver_path=args.silver,
        gold_path=args.gold,
        output_dir=args.output_dir,
        dev_ratio=args.dev_ratio,
        negative_ratio=args.negative_ratio,
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
