from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INPUT = DATA_DIR / "annotation" / "cleaned_silver_corpus.jsonl"
DEFAULT_OUTPUT_DIR = DATA_DIR / "processed" / "graph"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def build_entity_node_id(entity_type: str, text: str) -> str:
    return f"{entity_type}|{text}"


def build_clause_node_id(record_id: str) -> str:
    return f"CLAUSE|{record_id}"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_graph(input_path: Path, output_dir: Path) -> dict[str, int]:
    records = load_jsonl(input_path)

    entity_nodes: dict[str, dict[str, object]] = {}
    clause_nodes: list[dict[str, object]] = []
    clause_mentions: list[dict[str, object]] = []
    entity_relations_index: dict[tuple[str, str, str], dict[str, object]] = {}

    for record in records:
        record_id = str(record["id"])
        text = str(record["text"])
        line_number = int(record.get("meta", {}).get("line_number", 0))
        entry_type = str(record.get("meta", {}).get("entry_type", "unknown"))
        clause_node_id = build_clause_node_id(record_id)
        clause_nodes.append(
            {
                "clause_id:ID(Clause-ID)": clause_node_id,
                ":LABEL": "Clause",
                "record_id": record_id,
                "line_number:int": line_number,
                "entry_type": entry_type,
                "text": text,
            }
        )

        local_entity_lookup: dict[str, str] = {}
        for entity in record.get("entities", []):
            entity_type = str(entity["type"])
            entity_text = str(entity["text"])
            entity_id = build_entity_node_id(entity_type, entity_text)
            local_entity_lookup[str(entity["id"])] = entity_id

            node = entity_nodes.setdefault(
                entity_id,
                {
                    "entity_id:ID(Entity-ID)": entity_id,
                    ":LABEL": "Entity;" + entity_type.title(),
                    "entity_type": entity_type,
                    "name": entity_text,
                    "mention_count:int": 0,
                    "record_count:int": 0,
                    "first_record_id": record_id,
                    "entry_types": set(),
                },
            )
            node["mention_count:int"] = int(node["mention_count:int"]) + 1
            node["entry_types"].add(entry_type)

            clause_mentions.append(
                {
                    ":START_ID(Clause-ID)": clause_node_id,
                    ":END_ID(Entity-ID)": entity_id,
                    ":TYPE": "CLAUSE_MENTIONS_ENTITY",
                    "record_id": record_id,
                    "entity_type": entity_type,
                    "mention_text": entity_text,
                    "start:int": int(entity["start"]),
                    "end:int": int(entity["end"]),
                }
            )

        mentioned_node_ids = set(local_entity_lookup.values())
        for entity_id in mentioned_node_ids:
            entity_nodes[entity_id]["record_count:int"] = int(entity_nodes[entity_id]["record_count:int"]) + 1

        for relation in record.get("relations", []):
            source_id = local_entity_lookup.get(str(relation["head"]))
            target_id = local_entity_lookup.get(str(relation["tail"]))
            relation_type = str(relation["type"])
            if not source_id or not target_id:
                continue

            key = (source_id, target_id, relation_type)
            payload = entity_relations_index.setdefault(
                key,
                {
                    ":START_ID(Entity-ID)": source_id,
                    ":END_ID(Entity-ID)": target_id,
                    ":TYPE": relation_type,
                    "evidence_count:int": 0,
                    "record_ids": [],
                    "example_text": text,
                },
            )
            payload["evidence_count:int"] = int(payload["evidence_count:int"]) + 1
            payload["record_ids"].append(record_id)

    entity_node_rows: list[dict[str, object]] = []
    for node in entity_nodes.values():
        entry_types = sorted(node.pop("entry_types"))
        node["entry_types"] = "|".join(entry_types)
        entity_node_rows.append(node)

    entity_relation_rows: list[dict[str, object]] = []
    for relation in entity_relations_index.values():
        relation["record_ids"] = "|".join(sorted(set(relation["record_ids"])))
        entity_relation_rows.append(relation)

    entity_node_rows.sort(key=lambda row: str(row["entity_id:ID(Entity-ID)"]))
    clause_nodes.sort(key=lambda row: str(row["clause_id:ID(Clause-ID)"]))
    clause_mentions.sort(key=lambda row: (str(row[":START_ID(Clause-ID)"]), int(row["start:int"]), str(row[":END_ID(Entity-ID)"])))
    entity_relation_rows.sort(key=lambda row: (str(row[":TYPE"]), str(row[":START_ID(Entity-ID)"]), str(row[":END_ID(Entity-ID)"])))

    write_csv(
        output_dir / "entity_nodes.csv",
        ["entity_id:ID(Entity-ID)", ":LABEL", "entity_type", "name", "mention_count:int", "record_count:int", "first_record_id", "entry_types"],
        entity_node_rows,
    )
    write_csv(
        output_dir / "clause_nodes.csv",
        ["clause_id:ID(Clause-ID)", ":LABEL", "record_id", "line_number:int", "entry_type", "text"],
        clause_nodes,
    )
    write_csv(
        output_dir / "entity_relations.csv",
        [":START_ID(Entity-ID)", ":END_ID(Entity-ID)", ":TYPE", "evidence_count:int", "record_ids", "example_text"],
        entity_relation_rows,
    )
    write_csv(
        output_dir / "clause_mentions.csv",
        [":START_ID(Clause-ID)", ":END_ID(Entity-ID)", ":TYPE", "record_id", "entity_type", "mention_text", "start:int", "end:int"],
        clause_mentions,
    )

    summary = {
        "input_record_count": len(records),
        "entity_node_count": len(entity_node_rows),
        "clause_node_count": len(clause_nodes),
        "entity_relation_count": len(entity_relation_rows),
        "clause_mention_count": len(clause_mentions),
    }
    (output_dir / "graph_export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export cleaned silver corpus to graph CSV files.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    summary = export_graph(args.input, args.output_dir)
    print(f"wrote graph CSV files to {args.output_dir}")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()