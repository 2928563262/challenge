from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "processed" / "model_registry.json"
SUPPORTED_TASKS = {"ner", "relation"}


def get_registry_path() -> Path:
    configured = os.getenv("MODEL_REGISTRY_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_REGISTRY_PATH


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _empty_registry() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": iso_now(),
        "models": [],
    }


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or get_registry_path()
    if not registry_path.exists():
        return _empty_registry()

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _empty_registry()

    models = payload.get("models")
    if not isinstance(models, list):
        payload["models"] = []
    payload.setdefault("version", 1)
    payload.setdefault("updated_at", iso_now())
    return payload


def save_registry(registry: dict[str, Any], path: Path | None = None) -> Path:
    registry_path = path or get_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry["updated_at"] = iso_now()
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry_path


def infer_dataset_source(dataset_dir: str | Path | None) -> str:
    normalized = str(dataset_dir or "").replace("\\", "/").lower()
    if "/merged/" in normalized:
        return "merged"
    if "/annotation/incremental" in normalized:
        return "incremental"
    return "baseline"


def _coerce_task(task: str) -> str:
    normalized = task.strip().lower()
    if normalized not in SUPPORTED_TASKS:
        raise ValueError(f"Unsupported task: {task}")
    return normalized


def _build_record(summary: dict[str, Any], task: str, is_active: bool) -> dict[str, Any]:
    dataset_dir = str(summary.get("dataset_dir") or "")
    output_dir = str(summary.get("output_dir") or "")
    validation_metrics = dict(summary.get("validation_metrics") or {})
    return {
        "id": summary.get("registry_id") or f"{task}-{uuid4().hex[:12]}",
        "task": task,
        "run_name": str(summary.get("run_name") or ""),
        "model_name": str(summary.get("model_name") or ""),
        "model_dir": output_dir,
        "dataset_dir": dataset_dir,
        "dataset_source": str(summary.get("dataset_source") or infer_dataset_source(dataset_dir)),
        "label_list": list(summary.get("label_list") or []),
        "validation_metrics": validation_metrics,
        "train_metrics": dict(summary.get("train_metrics") or {}),
        "test_metrics": dict(summary.get("test_metrics") or {}),
        "created_at": str(summary.get("created_at") or iso_now()),
        "updated_at": iso_now(),
        "is_active": is_active,
    }


def register_model_run(
    summary: dict[str, Any],
    task: str,
    activate: bool = False,
    path: Path | None = None,
) -> dict[str, Any]:
    normalized_task = _coerce_task(task)
    registry = load_registry(path=path)
    records = list(registry.get("models") or [])
    record = _build_record(summary=summary, task=normalized_task, is_active=activate)

    updated_records: list[dict[str, Any]] = []
    replaced = False
    for existing in records:
        if existing.get("id") == record["id"] or (
            existing.get("task") == normalized_task and existing.get("model_dir") == record["model_dir"]
        ):
            existing = {**existing, **record}
            replaced = True
        if activate and existing.get("task") == normalized_task:
            existing["is_active"] = existing.get("id") == record["id"]
        updated_records.append(existing)

    if not replaced:
        if activate:
            for existing in updated_records:
                if existing.get("task") == normalized_task:
                    existing["is_active"] = False
        updated_records.append(record)

    registry["models"] = updated_records
    save_registry(registry, path=path)
    return record


def activate_model(task: str, model_id: str, path: Path | None = None) -> dict[str, Any]:
    normalized_task = _coerce_task(task)
    registry = load_registry(path=path)
    found: dict[str, Any] | None = None
    for record in registry.get("models", []):
        if record.get("task") != normalized_task:
            continue
        is_selected = record.get("id") == model_id
        record["is_active"] = is_selected
        record["updated_at"] = iso_now()
        if is_selected:
            found = record

    if found is None:
        raise KeyError(f"Model not found for task={normalized_task}: {model_id}")

    save_registry(registry, path=path)
    return found


def list_models(task: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    registry = load_registry(path=path)
    records = list(registry.get("models") or [])
    if task is not None:
        normalized_task = _coerce_task(task)
        records = [record for record in records if record.get("task") == normalized_task]
    return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def get_active_model(task: str, path: Path | None = None) -> dict[str, Any] | None:
    normalized_task = _coerce_task(task)
    for record in list_models(task=normalized_task, path=path):
        if record.get("is_active"):
            return record
    return None
