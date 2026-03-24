from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
import os
from uuid import uuid4

from django.conf import settings

from .registry import activate_graph, get_active_graph, get_registry_path, list_graph_versions

GRAPH_DIR = Path(settings.DATA_DIR) / "processed" / "graph"
DEFAULT_REVIEWED_GRAPH_DIR = Path(settings.DATA_DIR) / "processed" / "graph-reviewed"
GRAPH_SYNC_DIR = Path(settings.DATA_DIR) / "processed" / "graph-sync"
NEO4J_SYNC_REPORT_PATH = GRAPH_SYNC_DIR / "neo4j_sync_report.json"
DEFAULT_MANUAL_RELATIONS_PATH = Path(settings.DATA_DIR) / "processed" / "graph" / "manual_relation_overrides.json"

RELATION_TYPE_PAIR_RULES = {
    "SYNDROME_HAS_SYMPTOM": ("SYNDROME", "SYMPTOM"),
    "SYNDROME_TO_FORMULA": ("SYNDROME", "FORMULA"),
    "SYNDROME_TO_THERAPY": ("SYNDROME", "THERAPY"),
    "FORMULA_CONTAINS_HERB": ("FORMULA", "HERB"),
    "FORMULA_HAS_ADMINISTRATION": ("FORMULA", "ADMINISTRATION"),
}

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manual_relations_path() -> Path:
    configured = os.getenv("GRAPH_MANUAL_RELATIONS_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_MANUAL_RELATIONS_PATH


def _load_manual_relation_overrides() -> list[dict[str, Any]]:
    path = _manual_relations_path()
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip().lower()
        relation_type = str(item.get("relation_type") or "").strip().upper()
        start_id = str(item.get("start_id") or "").strip()
        end_id = str(item.get("end_id") or "").strip()
        if action not in {"upsert", "suppress"}:
            continue
        if not relation_type or not start_id or not end_id:
            continue
        normalized.append(
            {
                "id": str(item.get("id") or f"manual-{uuid4().hex[:12]}"),
                "graph_id": str(item.get("graph_id") or "").strip(),
                "action": action,
                "relation_type": relation_type,
                "start_id": start_id,
                "end_id": end_id,
                "evidence_count": int(item.get("evidence_count") or 1),
                "record_ids": [str(value) for value in item.get("record_ids", []) if str(value).strip()],
                "example_text": str(item.get("example_text") or ""),
                "created_at": str(item.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or ""),
            }
        )
    return normalized


def _save_manual_relation_overrides(records: list[dict[str, Any]]) -> None:
    path = _manual_relations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"records": records}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_manual_relations(graph_id: str | None = None) -> dict[str, Any]:
    records = _load_manual_relation_overrides()
    active_graph_id = str(get_active_graph_record().get("id") or "")
    target_graph_id = graph_id or active_graph_id
    if target_graph_id:
        filtered = [item for item in records if str(item.get("graph_id") or "") in {"", target_graph_id}]
    else:
        filtered = records
    filtered.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")), reverse=True)
    return {
        "path": str(_manual_relations_path()),
        "total": len(filtered),
        "records": filtered,
    }


def _resolve_manual_relation_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_records = sorted(
        records,
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")),
    )
    final_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in sorted_records:
        relation_key = (
            str(item.get("start_id") or ""),
            str(item.get("end_id") or ""),
            str(item.get("relation_type") or ""),
        )
        if not all(relation_key):
            continue
        final_by_key[relation_key] = item
    return sorted(
        final_by_key.values(),
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")),
    )


def _validate_relation_pair(start_entity: dict[str, Any], end_entity: dict[str, Any], relation_type: str) -> None:
    expected = RELATION_TYPE_PAIR_RULES.get(relation_type)
    if expected is None:
        raise ValueError(f"Unsupported relation_type: {relation_type}")
    actual = (str(start_entity.get("entity_type") or ""), str(end_entity.get("entity_type") or ""))
    if actual != expected:
        raise ValueError(
            f"relation_type {relation_type} requires pair {expected[0]}->{expected[1]}, got {actual[0]}->{actual[1]}"
        )


def _build_manual_relation_record(
    *,
    graph_id: str,
    action: str,
    relation_type: str,
    start_id: str,
    end_id: str,
    example_text: str = "",
    evidence_count: int = 1,
    record_ids: list[str] | None = None,
) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "id": f"manual-{uuid4().hex[:12]}",
        "graph_id": graph_id,
        "action": action,
        "relation_type": relation_type,
        "start_id": start_id,
        "end_id": end_id,
        "evidence_count": max(1, int(evidence_count)),
        "record_ids": [str(item) for item in (record_ids or []) if str(item).strip()],
        "example_text": example_text.strip(),
        "created_at": now,
        "updated_at": now,
    }


def add_manual_relation_upsert(
    *,
    start_id: str,
    end_id: str,
    relation_type: str,
    example_text: str = "",
    evidence_count: int = 1,
    record_ids: list[str] | None = None,
) -> dict[str, Any]:
    data = load_graph_data()
    start_entity = data["entities"].get(start_id)
    end_entity = data["entities"].get(end_id)
    if start_entity is None or end_entity is None:
        raise KeyError("start_id or end_id does not exist in current graph.")

    normalized_relation_type = relation_type.strip().upper()
    _validate_relation_pair(start_entity, end_entity, normalized_relation_type)

    active = get_active_graph_record()
    record = _build_manual_relation_record(
        graph_id=str(active.get("id") or ""),
        action="upsert",
        relation_type=normalized_relation_type,
        start_id=start_id,
        end_id=end_id,
        example_text=example_text,
        evidence_count=evidence_count,
        record_ids=record_ids,
    )
    records = _load_manual_relation_overrides()
    records.append(record)
    _save_manual_relation_overrides(records)
    load_graph_data.cache_clear()
    return record


def add_manual_relation_suppress(
    *,
    start_id: str,
    end_id: str,
    relation_type: str,
    example_text: str = "",
) -> dict[str, Any]:
    data = load_graph_data()
    start_entity = data["entities"].get(start_id)
    end_entity = data["entities"].get(end_id)
    if start_entity is None or end_entity is None:
        raise KeyError("start_id or end_id does not exist in current graph.")

    normalized_relation_type = relation_type.strip().upper()
    _validate_relation_pair(start_entity, end_entity, normalized_relation_type)

    active = get_active_graph_record()
    record = _build_manual_relation_record(
        graph_id=str(active.get("id") or ""),
        action="suppress",
        relation_type=normalized_relation_type,
        start_id=start_id,
        end_id=end_id,
        example_text=example_text,
        evidence_count=1,
        record_ids=[],
    )
    records = _load_manual_relation_overrides()
    records.append(record)
    _save_manual_relation_overrides(records)
    load_graph_data.cache_clear()
    return record


def delete_manual_relation(override_id: str) -> dict[str, Any]:
    records = _load_manual_relation_overrides()
    target = None
    kept: list[dict[str, Any]] = []
    for record in records:
        if str(record.get("id") or "") == override_id:
            target = record
            continue
        kept.append(record)
    if target is None:
        raise KeyError(override_id)
    _save_manual_relation_overrides(kept)
    load_graph_data.cache_clear()
    return target


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
    active_graph_id = str(active_graph.get("id") or "")
    manual_records = _resolve_manual_relation_records(
        [
            item
            for item in _load_manual_relation_overrides()
            if str(item.get("graph_id") or "") in {"", active_graph_id}
        ]
    )

    try:
        summary = import_graph(
            graph_dir=target_graph_dir,
            uri=uri,
            username=username,
            password=password,
            database=database,
            batch_size=batch_size,
            manual_overrides=manual_records,
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

    relation_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in relation_rows:
        relation = {
            "start_id": row[":START_ID(Entity-ID)"],
            "end_id": row[":END_ID(Entity-ID)"],
            "relation_type": row[":TYPE"],
            "evidence_count": int(row["evidence_count:int"]),
            "record_ids": row["record_ids"].split("|") if row["record_ids"] else [],
            "example_text": row["example_text"],
            "manual_override": False,
            "manual_override_id": None,
        }
        relation_key = (relation["start_id"], relation["end_id"], relation["relation_type"])
        relation_map[relation_key] = relation

    active_graph_id = str(active_graph.get("id") or "")
    manual_records = [
        item
        for item in _load_manual_relation_overrides()
        if str(item.get("graph_id") or "") in {"", active_graph_id}
    ]
    manual_records = _resolve_manual_relation_records(manual_records)

    for item in manual_records:
        relation_key = (
            str(item.get("start_id") or ""),
            str(item.get("end_id") or ""),
            str(item.get("relation_type") or ""),
        )
        if item.get("action") == "suppress":
            relation_map.pop(relation_key, None)
            continue

        if item.get("action") == "upsert":
            relation_map[relation_key] = {
                "start_id": relation_key[0],
                "end_id": relation_key[1],
                "relation_type": relation_key[2],
                "evidence_count": int(item.get("evidence_count") or 1),
                "record_ids": [str(value) for value in item.get("record_ids", []) if str(value).strip()],
                "example_text": str(item.get("example_text") or ""),
                "manual_override": True,
                "manual_override_id": str(item.get("id") or ""),
            }

    for relation in relation_map.values():
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
        "manual_override": bool(relation.get("manual_override")),
        "manual_override_id": relation.get("manual_override_id"),
        "related_entity": related_entity,
    }


def _entity_brief(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": entity["entity_id"],
        "entity_type": entity["entity_type"],
        "name": entity["name"],
    }


def _outgoing_relations_by_type(data: dict[str, Any], entity_id: str, relation_type: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for relation in data["outgoing_relations"].get(entity_id, []):
        if relation["relation_type"] != relation_type:
            continue
        related = data["entities"].get(relation["end_id"])
        if related is None:
            continue
        rows.append((relation, related))
    rows.sort(key=lambda item: (-item[0]["evidence_count"], item[1]["name"], item[1]["entity_id"]))
    return rows


def _incoming_relations_by_type(data: dict[str, Any], entity_id: str, relation_type: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for relation in data["incoming_relations"].get(entity_id, []):
        if relation["relation_type"] != relation_type:
            continue
        related = data["entities"].get(relation["start_id"])
        if related is None:
            continue
        rows.append((relation, related))
    rows.sort(key=lambda item: (-item[0]["evidence_count"], item[1]["name"], item[1]["entity_id"]))
    return rows


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


def build_entity_pathways(entity_id: str, limit: int = 20) -> dict[str, Any]:
    data = load_graph_data()
    entity = data["entities"].get(entity_id)
    if entity is None:
        raise KeyError(entity_id)

    safe_limit = max(1, min(limit, 100))
    focus_type = entity["entity_type"]
    focus_id = entity["entity_id"]

    pair_map: dict[tuple[str, str], dict[str, Any]] = {}

    def add_pair(syndrome_id: str, formula_id: str, relation: dict[str, Any]) -> None:
        key = (syndrome_id, formula_id)
        existing = pair_map.get(key)
        if existing is None or relation["evidence_count"] > existing["relation"]["evidence_count"]:
            pair_map[key] = {"relation": relation}

    if focus_type == "SYNDROME":
        for relation, formula in _outgoing_relations_by_type(data, focus_id, "SYNDROME_TO_FORMULA"):
            add_pair(focus_id, formula["entity_id"], relation)
    elif focus_type == "FORMULA":
        for relation, syndrome in _incoming_relations_by_type(data, focus_id, "SYNDROME_TO_FORMULA"):
            add_pair(syndrome["entity_id"], focus_id, relation)
    elif focus_type == "SYMPTOM":
        for _, syndrome in _incoming_relations_by_type(data, focus_id, "SYNDROME_HAS_SYMPTOM"):
            for relation, formula in _outgoing_relations_by_type(data, syndrome["entity_id"], "SYNDROME_TO_FORMULA"):
                add_pair(syndrome["entity_id"], formula["entity_id"], relation)
    elif focus_type == "HERB":
        for _, formula in _incoming_relations_by_type(data, focus_id, "FORMULA_CONTAINS_HERB"):
            for relation, syndrome in _incoming_relations_by_type(data, formula["entity_id"], "SYNDROME_TO_FORMULA"):
                add_pair(syndrome["entity_id"], formula["entity_id"], relation)
    elif focus_type == "ADMINISTRATION":
        for _, formula in _incoming_relations_by_type(data, focus_id, "FORMULA_HAS_ADMINISTRATION"):
            for relation, syndrome in _incoming_relations_by_type(data, formula["entity_id"], "SYNDROME_TO_FORMULA"):
                add_pair(syndrome["entity_id"], formula["entity_id"], relation)

    path_index: dict[str, dict[str, Any]] = {}

    def add_path(path_type: str, nodes: list[dict[str, Any]], relations: list[dict[str, Any]]) -> None:
        node_ids = [str(item["entity_id"]) for item in nodes]
        relation_types = [str(item["relation_type"]) for item in relations]
        dedupe_key = f"{path_type}|{'|'.join(node_ids)}|{'|'.join(relation_types)}"
        if dedupe_key in path_index:
            return
        evidence_score = int(sum(int(item["evidence_count"]) for item in relations))
        path_index[dedupe_key] = {
            "path_type": path_type,
            "nodes": [_entity_brief(item) for item in nodes],
            "relations": [
                {
                    "relation_type": item["relation_type"],
                    "start_entity_id": item["start_id"],
                    "end_entity_id": item["end_id"],
                    "evidence_count": int(item["evidence_count"]),
                }
                for item in relations
            ],
            "evidence_score": evidence_score,
            "chain_text": " -> ".join(str(item["name"]) for item in nodes),
        }

    for (syndrome_id, formula_id), pair_payload in pair_map.items():
        syndrome = data["entities"].get(syndrome_id)
        formula = data["entities"].get(formula_id)
        relation = pair_payload["relation"]
        if syndrome is None or formula is None:
            continue

        add_path("SYNDROME_TO_FORMULA", [syndrome, formula], [relation])

        symptoms = _outgoing_relations_by_type(data, syndrome_id, "SYNDROME_HAS_SYMPTOM")
        for symptom_relation, symptom in symptoms[:3]:
            add_path(
                "SYMPTOM_SYNDROME_FORMULA",
                [symptom, syndrome, formula],
                [symptom_relation, relation],
            )

        herbs = _outgoing_relations_by_type(data, formula_id, "FORMULA_CONTAINS_HERB")
        for herb_relation, herb in herbs[:4]:
            add_path(
                "SYNDROME_FORMULA_HERB",
                [syndrome, formula, herb],
                [relation, herb_relation],
            )

        administrations = _outgoing_relations_by_type(data, formula_id, "FORMULA_HAS_ADMINISTRATION")
        for administration_relation, administration in administrations[:2]:
            add_path(
                "SYNDROME_FORMULA_ADMINISTRATION",
                [syndrome, formula, administration],
                [relation, administration_relation],
            )

    if focus_type == "FORMULA":
        formula = entity
        for herb_relation, herb in _outgoing_relations_by_type(data, focus_id, "FORMULA_CONTAINS_HERB")[:6]:
            add_path("FORMULA_HERB", [formula, herb], [herb_relation])
        for administration_relation, administration in _outgoing_relations_by_type(data, focus_id, "FORMULA_HAS_ADMINISTRATION")[:3]:
            add_path("FORMULA_ADMINISTRATION", [formula, administration], [administration_relation])
    elif focus_type == "SYNDROME":
        syndrome = entity
        for symptom_relation, symptom in _outgoing_relations_by_type(data, focus_id, "SYNDROME_HAS_SYMPTOM")[:6]:
            add_path("SYNDROME_SYMPTOM", [syndrome, symptom], [symptom_relation])

    paths = sorted(
        path_index.values(),
        key=lambda item: (-item["evidence_score"], len(item["nodes"]), item["chain_text"]),
    )

    return {
        "entity": _entity_brief(entity),
        "total": len(paths),
        "paths": paths[:safe_limit],
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
