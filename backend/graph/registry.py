from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "processed" / "graph_registry.json"


def get_registry_path() -> Path:
    configured = os.getenv("GRAPH_REGISTRY_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_REGISTRY_PATH


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _empty_registry() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": iso_now(),
        "graphs": [],
    }


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or get_registry_path()
    if not registry_path.exists():
        return _empty_registry()

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _empty_registry()
    graphs = payload.get("graphs")
    if not isinstance(graphs, list):
        payload["graphs"] = []
    payload.setdefault("version", 1)
    payload.setdefault("updated_at", iso_now())
    return payload


def save_registry(registry: dict[str, Any], path: Path | None = None) -> Path:
    registry_path = path or get_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry["updated_at"] = iso_now()
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry_path


def infer_graph_source(input_path: str | Path | None) -> str:
    normalized = str(input_path or "").replace("\\", "/").lower()
    if "accepted" in normalized:
        return "accepted_reviewed"
    if "silver" in normalized:
        return "cleaned_silver"
    return "custom"


def _build_record(summary: dict[str, Any], activate: bool) -> dict[str, Any]:
    input_path = str(summary.get("input_path") or "")
    output_dir = str(summary.get("output_dir") or "")
    return {
        "id": summary.get("registry_id") or f"graph-{uuid4().hex[:12]}",
        "run_name": str(summary.get("run_name") or Path(output_dir).name or "graph-export"),
        "source_input": input_path,
        "source_type": str(summary.get("source_type") or infer_graph_source(input_path)),
        "output_dir": output_dir,
        "stats": dict(summary.get("stats") or {}),
        "created_at": str(summary.get("created_at") or iso_now()),
        "updated_at": iso_now(),
        "is_active": activate,
    }


def register_graph_export(summary: dict[str, Any], activate: bool = True, path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path=path)
    records = list(registry.get("graphs") or [])
    record = _build_record(summary=summary, activate=activate)

    updated_records: list[dict[str, Any]] = []
    replaced = False
    for existing in records:
        if existing.get("id") == record["id"] or existing.get("output_dir") == record["output_dir"]:
            existing = {**existing, **record}
            replaced = True
        if activate:
            existing["is_active"] = existing.get("id") == record["id"]
        updated_records.append(existing)

    if not replaced:
        if activate:
            for existing in updated_records:
                existing["is_active"] = False
        updated_records.append(record)

    registry["graphs"] = updated_records
    save_registry(registry, path=path)
    return record


def list_graph_versions(path: Path | None = None) -> list[dict[str, Any]]:
    registry = load_registry(path=path)
    records = list(registry.get("graphs") or [])
    return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def get_active_graph(path: Path | None = None) -> dict[str, Any] | None:
    for record in list_graph_versions(path=path):
        if record.get("is_active"):
            return record
    return None


def activate_graph(graph_id: str, path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path=path)
    found: dict[str, Any] | None = None
    for record in registry.get("graphs", []):
        is_selected = record.get("id") == graph_id
        record["is_active"] = is_selected
        record["updated_at"] = iso_now()
        if is_selected:
            found = record

    if found is None:
        raise KeyError(f"Graph version not found: {graph_id}")

    save_registry(registry, path=path)
    return found
