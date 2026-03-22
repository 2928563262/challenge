from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_GRAPH_DIR = DATA_DIR / "processed" / "graph"
DEFAULT_OUTPUT = DEFAULT_GRAPH_DIR / "neo4j_import.cypher"

ENTITY_LABEL_CASES = {
    "SYNDROME": "Syndrome",
    "SYMPTOM": "Symptom",
    "FORMULA": "Formula",
    "HERB": "Herb",
    "THERAPY": "Therapy",
    "ADMINISTRATION": "Administration",
}


def build_label_foreach() -> str:
    blocks = []
    for entity_type, label in ENTITY_LABEL_CASES.items():
        blocks.append(
            """
  FOREACH (_ IN CASE WHEN row.entity_type = '{entity_type}' THEN [1] ELSE [] END |
    SET e:{label}
  )""".strip().format(entity_type=entity_type, label=label)
        )
    return "\n".join(blocks)


def build_script(graph_dir: Path) -> str:
    entity_nodes = "file:///entity_nodes.csv"
    clause_nodes = "file:///clause_nodes.csv"
    entity_relations = "file:///entity_relations.csv"
    clause_mentions = "file:///clause_mentions.csv"
    label_foreach = build_label_foreach()

    return f"""
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE;

CREATE CONSTRAINT clause_id_unique IF NOT EXISTS
FOR (c:Clause) REQUIRE c.clause_id IS UNIQUE;

LOAD CSV WITH HEADERS FROM '{entity_nodes}' AS row
MERGE (e:Entity {{entity_id: row.`entity_id:ID(Entity-ID)`}})
SET e.entity_type = row.entity_type,
    e.name = row.name,
    e.mention_count = toInteger(row.`mention_count:int`),
    e.record_count = toInteger(row.`record_count:int`),
    e.first_record_id = row.first_record_id,
    e.entry_types = split(row.entry_types, '|')
{label_foreach};

LOAD CSV WITH HEADERS FROM '{clause_nodes}' AS row
MERGE (c:Clause {{clause_id: row.`clause_id:ID(Clause-ID)`}})
SET c.record_id = row.record_id,
    c.line_number = toInteger(row.`line_number:int`),
    c.entry_type = row.entry_type,
    c.text = row.text;

LOAD CSV WITH HEADERS FROM '{entity_relations}' AS row
MATCH (source:Entity {{entity_id: row.`:START_ID(Entity-ID)`}})
MATCH (target:Entity {{entity_id: row.`:END_ID(Entity-ID)`}})
CALL {{
  WITH source, target, row
  FOREACH (_ IN CASE WHEN row.`:TYPE` = 'SYNDROME_HAS_SYMPTOM' THEN [1] ELSE [] END |
    MERGE (source)-[r:SYNDROME_HAS_SYMPTOM]->(target)
    SET r.evidence_count = toInteger(row.`evidence_count:int`),
        r.record_ids = split(row.record_ids, '|'),
        r.example_text = row.example_text
  )
  FOREACH (_ IN CASE WHEN row.`:TYPE` = 'SYNDROME_TO_FORMULA' THEN [1] ELSE [] END |
    MERGE (source)-[r:SYNDROME_TO_FORMULA]->(target)
    SET r.evidence_count = toInteger(row.`evidence_count:int`),
        r.record_ids = split(row.record_ids, '|'),
        r.example_text = row.example_text
  )
  FOREACH (_ IN CASE WHEN row.`:TYPE` = 'FORMULA_CONTAINS_HERB' THEN [1] ELSE [] END |
    MERGE (source)-[r:FORMULA_CONTAINS_HERB]->(target)
    SET r.evidence_count = toInteger(row.`evidence_count:int`),
        r.record_ids = split(row.record_ids, '|'),
        r.example_text = row.example_text
  )
  FOREACH (_ IN CASE WHEN row.`:TYPE` = 'FORMULA_HAS_ADMINISTRATION' THEN [1] ELSE [] END |
    MERGE (source)-[r:FORMULA_HAS_ADMINISTRATION]->(target)
    SET r.evidence_count = toInteger(row.`evidence_count:int`),
        r.record_ids = split(row.record_ids, '|'),
        r.example_text = row.example_text
  )
}} IN TRANSACTIONS OF 500 ROWS;

LOAD CSV WITH HEADERS FROM '{clause_mentions}' AS row
MATCH (c:Clause {{clause_id: row.`:START_ID(Clause-ID)`}})
MATCH (e:Entity {{entity_id: row.`:END_ID(Entity-ID)`}})
MERGE (c)-[r:CLAUSE_MENTIONS_ENTITY {{start: toInteger(row.`start:int`), end: toInteger(row.`end:int`)}}]->(e)
SET r.record_id = row.record_id,
    r.entity_type = row.entity_type,
    r.mention_text = row.mention_text;
""".strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Neo4j LOAD CSV import script.")
    parser.add_argument("--graph-dir", type=Path, default=DEFAULT_GRAPH_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    script = build_script(args.graph_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script, encoding="utf-8")
    print(f"wrote Neo4j import script to {args.output}")


if __name__ == "__main__":
    main()
