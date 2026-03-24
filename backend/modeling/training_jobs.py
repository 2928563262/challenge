from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings

JOBS_DIR = settings.DATA_DIR / "processed" / "training_jobs"
JOBS_STATE_PATH = JOBS_DIR / "jobs.json"
_PROCESS_HANDLES: dict[str, subprocess.Popen[Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_jobs_dir() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _load_jobs() -> list[dict[str, Any]]:
    _ensure_jobs_dir()
    if not JOBS_STATE_PATH.exists():
        return []
    payload = json.loads(JOBS_STATE_PATH.read_text(encoding="utf-8"))
    jobs = payload.get("jobs")
    if isinstance(jobs, list):
        return jobs
    return []


def _save_jobs(jobs: list[dict[str, Any]]) -> None:
    _ensure_jobs_dir()
    JOBS_STATE_PATH.write_text(
        json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _task_to_script_name(task: str) -> str:
    if task == "ner":
        return "train_ner_baseline.py"
    return "train_relation_baseline.py"


def _task_to_dataset_leaf(task: str) -> str:
    return "ner" if task == "ner" else "relation"


def _task_to_output_root(task: str) -> Path:
    return settings.PROJECT_ROOT / "models" / "baseline" / _task_to_dataset_leaf(task)


def _task_to_dataset_dir(task: str, dataset_source: str) -> Path:
    leaf = _task_to_dataset_leaf(task)
    if dataset_source == "merged":
        return settings.DATA_DIR / "processed" / "merged" / leaf
    return settings.DATA_DIR / "processed" / leaf


def _default_run_name(task: str, dataset_source: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"guwenbert-{_task_to_dataset_leaf(task)}-{dataset_source}-{stamp}"


def _finalize_job(job: dict[str, Any], return_code: int | None) -> None:
    expected_summary_path = Path(str(job.get("expected_summary_path") or ""))
    summary_payload: dict[str, Any] | None = None
    if expected_summary_path.exists():
        try:
            summary_payload = json.loads(expected_summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary_payload = None

    status = "succeeded" if (return_code == 0 and summary_payload is not None) else "failed"
    if return_code is None and summary_payload is not None:
        status = "succeeded"

    job["status"] = status
    job["return_code"] = return_code
    job["summary"] = summary_payload
    job["finished_at"] = _utc_now_iso()
    job["updated_at"] = job["finished_at"]
    if status == "failed" and summary_payload is None and not job.get("error_message"):
        job["error_message"] = "Training process finished without a run_summary.json artifact."


def _refresh_jobs_in_place(jobs: list[dict[str, Any]]) -> None:
    changed = False
    for job in jobs:
        if job.get("status") != "running":
            continue

        job_id = str(job.get("id") or "")
        process = _PROCESS_HANDLES.get(job_id)
        if process is not None:
            return_code = process.poll()
            if return_code is None:
                continue
            _finalize_job(job, return_code)
            _PROCESS_HANDLES.pop(job_id, None)
            changed = True
            continue

        pid = int(job.get("pid") or 0)
        if pid and _pid_exists(pid):
            continue

        _finalize_job(job, None)
        changed = True

    if changed:
        _save_jobs(jobs)


def list_training_jobs(limit: int = 20) -> dict[str, Any]:
    jobs = _load_jobs()
    _refresh_jobs_in_place(jobs)
    ordered = sorted(jobs, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {
        "path": str(JOBS_STATE_PATH),
        "running_count": sum(1 for item in jobs if item.get("status") == "running"),
        "jobs": ordered[:limit],
    }


def _validate_running_guard(jobs: list[dict[str, Any]], task: str) -> None:
    for job in jobs:
        if job.get("task") == task and job.get("status") == "running":
            raise ValueError(f"A {task.upper()} training job is already running.")


def start_training_job(
    *,
    task: str,
    dataset_source: str,
    run_name: str | None,
    epochs: int,
    batch_size: int,
    learning_rate: float | None,
    activate: bool,
) -> dict[str, Any]:
    if task not in {"ner", "relation"}:
        raise ValueError("task must be ner or relation.")
    if dataset_source not in {"baseline", "merged"}:
        raise ValueError("dataset_source must be baseline or merged.")
    if epochs <= 0:
        raise ValueError("epochs must be a positive integer.")
    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer.")
    if learning_rate is not None and learning_rate <= 0:
        raise ValueError("learning_rate must be positive.")

    jobs = _load_jobs()
    _refresh_jobs_in_place(jobs)
    _validate_running_guard(jobs, task)

    resolved_run_name = (run_name or "").strip() or _default_run_name(task, dataset_source)
    dataset_dir = _task_to_dataset_dir(task, dataset_source)
    output_root = _task_to_output_root(task)
    expected_summary_path = output_root / resolved_run_name / "best" / "run_summary.json"

    script_path = settings.BASE_DIR / "scripts" / _task_to_script_name(task)
    command = [
        sys.executable,
        str(script_path),
        "--dataset-dir",
        str(dataset_dir),
        "--output-root",
        str(output_root),
        "--epochs",
        str(epochs),
        "--batch-size",
        str(batch_size),
        "--run-name",
        resolved_run_name,
    ]
    if learning_rate is not None:
        command.extend(["--learning-rate", str(learning_rate)])
    if activate:
        command.append("--activate")

    job_id = f"{task}-{uuid.uuid4().hex[:10]}"
    log_path = JOBS_DIR / f"{job_id}.log"
    _ensure_jobs_dir()
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(settings.PROJECT_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    created_at = _utc_now_iso()
    record = {
        "id": job_id,
        "task": task,
        "status": "running",
        "dataset_source": dataset_source,
        "dataset_dir": str(dataset_dir),
        "run_name": resolved_run_name,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "activate": activate,
        "command": command,
        "pid": process.pid,
        "log_path": str(log_path),
        "expected_summary_path": str(expected_summary_path),
        "summary": None,
        "return_code": None,
        "error_message": None,
        "created_at": created_at,
        "started_at": created_at,
        "finished_at": None,
        "updated_at": created_at,
    }
    jobs.append(record)
    _save_jobs(jobs)
    _PROCESS_HANDLES[job_id] = process
    return record
