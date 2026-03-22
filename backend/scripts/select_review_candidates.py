from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "annotation" / "preannotated_corpus.jsonl"
DEFAULT_OUTPUT = DATA_DIR / "annotation" / "review_candidates.jsonl"
DEFAULT_STATS_OUTPUT = DATA_DIR / "annotation" / "review_candidate_stats.json"
DEFAULT_GOLD_SEED = DATA_DIR / "annotation" / "gold_seed.jsonl"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def build_global_counters(records: list[dict[str, object]]) -> tuple[Counter[str], Counter[str], Counter[str]]:
    entity_type_counter: Counter[str] = Counter()
    relation_type_counter: Counter[str] = Counter()
    entity_text_counter: Counter[str] = Counter()

    for record in records:
        for entity in record.get("entities", []):
            entity_type = str(entity.get("type", ""))
            entity_text = str(entity.get("text", ""))
            entity_type_counter[entity_type] += 1
            entity_text_counter[entity_text] += 1
        for relation in record.get("relations", []):
            relation_type_counter[str(relation.get("type", ""))] += 1

    return entity_type_counter, relation_type_counter, entity_text_counter


def score_record(
    record: dict[str, object],
    entity_type_counter: Counter[str],
    relation_type_counter: Counter[str],
    entity_text_counter: Counter[str],
) -> tuple[float, dict[str, float], list[str]]:
    text = str(record.get("text", ""))
    entities = list(record.get("entities", []))
    relations = list(record.get("relations", []))

    entity_types = [str(entity.get("type", "")) for entity in entities]
    relation_types = [str(relation.get("type", "")) for relation in relations]
    type_set = set(entity_types)
    relation_set = set(relation_types)

    syndrome_count = entity_types.count("SYNDROME")
    formula_count = entity_types.count("FORMULA")
    herb_count = entity_types.count("HERB")
    symptom_count = entity_types.count("SYMPTOM")
    administration_count = entity_types.count("ADMINISTRATION")
    therapy_count = entity_types.count("THERAPY")

    relation_score = min(len(relations), 8) * 4.0
    coverage_score = len(type_set) * 5.0 + len(relation_set) * 2.5
    length_score = 12.0 - abs(len(text) - 90) / 8.0
    length_score = clamp(length_score, 0.0, 12.0)

    triad_bonus = 0.0
    if syndrome_count > 0 and formula_count > 0 and herb_count > 0:
        triad_bonus += 16.0
    if formula_count > 0 and administration_count > 0:
        triad_bonus += 8.0
    if syndrome_count > 0 and therapy_count > 0:
        triad_bonus += 6.0

    low_frequency_bonus = 0.0
    rare_items = 0
    for entity in entities:
        entity_text = str(entity.get("text", ""))
        if entity_text and entity_text_counter[entity_text] <= 2:
            rare_items += 1
    low_frequency_bonus = min(rare_items, 4) * 2.5

    ambiguity_bonus = 0.0
    flags: list[str] = []
    if syndrome_count >= 2:
        ambiguity_bonus += 6.0
        flags.append("multiple_syndromes")
    if formula_count >= 2:
        ambiguity_bonus += 6.0
        flags.append("multiple_formulas")
    if symptom_count >= 4 and syndrome_count >= 1:
        ambiguity_bonus += 4.0
        flags.append("dense_symptom_cluster")
    if administration_count >= 2:
        ambiguity_bonus += 3.0
        flags.append("multiple_administration_terms")

    rare_relation_hits = 0
    for relation_type in relation_set:
        if relation_type_counter[relation_type] <= 100:
            rare_relation_hits += 1
    rare_relation_bonus = rare_relation_hits * 2.0
    if rare_relation_hits:
        flags.append("contains_low_frequency_relation")

    if syndrome_count and formula_count and herb_count:
        flags.append("contains_syndrome_formula_herb_chain")
    if formula_count and administration_count:
        flags.append("contains_formula_administration_pair")
    if therapy_count:
        flags.append("contains_therapy")

    breakdown = {
        "relation_score": relation_score,
        "coverage_score": coverage_score,
        "length_score": length_score,
        "triad_bonus": triad_bonus,
        "low_frequency_bonus": low_frequency_bonus,
        "ambiguity_bonus": ambiguity_bonus,
        "rare_relation_bonus": rare_relation_bonus,
    }
    total_score = sum(breakdown.values())
    return total_score, breakdown, sorted(set(flags))


def main() -> None:
    parser = argparse.ArgumentParser(description="Select high-value records for minimal gold review.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stats-output", type=Path, default=DEFAULT_STATS_OUTPUT)
    parser.add_argument("--gold-seed", type=Path, default=DEFAULT_GOLD_SEED)
    parser.add_argument("--top-k", type=int, default=30)
    args = parser.parse_args()

    records = load_jsonl(args.input)
    gold_seed_records = load_jsonl(args.gold_seed)
    excluded_ids = {str(record.get("id")) for record in gold_seed_records}

    entity_type_counter, relation_type_counter, entity_text_counter = build_global_counters(records)

    scored_records: list[dict[str, object]] = []
    for record in records:
        record_id = str(record.get("id"))
        if record_id in excluded_ids:
            continue

        score, breakdown, flags = score_record(
            record=record,
            entity_type_counter=entity_type_counter,
            relation_type_counter=relation_type_counter,
            entity_text_counter=entity_text_counter,
        )

        if not record.get("entities"):
            continue

        enriched = dict(record)
        enriched["review_priority"] = {
            "score": round(score, 2),
            "score_breakdown": {key: round(value, 2) for key, value in breakdown.items()},
            "flags": flags,
            "entity_type_count": len({str(entity.get("type", "")) for entity in record.get("entities", [])}),
            "relation_count": len(record.get("relations", [])),
            "text_length": len(str(record.get("text", ""))),
        }
        scored_records.append(enriched)

    scored_records.sort(
        key=lambda record: (
            -float(record["review_priority"]["score"]),
            -int(record["review_priority"]["entity_type_count"]),
            -int(record["review_priority"]["relation_count"]),
            str(record.get("id", "")),
        )
    )

    selected_records = scored_records[: args.top_k]
    for rank, record in enumerate(selected_records, start=1):
        record["review_priority"]["rank"] = rank

    flag_counter: Counter[str] = Counter()
    for record in selected_records:
        for flag in record["review_priority"]["flags"]:
            flag_counter[flag] += 1

    stats = {
        "input_record_count": len(records),
        "excluded_seed_count": len(excluded_ids),
        "selected_count": len(selected_records),
        "top_k": args.top_k,
        "flag_distribution": dict(flag_counter),
        "selected_ids": [str(record.get("id")) for record in selected_records],
    }

    write_jsonl(args.output, selected_records)
    write_json(args.stats_output, stats)

    print(f"wrote {len(selected_records)} review candidates to {args.output}")
    print(f"wrote stats to {args.stats_output}")


if __name__ == "__main__":
    main()