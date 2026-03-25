from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
import os
from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings

from .registry import activate_graph, get_active_graph, get_registry_path, list_graph_versions
try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover
    GraphDatabase = None

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

ENTITY_TYPE_ZH = {
    "SYNDROME": "证候",
    "SYMPTOM": "症状",
    "FORMULA": "方剂",
    "HERB": "中药",
    "THERAPY": "治法",
    "ADMINISTRATION": "服法",
}

RELATION_TYPE_ZH = {
    "SYNDROME_HAS_SYMPTOM": "证候具有症状",
    "SYNDROME_TO_FORMULA": "证候对应方剂",
    "SYNDROME_TO_THERAPY": "证候采用治法",
    "FORMULA_CONTAINS_HERB": "方剂包含中药",
    "FORMULA_HAS_ADMINISTRATION": "方剂具有服法",
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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_neo4j_host_port(uri: str) -> tuple[str, int]:
    normalized = uri if "://" in uri else f"bolt://{uri}"
    parsed = urlparse(normalized)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 7687)
    return host, port


def _is_tcp_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _candidate_neo4j_dbms_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".Neo4jDesktop2" / "Data" / "dbmss",
        home / ".Neo4jDesktop" / "relate-data" / "dbmss",
    ]


def _discover_neo4j_desktop_dbms_home() -> Path | None:
    configured_id = str(os.getenv("NEO4J_DESKTOP_DBMS_ID") or "").strip()
    normalized_id = configured_id if configured_id.startswith("dbms-") else f"dbms-{configured_id}" if configured_id else ""

    for root in _candidate_neo4j_dbms_roots():
        if not root.exists():
            continue
        if normalized_id:
            explicit = root / normalized_id
            if (explicit / "bin" / "neo4j.bat").exists():
                return explicit

        candidates = [item for item in root.iterdir() if item.is_dir() and (item / "bin" / "neo4j.bat").exists()]
        if not candidates:
            continue
        candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return candidates[0]
    return None


def _resolve_neo4j_start_commands() -> tuple[list[str], str | None]:
    custom_command = str(os.getenv("NEO4J_START_COMMAND") or "").strip()
    if custom_command:
        return [custom_command], None

    configured_home = str(os.getenv("NEO4J_DESKTOP_DBMS_HOME") or "").strip()
    dbms_home = Path(configured_home) if configured_home else _discover_neo4j_desktop_dbms_home()
    if dbms_home is None:
        return [], None

    neo4j_bat = dbms_home / "bin" / "neo4j.bat"
    if not neo4j_bat.exists():
        return [], None
    quoted = f"\"{neo4j_bat}\""
    return [f"{quoted} start", f"{quoted} console"], str(dbms_home)


def _attempt_auto_start_neo4j(uri: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "enabled": _env_flag("NEO4J_AUTO_START", default=False),
        "attempted": False,
        "started": False,
        "detail": "",
    }
    if not report["enabled"]:
        report["detail"] = "auto-start disabled."
        return report

    host, port = _parse_neo4j_host_port(uri)
    if _is_tcp_port_open(host, port):
        report["started"] = True
        report["detail"] = "neo4j already running."
        return report

    commands, cwd = _resolve_neo4j_start_commands()
    report["attempted"] = True
    report["commands"] = commands
    report["cwd"] = cwd
    if not commands:
        report["detail"] = "未找到 Neo4j 启动命令，请配置 NEO4J_DESKTOP_DBMS_HOME 或 NEO4J_START_COMMAND。"
        return report

    timeout_sec = int(os.getenv("NEO4J_AUTO_START_TIMEOUT_SEC", "25") or "25")
    deadline = time.time() + max(10, timeout_sec)
    per_command_window = max(6, timeout_sec // max(1, len(commands)))
    launch_records: list[dict[str, Any]] = []
    last_error = ""

    for command in commands:
        try:
            creation_flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            process = subprocess.Popen(
                command,
                cwd=cwd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            launch_records.append({"command": command, "pid": int(process.pid or 0)})
        except Exception as exc:
            last_error = str(exc)
            launch_records.append({"command": command, "error": last_error})
            continue

        command_deadline = min(deadline, time.time() + per_command_window)
        while time.time() < command_deadline:
            if _is_tcp_port_open(host, port):
                report["started"] = True
                report["detail"] = f"Neo4j 已自动启动（命令：{command}）。"
                report["launches"] = launch_records
                return report
            time.sleep(0.5)

    report["launches"] = launch_records
    if last_error:
        report["detail"] = f"已尝试自动启动，但端口仍未就绪：{last_error}"
    else:
        report["detail"] = "已尝试自动启动（含 console 回退），但端口仍未就绪。"
    return report


def _friendly_graph_sync_error(exc: Exception) -> str:
    raw = str(exc)
    lowered = raw.lower()
    if "winerror 10061" in lowered or "couldn't connect to" in lowered or "failed to establish connection" in lowered:
        return "无法连接 Neo4j（127.0.0.1:7687）。请确认 Neo4j Desktop 实例已启动，且 Bolt 端口为 7687。"
    if "authentication" in lowered or "unauthorized" in lowered:
        return "Neo4j 认证失败。请检查用户名或密码配置。"
    if "serviceunavailable" in lowered:
        return "Neo4j 服务不可用。请确认数据库实例处于运行状态。"
    return f"Neo4j 同步失败：{raw}"


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
        raise ValueError(f"不支持的关系类型：{relation_type}")
    actual = (str(start_entity.get("entity_type") or ""), str(end_entity.get("entity_type") or ""))
    if actual != expected:
        relation_label = RELATION_TYPE_ZH.get(relation_type, relation_type)
        expected_pair = f"{ENTITY_TYPE_ZH.get(expected[0], expected[0])} -> {ENTITY_TYPE_ZH.get(expected[1], expected[1])}"
        actual_pair = f"{ENTITY_TYPE_ZH.get(actual[0], actual[0])} -> {ENTITY_TYPE_ZH.get(actual[1], actual[1])}"
        raise ValueError(
            f"关系类型“{relation_label}”的实体方向不匹配：要求 {expected_pair}，当前为 {actual_pair}。"
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
    auto_start_report = _attempt_auto_start_neo4j(uri)
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
        friendly_detail = _friendly_graph_sync_error(exc)
        payload = {
            "ok": False,
            "detail": friendly_detail,
            "raw_error": str(exc),
            "auto_start": auto_start_report,
            "graph_version": active_graph,
            "graph_dir": str(target_graph_dir),
            "uri": uri,
            "database": database,
        }
        _write_neo4j_sync_report(payload)
        raise GraphSyncError(friendly_detail) from exc

    payload = {
        "ok": True,
        "detail": "neo4j sync completed.",
        "graph_version": active_graph,
        "graph_dir": str(target_graph_dir),
        "uri": uri,
        "database": database,
        "summary": summary,
        "auto_start": auto_start_report,
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


def _read_graph_query_source() -> str:
    raw = str(os.getenv("GRAPH_QUERY_SOURCE", "csv") or "csv").strip().lower()
    if raw not in {"csv", "neo4j"}:
        return "csv"
    return raw


def _read_graph_query_fallback_to_csv() -> bool:
    raw = str(os.getenv("GRAPH_QUERY_FALLBACK_TO_CSV", "true") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def _get_neo4j_driver():
    if GraphDatabase is None:
        raise GraphDataUnavailableError("neo4j package is not installed in current environment.")
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4jpassword")
    return GraphDatabase.driver(uri, auth=(username, password))


def _run_neo4j_read(query: str, **params: Any) -> list[dict[str, Any]]:
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    driver = _get_neo4j_driver()
    with driver.session(database=database) as session:
        result = session.run(query, params)
        return [record.data() for record in result]


def _split_entry_types(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [item for item in text.split("|") if item]


def _base_summary_from_graph_dir(paths: dict[str, Path], clauses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    summary_path = paths["summary"]
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "input_record_count": len({str(item["record_id"]) for item in clauses.values()}),
        "entity_node_count": 0,
        "clause_node_count": len(clauses),
        "entity_relation_count": 0,
        "clause_mention_count": 0,
    }


def _finalize_graph_payload(
    *,
    summary: dict[str, Any],
    active_graph: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    clauses: dict[str, dict[str, Any]],
    outgoing_relations: dict[str, list[dict[str, Any]]],
    incoming_relations: dict[str, list[dict[str, Any]]],
    mentions_by_entity: dict[str, list[dict[str, Any]]],
    entity_type_breakdown: Counter[str],
    relation_type_breakdown: Counter[str],
    query_source: str,
) -> dict[str, Any]:
    for relation_list in outgoing_relations.values():
        relation_list.sort(key=lambda item: (-int(item["evidence_count"]), str(item["relation_type"]), str(item["end_id"])))
    for relation_list in incoming_relations.values():
        relation_list.sort(key=lambda item: (-int(item["evidence_count"]), str(item["relation_type"]), str(item["start_id"])))
    for mention_list in mentions_by_entity.values():
        mention_list.sort(key=lambda item: (str(item["record_id"]), int(item["start"]), int(item["end"])))

    summary["entity_node_count"] = len(entities)
    summary["clause_node_count"] = len(clauses)
    summary["entity_relation_count"] = int(sum(len(rows) for rows in outgoing_relations.values()))
    summary["clause_mention_count"] = int(sum(len(rows) for rows in mentions_by_entity.values()))
    summary["entity_type_breakdown"] = dict(sorted(entity_type_breakdown.items()))
    summary["relation_type_breakdown"] = dict(sorted(relation_type_breakdown.items()))
    summary["graph_version"] = active_graph
    summary["query_source"] = query_source

    if "input_record_count" not in summary:
        summary["input_record_count"] = len({str(item["record_id"]) for item in clauses.values()})

    return {
        "summary": summary,
        "entities": entities,
        "clauses": clauses,
        "outgoing_relations": outgoing_relations,
        "incoming_relations": incoming_relations,
        "mentions_by_entity": mentions_by_entity,
    }


def _load_graph_data_from_csv() -> dict[str, Any]:
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

    return _finalize_graph_payload(
        summary=summary,
        active_graph=active_graph,
        entities=entities,
        clauses=clauses,
        outgoing_relations=outgoing_relations,
        incoming_relations=incoming_relations,
        mentions_by_entity=mentions_by_entity,
        entity_type_breakdown=entity_type_breakdown,
        relation_type_breakdown=relation_type_breakdown,
        query_source="csv",
    )


def _load_graph_data_from_neo4j() -> dict[str, Any]:
    active_graph = get_active_graph_record()
    graph_dir = Path(str(active_graph.get("output_dir") or GRAPH_DIR))
    paths = _graph_paths(graph_dir)

    entities: dict[str, dict[str, Any]] = {}
    clauses: dict[str, dict[str, Any]] = {}
    outgoing_relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming_relations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mentions_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entity_type_breakdown: Counter[str] = Counter()
    relation_type_breakdown: Counter[str] = Counter()

    entity_rows = _run_neo4j_read(
        """
        MATCH (e:Entity)
        RETURN
          e.entity_id AS entity_id,
          e.entity_type AS entity_type,
          e.name AS name,
          coalesce(e.mention_count, 0) AS mention_count,
          coalesce(e.record_count, 0) AS record_count,
          coalesce(e.first_record_id, "") AS first_record_id,
          coalesce(e.entry_types, []) AS entry_types,
          labels(e) AS labels
        """
    )
    for row in entity_rows:
        entity_id = str(row.get("entity_id") or "")
        if not entity_id:
            continue
        entity_type = str(row.get("entity_type") or "")
        entity = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "name": str(row.get("name") or ""),
            "mention_count": int(row.get("mention_count") or 0),
            "record_count": int(row.get("record_count") or 0),
            "first_record_id": str(row.get("first_record_id") or ""),
            "entry_types": _split_entry_types(row.get("entry_types")),
            "labels": [str(item) for item in (row.get("labels") or []) if str(item).strip()],
        }
        entities[entity_id] = entity
        if entity_type:
            entity_type_breakdown[entity_type] += 1

    clause_rows = _run_neo4j_read(
        """
        MATCH (c:Clause)
        RETURN
          c.clause_id AS clause_id,
          coalesce(c.record_id, "") AS record_id,
          coalesce(c.line_number, 0) AS line_number,
          coalesce(c.entry_type, "") AS entry_type,
          coalesce(c.text, "") AS text
        """
    )
    for row in clause_rows:
        clause_id = str(row.get("clause_id") or "")
        if not clause_id:
            continue
        clauses[clause_id] = {
            "clause_id": clause_id,
            "record_id": str(row.get("record_id") or ""),
            "line_number": int(row.get("line_number") or 0),
            "entry_type": str(row.get("entry_type") or ""),
            "text": str(row.get("text") or ""),
        }

    relation_rows = _run_neo4j_read(
        """
        MATCH (source:Entity)-[r]->(target:Entity)
        WHERE type(r) IN $relation_types
        RETURN
          source.entity_id AS start_id,
          target.entity_id AS end_id,
          type(r) AS relation_type,
          coalesce(r.evidence_count, 1) AS evidence_count,
          coalesce(r.record_ids, []) AS record_ids,
          coalesce(r.example_text, "") AS example_text,
          coalesce(r.manual_override, false) AS manual_override,
          coalesce(r.manual_override_id, "") AS manual_override_id
        """,
        relation_types=list(RELATION_TYPE_PAIR_RULES.keys()),
    )
    for row in relation_rows:
        start_id = str(row.get("start_id") or "")
        end_id = str(row.get("end_id") or "")
        relation_type = str(row.get("relation_type") or "")
        if not start_id or not end_id or not relation_type:
            continue
        relation = {
            "start_id": start_id,
            "end_id": end_id,
            "relation_type": relation_type,
            "evidence_count": int(row.get("evidence_count") or 1),
            "record_ids": [str(item) for item in (row.get("record_ids") or []) if str(item).strip()],
            "example_text": str(row.get("example_text") or ""),
            "manual_override": bool(row.get("manual_override")),
            "manual_override_id": str(row.get("manual_override_id") or "") or None,
        }
        relation_type_breakdown[relation_type] += 1
        outgoing_relations[start_id].append(relation)
        incoming_relations[end_id].append(relation)

    mention_rows = _run_neo4j_read(
        """
        MATCH (c:Clause)-[m:CLAUSE_MENTIONS_ENTITY]->(e:Entity)
        RETURN
          c.clause_id AS clause_id,
          coalesce(c.record_id, m.record_id, "") AS record_id,
          coalesce(c.entry_type, "") AS entry_type,
          coalesce(c.line_number, 0) AS line_number,
          coalesce(c.text, "") AS clause_text,
          e.entity_id AS entity_id,
          coalesce(m.entity_type, e.entity_type, "") AS entity_type,
          coalesce(m.mention_text, e.name, "") AS mention_text,
          coalesce(m.start, 0) AS start,
          coalesce(m.end, 0) AS end
        """
    )
    for row in mention_rows:
        entity_id = str(row.get("entity_id") or "")
        if not entity_id:
            continue
        mention = {
            "clause_id": str(row.get("clause_id") or ""),
            "record_id": str(row.get("record_id") or ""),
            "entity_type": str(row.get("entity_type") or ""),
            "mention_text": str(row.get("mention_text") or ""),
            "start": int(row.get("start") or 0),
            "end": int(row.get("end") or 0),
            "clause_text": str(row.get("clause_text") or ""),
            "entry_type": str(row.get("entry_type") or "") or None,
            "line_number": int(row.get("line_number") or 0),
        }
        mentions_by_entity[entity_id].append(mention)

    summary = _base_summary_from_graph_dir(paths, clauses)
    return _finalize_graph_payload(
        summary=summary,
        active_graph=active_graph,
        entities=entities,
        clauses=clauses,
        outgoing_relations=outgoing_relations,
        incoming_relations=incoming_relations,
        mentions_by_entity=mentions_by_entity,
        entity_type_breakdown=entity_type_breakdown,
        relation_type_breakdown=relation_type_breakdown,
        query_source="neo4j",
    )


@lru_cache(maxsize=1)
def load_graph_data() -> dict[str, Any]:
    source = _read_graph_query_source()
    if source == "neo4j":
        try:
            return _load_graph_data_from_neo4j()
        except Exception:
            if not _read_graph_query_fallback_to_csv():
                raise
            return _load_graph_data_from_csv()
    return _load_graph_data_from_csv()


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

    def resolve_first_clause_text(entity_id: str, first_record_id: str) -> str:
        mentions = data["mentions_by_entity"].get(entity_id, [])
        if mentions:
            first_mention = min(
                mentions,
                key=lambda item: (
                    str(item.get("record_id") or ""),
                    int(item.get("start") or 0),
                    int(item.get("end") or 0),
                    str(item.get("clause_id") or ""),
                ),
            )
            clause_text = str(first_mention.get("clause_text") or "").strip()
            if clause_text:
                return clause_text
            clause_id = str(first_mention.get("clause_id") or "").strip()
            if clause_id:
                clause = data["clauses"].get(clause_id)
                if clause:
                    return str(clause.get("text") or "").strip()

        normalized_record_id = str(first_record_id or "").strip()
        if normalized_record_id:
            candidates = [item for item in data["clauses"].values() if str(item.get("record_id") or "") == normalized_record_id]
            if candidates:
                first_clause = min(
                    candidates,
                    key=lambda item: (
                        int(item.get("line_number") or 0),
                        str(item.get("clause_id") or ""),
                    ),
                )
                return str(first_clause.get("text") or "").strip()
        return ""

    results = []
    for entity in data["entities"].values():
        if normalized_type and entity["entity_type"] != normalized_type:
            continue
        if normalized_keyword and normalized_keyword not in entity["name"] and normalized_keyword not in entity["entity_id"]:
            continue
        results.append(
            {
                **entity,
                "first_clause_text": resolve_first_clause_text(
                    entity_id=str(entity.get("entity_id") or ""),
                    first_record_id=str(entity.get("first_record_id") or ""),
                ),
            }
        )

    results.sort(key=lambda item: (-item["mention_count"], item["entity_type"], item["name"]))
    return {
        "keyword": normalized_keyword,
        "entity_type": normalized_type or None,
        "total": len(results),
        "results": results[:safe_limit],
    }


def _build_clause_mentions(data: dict[str, Any], clause_id: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for entity_id, rows in data["mentions_by_entity"].items():
        entity = data["entities"].get(entity_id)
        if entity is None:
            continue
        for row in rows:
            if str(row.get("clause_id") or "") != clause_id:
                continue
            signature = f"{entity_id}|{int(row.get('start') or 0)}|{int(row.get('end') or 0)}|{str(row.get('mention_text') or '')}"
            if signature in seen_keys:
                continue
            seen_keys.add(signature)
            mentions.append(
                {
                    "entity_id": entity_id,
                    "entity_name": entity["name"],
                    "entity_type": entity["entity_type"],
                    "mention_text": str(row.get("mention_text") or ""),
                    "start": int(row.get("start") or 0),
                    "end": int(row.get("end") or 0),
                }
            )
    mentions.sort(key=lambda item: (item["start"], item["end"], item["entity_type"], item["entity_name"]))
    return mentions


def search_clauses(
    keyword: str = "",
    entry_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    data = load_graph_data()
    normalized_keyword = keyword.strip()
    normalized_entry_type = (entry_type or "").strip()
    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size), 100))

    rows: list[dict[str, Any]] = []
    for clause in data["clauses"].values():
        text = str(clause.get("text") or "")
        clause_id = str(clause.get("clause_id") or "")
        record_id = str(clause.get("record_id") or "")
        current_entry_type = str(clause.get("entry_type") or "")

        if normalized_entry_type and current_entry_type != normalized_entry_type:
            continue
        if normalized_keyword and normalized_keyword not in text and normalized_keyword not in clause_id and normalized_keyword not in record_id:
            continue

        rows.append(
            {
                "clause_id": clause_id,
                "record_id": record_id,
                "line_number": clause.get("line_number"),
                "entry_type": clause.get("entry_type"),
                "text": text,
            }
        )

    rows.sort(key=lambda item: (str(item["record_id"]), int(item.get("line_number") or 0), str(item["clause_id"])))
    total = len(rows)
    total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    if total_pages and safe_page > total_pages:
        safe_page = total_pages
    offset = (safe_page - 1) * safe_page_size
    paged_rows = rows[offset : offset + safe_page_size]

    results = []
    for item in paged_rows:
        mentions = _build_clause_mentions(data, item["clause_id"])
        results.append(
            {
                **item,
                "mention_count": len(mentions),
                "entity_types": sorted({mention["entity_type"] for mention in mentions}),
            }
        )

    return {
        "keyword": normalized_keyword,
        "entry_type": normalized_entry_type or None,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
        "has_next": safe_page < total_pages,
        "has_previous": safe_page > 1 and total_pages > 0,
        "results": results,
    }


def get_clause_detail(clause_id: str) -> dict[str, Any]:
    data = load_graph_data()
    clause = data["clauses"].get(clause_id)
    if clause is None:
        raise KeyError(clause_id)

    mentions = _build_clause_mentions(data, clause_id)
    mention_entity_ids = {str(item["entity_id"]) for item in mentions}
    relations: list[dict[str, Any]] = []
    seen_relations: set[str] = set()

    for start_id in mention_entity_ids:
        for relation in data["outgoing_relations"].get(start_id, []):
            end_id = str(relation.get("end_id") or "")
            if end_id not in mention_entity_ids:
                continue
            start_entity = data["entities"].get(start_id)
            end_entity = data["entities"].get(end_id)
            if start_entity is None or end_entity is None:
                continue
            signature = f"{start_id}|{end_id}|{relation['relation_type']}"
            if signature in seen_relations:
                continue
            seen_relations.add(signature)
            relations.append(
                {
                    "relation_type": relation["relation_type"],
                    "evidence_count": int(relation.get("evidence_count") or 0),
                    "start_entity": _entity_brief(start_entity),
                    "end_entity": _entity_brief(end_entity),
                }
            )

    relations.sort(
        key=lambda item: (
            item["relation_type"],
            item["start_entity"]["entity_type"],
            item["start_entity"]["name"],
            item["end_entity"]["entity_type"],
            item["end_entity"]["name"],
        )
    )

    return {
        "clause": {
            "clause_id": clause["clause_id"],
            "record_id": clause["record_id"],
            "line_number": clause["line_number"],
            "entry_type": clause["entry_type"],
            "text": clause["text"],
        },
        "mentions": mentions,
        "relations": relations,
        "stats": {
            "mention_count": len(mentions),
            "entity_count": len(mention_entity_ids),
            "relation_count": len(relations),
        },
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
