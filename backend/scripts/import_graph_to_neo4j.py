from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from dotenv import load_dotenv

try:
    from neo4j import GraphDatabase
except ImportError as exc:  # pragma: no cover
    GraphDatabase = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_GRAPH_DIR = DATA_DIR / "processed" / "graph"

ENTITY_RELATION_TYPES = {
    "SYNDROME_HAS_SYMPTOM",
    "SYNDROME_TO_FORMULA",
    "FORMULA_CONTAINS_HERB",
    "FORMULA_HAS_ADMINISTRATION",
}

ENTITY_LABELS = {
    "SYNDROME": "Syndrome",
    "SYMPTOM": "Symptom",
    "FORMULA": "Formula",
    "HERB": "Herb",
    "THERAPY": "Therapy",
    "ADMINISTRATION": "Administration",
}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def chunked(rows: list[dict[str, str]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index:index + size]


def merge_entity_nodes(tx, rows: list[dict[str, str]]) -> None:
    for entity_type, label in ENTITY_LABELS.items():
        typed_rows = [row for row in rows if row["entity_type"] == entity_type]
        if not typed_rows:
            continue
        tx.run(
            f"""
            UNWIND $rows AS row
            MERGE (e:Entity {{entity_id: row.entity_id}})
            SET e:{label},
                e.entity_type = row.entity_type,
                e.name = row.name,
                e.mention_count = row.mention_count,
                e.record_count = row.record_count,
                e.first_record_id = row.first_record_id,
                e.entry_types = row.entry_types
            """,
            rows=typed_rows,
        )


def merge_clause_nodes(tx, rows: list[dict[str, str]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (c:Clause {clause_id: row.clause_id})
        SET c.record_id = row.record_id,
            c.line_number = row.line_number,
            c.entry_type = row.entry_type,
            c.text = row.text
        """,
        rows=rows,
    )


def merge_entity_relations(tx, relation_type: str, rows: list[dict[str, str]]) -> None:
    query = f"""
        UNWIND $rows AS row
        MATCH (source:Entity {{entity_id: row.start_id}})
        MATCH (target:Entity {{entity_id: row.end_id}})
        MERGE (source)-[r:{relation_type}]->(target)
        SET r.evidence_count = row.evidence_count,
            r.record_ids = row.record_ids,
            r.example_text = row.example_text
    """
    tx.run(query, rows=rows)


def merge_clause_mentions(tx, rows: list[dict[str, str]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (c:Clause {clause_id: row.start_clause_id})
        MATCH (e:Entity {entity_id: row.end_entity_id})
        MERGE (c)-[r:CLAUSE_MENTIONS_ENTITY {start: row.start, end: row.end}]->(e)
        SET r.record_id = row.record_id,
            r.entity_type = row.entity_type,
            r.mention_text = row.mention_text
        """,
        rows=rows,
    )


def ensure_constraints(driver, database: str) -> None:
    statements = [
        "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
        "CREATE CONSTRAINT clause_id_unique IF NOT EXISTS FOR (c:Clause) REQUIRE c.clause_id IS UNIQUE",
    ]
    with driver.session(database=database) as session:
        for statement in statements:
            session.run(statement)


def import_graph(graph_dir: Path, uri: str, username: str, password: str, database: str, batch_size: int) -> dict[str, int]:
    if GraphDatabase is None:
        raise RuntimeError(f"neo4j package is not installed: {IMPORT_ERROR}")

    entity_rows = [
        {
            "entity_id": row["entity_id:ID(Entity-ID)"],
            "entity_type": row["entity_type"],
            "name": row["name"],
            "mention_count": int(row["mention_count:int"]),
            "record_count": int(row["record_count:int"]),
            "first_record_id": row["first_record_id"],
            "entry_types": row["entry_types"].split("|") if row["entry_types"] else [],
        }
        for row in load_rows(graph_dir / "entity_nodes.csv")
    ]
    clause_rows = [
        {
            "clause_id": row["clause_id:ID(Clause-ID)"],
            "record_id": row["record_id"],
            "line_number": int(row["line_number:int"]),
            "entry_type": row["entry_type"],
            "text": row["text"],
        }
        for row in load_rows(graph_dir / "clause_nodes.csv")
    ]
    relation_rows_by_type: dict[str, list[dict[str, object]]] = {key: [] for key in ENTITY_RELATION_TYPES}
    for row in load_rows(graph_dir / "entity_relations.csv"):
        relation_type = row[":TYPE"]
        if relation_type not in relation_rows_by_type:
            continue
        relation_rows_by_type[relation_type].append(
            {
                "start_id": row[":START_ID(Entity-ID)"],
                "end_id": row[":END_ID(Entity-ID)"],
                "evidence_count": int(row["evidence_count:int"]),
                "record_ids": row["record_ids"].split("|") if row["record_ids"] else [],
                "example_text": row["example_text"],
            }
        )
    clause_mention_rows = [
        {
            "start_clause_id": row[":START_ID(Clause-ID)"],
            "end_entity_id": row[":END_ID(Entity-ID)"],
            "record_id": row["record_id"],
            "entity_type": row["entity_type"],
            "mention_text": row["mention_text"],
            "start": int(row["start:int"]),
            "end": int(row["end:int"]),
        }
        for row in load_rows(graph_dir / "clause_mentions.csv")
    ]

    driver = GraphDatabase.driver(uri, auth=(username, password))
    ensure_constraints(driver, database)

    with driver.session(database=database) as session:
        for batch in chunked(entity_rows, batch_size):
            session.execute_write(merge_entity_nodes, batch)
        for batch in chunked(clause_rows, batch_size):
            session.execute_write(merge_clause_nodes, batch)
        for relation_type, rows in relation_rows_by_type.items():
            for batch in chunked(rows, batch_size):
                session.execute_write(merge_entity_relations, relation_type, batch)
        for batch in chunked(clause_mention_rows, batch_size):
            session.execute_write(merge_clause_mentions, batch)

    driver.close()
    return {
        "entity_nodes": len(entity_rows),
        "clause_nodes": len(clause_rows),
        "entity_relations": sum(len(rows) for rows in relation_rows_by_type.values()),
        "clause_mentions": len(clause_mention_rows),
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / "backend" / ".env")
    parser = argparse.ArgumentParser(description="Import exported graph CSV files into Neo4j.")
    parser.add_argument("--graph-dir", type=Path, default=DEFAULT_GRAPH_DIR)
    parser.add_argument("--uri", type=str, default=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"))
    parser.add_argument("--username", type=str, default=os.getenv("NEO4J_USERNAME", "neo4j"))
    parser.add_argument("--password", type=str, default=os.getenv("NEO4J_PASSWORD", "neo4jpassword"))
    parser.add_argument("--database", type=str, default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("NEO4J_BATCH_SIZE", "500")))
    args = parser.parse_args()

    summary = import_graph(args.graph_dir, args.uri, args.username, args.password, args.database, args.batch_size)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
