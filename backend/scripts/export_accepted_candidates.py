from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = DATA_DIR / "processed" / "annotation"
ALLOWED_ENTITY_TYPES = {"SYNDROME", "SYMPTOM", "FORMULA", "HERB", "THERAPY", "ADMINISTRATION"}
ALLOWED_RELATION_TYPES = {
    "SYNDROME_HAS_SYMPTOM",
    "SYNDROME_TO_FORMULA",
    "FORMULA_CONTAINS_HERB",
    "FORMULA_HAS_ADMINISTRATION",
}

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend_config.settings")

import django  # noqa: E402

django.setup()

from annotation.models import AnnotationCandidate  # noqa: E402


def normalize_nodes(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str], int]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return [], Counter(), 0

    normalized: list[dict[str, Any]] = []
    counter: Counter[str] = Counter()
    skipped = 0
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            skipped += 1
            continue
        entity_type = str(node.get("type") or "").strip()
        text = str(node.get("text") or "").strip()
        start = node.get("start")
        end = node.get("end")
        if entity_type not in ALLOWED_ENTITY_TYPES or not text or start is None or end is None:
            skipped += 1
            continue
        normalized.append(
            {
                "id": str(node.get("key") or f"n-{index}"),
                "type": entity_type,
                "text": text,
                "start": int(start),
                "end": int(end),
                "match_count": int(node.get("match_count") or 0),
                "best_match": node.get("best_match") if isinstance(node.get("best_match"), dict) else None,
            }
        )
        counter[entity_type] += 1
    return normalized, counter, skipped


def normalize_relations(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str], int]:
    edges = payload.get("edges")
    if not isinstance(edges, list):
        return [], Counter(), 0

    normalized: list[dict[str, Any]] = []
    counter: Counter[str] = Counter()
    skipped = 0
    for edge in edges:
        if not isinstance(edge, dict):
            skipped += 1
            continue
        relation_type = str(edge.get("label") or "").strip()
        head = edge.get("head")
        tail = edge.get("tail")
        if relation_type not in ALLOWED_RELATION_TYPES or not isinstance(head, dict) or not isinstance(tail, dict):
            skipped += 1
            continue
        normalized.append(
            {
                "type": relation_type,
                "head": {
                    "text": str(head.get("text") or "").strip(),
                    "type": str(head.get("type") or "").strip(),
                    "start": int(head.get("start") or 0),
                    "end": int(head.get("end") or 0),
                },
                "tail": {
                    "text": str(tail.get("text") or "").strip(),
                    "type": str(tail.get("type") or "").strip(),
                    "start": int(tail.get("start") or 0),
                    "end": int(tail.get("end") or 0),
                },
                "confidence": float(edge.get("confidence") or 0.0),
                "top_predictions": edge.get("top_predictions") if isinstance(edge.get("top_predictions"), list) else [],
            }
        )
        counter[relation_type] += 1
    return normalized, counter, skipped


def export_accepted_candidates(output_dir: Path, limit: int | None = None) -> dict[str, Any]:
    queryset = AnnotationCandidate.objects.filter(status="accepted").order_by("-created_at", "-id")
    if limit is not None:
        queryset = queryset[:limit]

    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "accepted_candidates.jsonl"
    report_path = output_dir / "accepted_candidates_report.json"

    entity_counter: Counter[str] = Counter()
    relation_counter: Counter[str] = Counter()
    stats = {
        "record_count": 0,
        "node_count": 0,
        "relation_count": 0,
        "skipped_nodes": 0,
        "skipped_relations": 0,
    }

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for candidate in queryset:
            payload = candidate.session_payload if isinstance(candidate.session_payload, dict) else {}
            nodes, node_counts, skipped_nodes = normalize_nodes(payload)
            relations, relation_counts, skipped_relations = normalize_relations(payload)

            entity_counter.update(node_counts)
            relation_counter.update(relation_counts)
            stats["record_count"] += 1
            stats["node_count"] += len(nodes)
            stats["relation_count"] += len(relations)
            stats["skipped_nodes"] += skipped_nodes
            stats["skipped_relations"] += skipped_relations

            row = {
                "record_id": candidate.record_id,
                "source_text": candidate.source_text,
                "status": candidate.status,
                "source_page": candidate.source_page,
                "created_at": candidate.created_at.isoformat(),
                "updated_at": candidate.updated_at.isoformat(),
                "ner_model_dir": candidate.ner_model_dir,
                "relation_model_dir": candidate.relation_model_dir,
                "session_payload": payload,
                "entities": nodes,
                "relations": relations,
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "input": {
            "status": "accepted",
            "limit": limit,
        },
        "output": {
            "jsonl_path": str(jsonl_path),
        },
        "stats": {
            **stats,
            "entity_count_by_type": dict(sorted(entity_counter.items())),
            "relation_count_by_type": dict(sorted(relation_counter.items())),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Export accepted annotation candidates to JSONL for downstream dataset preparation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    report = export_accepted_candidates(output_dir=args.output_dir, limit=args.limit)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
