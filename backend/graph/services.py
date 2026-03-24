from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any
import os

from django.conf import settings

from .registry import activate_graph, get_active_graph, get_registry_path, list_graph_versions

GRAPH_DIR = Path(settings.DATA_DIR) / "processed" / "graph"
DEFAULT_REVIEWED_GRAPH_DIR = Path(settings.DATA_DIR) / "processed" / "graph-reviewed"
GRAPH_SYNC_DIR = Path(settings.DATA_DIR) / "processed" / "graph-sync"
NEO4J_SYNC_REPORT_PATH = GRAPH_SYNC_DIR / "neo4j_sync_report.json"

SHOWCASE_CASES = [
    {
        "slug": "guizhi-tang",
        "title": "桂枝汤证候链路",
        "description": "用于展示方剂如何连接证候、症状与原文条文，是最稳定的一条答辩演示路径。",
        "focus": "方剂 -> 证候 -> 症状 -> 原文",
        "entity_name": "桂枝汤",
        "entity_type": "FORMULA",
    },
    {
        "slug": "xiaochaihu-tang",
        "title": "小柴胡汤少阳链路",
        "description": "用于展示经典辨证方剂的图谱路径，适合回答“如何从条文回到方剂”的问题。",
        "focus": "少阳相关方剂链",
        "entity_name": "小柴胡汤",
        "entity_type": "FORMULA",
    },
    {
        "slug": "dachengqi-tang",
        "title": "大承气汤阳明链路",
        "description": "用于展示高频方剂节点和药味、服法的组合关系，突出图谱的结构化能力。",
        "focus": "阳明腑实代表方",
        "entity_name": "大承气汤",
        "entity_type": "FORMULA",
    },
    {
        "slug": "wuling-san",
        "title": "五苓散水气链路",
        "description": "用于展示方剂与服法的组合关系，以及原文条文的证据回溯能力。",
        "focus": "方剂 + 服法 + 条文证据",
        "entity_name": "五苓散",
        "entity_type": "FORMULA",
    },
]


class GraphDataUnavailableError(RuntimeError):
    pass


class GraphSyncError(RuntimeError):
    pass


def _graph_paths(graph_dir: Path) -> dict[str, Path]:
    return {
        "summary": graph_dir / "graph_export_summary.json",
        "entity": graph_dir / "entity_nodes.csv",
        "relation": graph_dir / "entity_relations.csv",
        "clause": graph_dir / "clause_nodes.csv",
        "mention": graph_dir / "clause_mentions.csv",
    }


def get_active_graph_record() -> dict[str, Any]:
    active = get_active_graph()
    if active is not None:
        return active
    return {
        "id": "default-graph",
        "run_name": "default-graph",
        "source_input": str(Path(settings.DATA_DIR) / "annotation" / "cleaned_silver_corpus.jsonl"),
        "source_type": "cleaned_silver",
        "output_dir": str(GRAPH_DIR),
        "stats": {},
        "created_at": "",
        "updated_at": "",
        "is_active": True,
    }


def get_graph_registry_status() -> dict[str, Any]:
    active = get_active_graph_record()
    versions = list_graph_versions()
    if not any(record.get("id") == active.get("id") for record in versions):
        versions = [active, *versions]
    return {
        "path": str(get_registry_path()),
        "active": active,
        "versions": versions,
    }


def activate_graph_version(graph_id: str) -> dict[str, Any]:
    load_graph_data.cache_clear()
    return activate_graph(graph_id)


def _write_neo4j_sync_report(payload: dict[str, Any]) -> None:
    GRAPH_SYNC_DIR.mkdir(parents=True, exist_ok=True)
    NEO4J_SYNC_REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_graph_sync_status() -> dict[str, Any]:
    if not NEO4J_SYNC_REPORT_PATH.exists():
        return {
            "exists": False,
            "path": str(NEO4J_SYNC_REPORT_PATH),
            "report": None,
        }
    return {
        "exists": True,
        "path": str(NEO4J_SYNC_REPORT_PATH),
        "report": json.loads(NEO4J_SYNC_REPORT_PATH.read_text(encoding="utf-8")),
    }


def run_neo4j_sync(graph_dir: Path | None = None) -> dict[str, Any]:
    from scripts.import_graph_to_neo4j import import_graph

    active_graph = get_active_graph_record()
    target_graph_dir = graph_dir or Path(str(active_graph.get("output_dir") or GRAPH_DIR))
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4jpassword")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    batch_size = int(os.getenv("NEO4J_BATCH_SIZE", "500"))

    try:
        summary = import_graph(
            graph_dir=target_graph_dir,
            uri=uri,
            username=username,
            password=password,
            database=database,
            batch_size=batch_size,
        )
    except Exception as exc:  # pragma: no cover
        payload = {
            "ok": False,
            "detail": str(exc),
            "graph_version": active_graph,
            "graph_dir": str(target_graph_dir),
            "uri": uri,
            "database": database,
        }
        _write_neo4j_sync_report(payload)
        raise GraphSyncError(str(exc)) from exc

    payload = {
        "ok": True,
        "detail": "neo4j sync completed.",
        "graph_version": active_graph,
        "graph_dir": str(target_graph_dir),
        "uri": uri,
        "database": database,
        "summary": summary,
    }
    _write_neo4j_sync_report(payload)
    return payload


def run_reviewed_graph_refresh(statuses: list[str] | None = None, limit: int | None = None, sync_neo4j: bool = False) -> dict[str, Any]:
    from scripts.export_reviewed_graph_csv import export_reviewed_graph

    summary = export_reviewed_graph(
        output_dir=DEFAULT_REVIEWED_GRAPH_DIR,
        statuses=statuses or ["accepted", "reviewed"],
        limit=limit,
        run_name="graph-reviewed",
        activate=True,
    )
    load_graph_data.cache_clear()
    payload = {
        "summary": summary,
        "registry": get_graph_registry_status(),
        "graph_summary": build_graph_summary(),
    }
    if sync_neo4j:
        payload["neo4j_sync"] = run_neo4j_sync(Path(summary["output_dir"]))
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise GraphDataUnavailableError(f"Missing graph data file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def load_graph_data() -> dict[str, Any]:
    active_graph = get_active_graph_record()
    graph_dir = Path(str(active_graph.get("output_dir") or GRAPH_DIR))
    paths = _graph_paths(graph_dir)
    summary_path = paths["summary"]
    if not summary_path.exists():
        raise GraphDataUnavailableError(f"Missing graph summary file: {summary_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    entity_rows = _read_csv(paths["entity"])
    relation_rows = _read_csv(paths["relation"])
    clause_rows = _read_csv(paths["clause"])
    mention_rows = _read_csv(paths["mention"])

    entities: dict[str, dict[str, Any]] = {}
    clauses: dict[str, dict[str, Any]] = {}
    outgoing_relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming_relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mentions_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entity_type_breakdown: Counter[str] = Counter()
    relation_type_breakdown: Counter[str] = Counter()

    for row in entity_rows:
        entity_id = row["entity_id:ID(Entity-ID)"]
        entity = {
            "entity_id": entity_id,
            "entity_type": row["entity_type"],
            "name": row["name"],
            "mention_count": int(row["mention_count:int"]),
            "record_count": int(row["record_count:int"]),
            "first_record_id": row["first_record_id"],
            "entry_types": row["entry_types"].split("|") if row["entry_types"] else [],
            "labels": row[":LABEL"].split(";") if row[":LABEL"] else [],
        }
        entities[entity_id] = entity
        entity_type_breakdown[entity["entity_type"]] += 1

    for row in clause_rows:
        clause_id = row["clause_id:ID(Clause-ID)"]
        clauses[clause_id] = {
            "clause_id": clause_id,
            "record_id": row["record_id"],
            "line_number": int(row["line_number:int"]),
            "entry_type": row["entry_type"],
            "text": row["text"],
        }

    for row in relation_rows:
        relation = {
            "start_id": row[":START_ID(Entity-ID)"],
            "end_id": row[":END_ID(Entity-ID)"],
            "relation_type": row[":TYPE"],
            "evidence_count": int(row["evidence_count:int"]),
            "record_ids": row["record_ids"].split("|") if row["record_ids"] else [],
            "example_text": row["example_text"],
        }
        relation_type_breakdown[relation["relation_type"]] += 1
        outgoing_relations[relation["start_id"]].append(relation)
        incoming_relations[relation["end_id"]].append(relation)

    for row in mention_rows:
        clause_id = row[":START_ID(Clause-ID)"]
        entity_id = row[":END_ID(Entity-ID)"]
        clause = clauses.get(clause_id)
        mention = {
            "clause_id": clause_id,
            "record_id": row["record_id"],
            "entity_type": row["entity_type"],
            "mention_text": row["mention_text"],
            "start": int(row["start:int"]),
            "end": int(row["end:int"]),
            "clause_text": clause["text"] if clause else "",
            "entry_type": clause["entry_type"] if clause else None,
            "line_number": clause["line_number"] if clause else None,
        }
        mentions_by_entity[entity_id].append(mention)

    for relation_list in outgoing_relations.values():
        relation_list.sort(key=lambda item: (-item["evidence_count"], item["relation_type"], item["end_id"]))
    for relation_list in incoming_relations.values():
        relation_list.sort(key=lambda item: (-item["evidence_count"], item["relation_type"], item["start_id"]))
    for mention_list in mentions_by_entity.values():
        mention_list.sort(key=lambda item: (item["record_id"], item["start"], item["end"]))

    summary["entity_type_breakdown"] = dict(sorted(entity_type_breakdown.items()))
    summary["relation_type_breakdown"] = dict(sorted(relation_type_breakdown.items()))
    summary["graph_version"] = active_graph

    return {
        "summary": summary,
        "entities": entities,
        "clauses": clauses,
        "outgoing_relations": outgoing_relations,
        "incoming_relations": incoming_relations,
        "mentions_by_entity": mentions_by_entity,
    }


def build_graph_summary() -> dict[str, Any]:
    data = load_graph_data()
    top_entities = sorted(
        data["entities"].values(),
        key=lambda item: (-item["mention_count"], item["entity_type"], item["name"]),
    )[:10]
    return {
        **data["summary"],
        "top_entities": top_entities,
    }


def search_entities(keyword: str = "", entity_type: str | None = None, limit: int = 20) -> dict[str, Any]:
    data = load_graph_data()
    normalized_keyword = keyword.strip()
    normalized_type = entity_type.strip().upper() if entity_type else ""
    safe_limit = max(1, min(limit, 100))

    results = []
    for entity in data["entities"].values():
        if normalized_type and entity["entity_type"] != normalized_type:
            continue
        if normalized_keyword and normalized_keyword not in entity["name"] and normalized_keyword not in entity["entity_id"]:
            continue
        results.append(entity)

    results.sort(key=lambda item: (-item["mention_count"], item["entity_type"], item["name"]))
    return {
        "keyword": normalized_keyword,
        "entity_type": normalized_type or None,
        "total": len(results),
        "results": results[:safe_limit],
    }


def _relation_payload(relation: dict[str, Any], related_entity: dict[str, Any], direction: str) -> dict[str, Any]:
    return {
        "direction": direction,
        "relation_type": relation["relation_type"],
        "evidence_count": relation["evidence_count"],
        "record_ids": relation["record_ids"],
        "example_text": relation["example_text"],
        "related_entity": related_entity,
    }


def get_entity_detail(entity_id: str, relation_limit: int = 20, evidence_limit: int = 20) -> dict[str, Any]:
    data = load_graph_data()
    entity = data["entities"].get(entity_id)
    if entity is None:
        raise KeyError(entity_id)

    safe_relation_limit = max(1, min(relation_limit, 100))
    safe_evidence_limit = max(1, min(evidence_limit, 100))

    outgoing = []
    for relation in data["outgoing_relations"].get(entity_id, [])[:safe_relation_limit]:
        related_entity = data["entities"].get(relation["end_id"])
        if related_entity is None:
            continue
        outgoing.append(_relation_payload(relation, related_entity, "outgoing"))

    incoming = []
    for relation in data["incoming_relations"].get(entity_id, [])[:safe_relation_limit]:
        related_entity = data["entities"].get(relation["start_id"])
        if related_entity is None:
            continue
        incoming.append(_relation_payload(relation, related_entity, "incoming"))

    mentions = data["mentions_by_entity"].get(entity_id, [])[:safe_evidence_limit]

    return {
        "entity": entity,
        "outgoing_relations": outgoing,
        "incoming_relations": incoming,
        "mentions": mentions,
        "stats": {
            "outgoing_relation_count": len(data["outgoing_relations"].get(entity_id, [])),
            "incoming_relation_count": len(data["incoming_relations"].get(entity_id, [])),
            "mention_count": len(data["mentions_by_entity"].get(entity_id, [])),
        },
    }


def _find_entity_by_name(entity_name: str, entity_type: str) -> dict[str, Any] | None:
    data = load_graph_data()
    candidates = [
        entity
        for entity in data["entities"].values()
        if entity["name"] == entity_name and entity["entity_type"] == entity_type
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item["mention_count"], item["entity_id"]))
    return candidates[0]


def _build_highlights(detail: dict[str, Any]) -> list[str]:
    entity = detail["entity"]
    incoming = detail["incoming_relations"]
    outgoing = detail["outgoing_relations"]

    if entity["entity_type"] == "FORMULA":
        syndromes = [item["related_entity"]["name"] for item in incoming if item["relation_type"] == "SYNDROME_TO_FORMULA"]
        herbs = [item["related_entity"]["name"] for item in outgoing if item["relation_type"] == "FORMULA_CONTAINS_HERB"]
        administrations = [item["related_entity"]["name"] for item in outgoing if item["relation_type"] == "FORMULA_HAS_ADMINISTRATION"]
        highlights = []
        if syndromes:
            highlights.append(f"证候: {'、'.join(syndromes[:4])}")
        if herbs:
            highlights.append(f"药味: {'、'.join(herbs[:6])}")
        if administrations:
            highlights.append(f"服法: {'、'.join(administrations[:3])}")
        if highlights:
            return highlights

    return [
        f"入边 {detail['stats']['incoming_relation_count']} 条",
        f"出边 {detail['stats']['outgoing_relation_count']} 条",
        f"原文证据 {detail['stats']['mention_count']} 条",
    ]


def build_graph_showcase() -> dict[str, Any]:
    cases = []
    for config in SHOWCASE_CASES:
        entity = _find_entity_by_name(config["entity_name"], config["entity_type"])
        if entity is None:
            continue
        detail = get_entity_detail(entity["entity_id"], relation_limit=6, evidence_limit=3)
        cases.append(
            {
                "slug": config["slug"],
                "title": config["title"],
                "description": config["description"],
                "focus": config["focus"],
                "entity": detail["entity"],
                "highlights": _build_highlights(detail),
                "relation_preview": (detail["outgoing_relations"] + detail["incoming_relations"])[:6],
                "evidence_preview": detail["mentions"][:3],
            }
        )
    return {"cases": cases}
