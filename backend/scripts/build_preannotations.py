from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "clean_text" / "shanghanlun_cleaned.txt"
DEFAULT_DICTIONARY = DATA_DIR / "dictionary" / "entity_terms.json"
DEFAULT_OUTPUT = DATA_DIR / "annotation" / "preannotated_corpus.jsonl"
DEFAULT_STATS = DATA_DIR / "annotation" / "preannotation_stats.json"


@dataclass(frozen=True)
class TermMatch:
    entity_type: str
    text: str
    start: int
    end: int


def load_dictionary(path: Path) -> dict[str, list[str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def iter_term_matches(text: str, entity_type: str, terms: Iterable[str]) -> list[TermMatch]:
    matches: list[TermMatch] = []
    for term in sorted(set(terms), key=lambda item: (-len(item), item)):
        start = 0
        while True:
            index = text.find(term, start)
            if index == -1:
                break
            matches.append(TermMatch(entity_type=entity_type, text=term, start=index, end=index + len(term)))
            start = index + 1
    return matches


def select_non_overlapping_matches(text: str, dictionary: dict[str, list[str]]) -> list[TermMatch]:
    candidate_matches: list[TermMatch] = []
    for entity_type, terms in dictionary.items():
        candidate_matches.extend(iter_term_matches(text, entity_type, terms))

    candidate_matches.sort(key=lambda item: (item.start, -(item.end - item.start), item.entity_type))
    occupied = [False] * len(text)
    selected: list[TermMatch] = []

    for match in candidate_matches:
        if any(occupied[index] for index in range(match.start, match.end)):
            continue
        for index in range(match.start, match.end):
            occupied[index] = True
        selected.append(match)

    return sorted(selected, key=lambda item: (item.start, item.end))


def build_entities(matches: list[TermMatch]) -> list[dict[str, object]]:
    entities: list[dict[str, object]] = []
    for idx, match in enumerate(matches, start=1):
        entities.append(
            {
                "id": f"e{idx}",
                "type": match.entity_type,
                "text": match.text,
                "start": match.start,
                "end": match.end,
                "source": "dictionary",
            }
        )
    return entities


def build_relations(text: str, entities: list[dict[str, object]]) -> list[dict[str, object]]:
    relations: list[dict[str, object]] = []
    by_type: dict[str, list[dict[str, object]]] = {}
    for entity in entities:
        by_type.setdefault(str(entity["type"]), []).append(entity)

    def add_relation(relation_type: str, head_id: str, tail_id: str) -> None:
        relation = {
            "type": relation_type,
            "head": head_id,
            "tail": tail_id,
            "source": "rule",
        }
        if relation not in relations:
            relations.append(relation)

    for syndrome in by_type.get("SYNDROME", []):
        for symptom in by_type.get("SYMPTOM", []):
            add_relation("SYNDROME_HAS_SYMPTOM", str(syndrome["id"]), str(symptom["id"]))
        for formula in by_type.get("FORMULA", []):
            add_relation("SYNDROME_TO_FORMULA", str(syndrome["id"]), str(formula["id"]))
        for therapy in by_type.get("THERAPY", []):
            add_relation("SYNDROME_TO_THERAPY", str(syndrome["id"]), str(therapy["id"]))

    if "方" in text or "主之" in text:
        for formula in by_type.get("FORMULA", []):
            for herb in by_type.get("HERB", []):
                add_relation("FORMULA_CONTAINS_HERB", str(formula["id"]), str(herb["id"]))
            for administration in by_type.get("ADMINISTRATION", []):
                add_relation("FORMULA_HAS_ADMINISTRATION", str(formula["id"]), str(administration["id"]))

    return relations


def build_record(line_number: int, text: str, dictionary: dict[str, list[str]], transformer_model: str | None) -> dict[str, object]:
    matches = select_non_overlapping_matches(text=text, dictionary=dictionary)
    entities = build_entities(matches)
    relations = build_relations(text=text, entities=entities)

    methods = ["dictionary", "rule"]
    if transformer_model:
        methods.append("transformer_hook")

    return {
        "id": f"line-{line_number:04d}",
        "text": text,
        "entities": entities,
        "relations": relations,
        "meta": {
            "line_number": line_number,
            "preannotation_methods": methods,
            "transformer_model": transformer_model,
        },
    }


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_stats(path: Path, records: list[dict[str, object]]) -> None:
    entity_counts: dict[str, int] = {}
    relation_counts: dict[str, int] = {}
    non_empty_records = 0

    for record in records:
        if record["entities"]:
            non_empty_records += 1
        for entity in record["entities"]:
            entity_type = str(entity["type"])
            entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
        for relation in record["relations"]:
            relation_type = str(relation["type"])
            relation_counts[relation_type] = relation_counts.get(relation_type, 0) + 1

    stats = {
        "record_count": len(records),
        "records_with_entities": non_empty_records,
        "entity_counts": entity_counts,
        "relation_counts": relation_counts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build weakly-supervised preannotations from Shanghanlun corpus.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stats-output", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for debugging.")
    parser.add_argument(
        "--transformer-model",
        type=str,
        default="",
        help="Reserved for transformer-assisted candidate ranking, e.g. ethanyt/guwenbert-base.",
    )
    args = parser.parse_args()

    dictionary = load_dictionary(args.dictionary)
    lines = load_lines(args.input)
    if args.limit > 0:
        lines = lines[: args.limit]

    transformer_model = args.transformer_model.strip() or None
    records = [
        build_record(line_number=index, text=text, dictionary=dictionary, transformer_model=transformer_model)
        for index, text in enumerate(lines, start=1)
    ]

    write_jsonl(args.output, records)
    write_stats(args.stats_output, records)

    print(f"wrote {len(records)} records to {args.output}")
    print(f"wrote stats to {args.stats_output}")


if __name__ == "__main__":
    main()