from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend_config.settings")

import django  # noqa: E402

django.setup()

from annotation.models import AnnotationCandidate  # noqa: E402
from scripts.export_graph_csv import export_graph_records  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = DATA_DIR / "processed" / "graph-reviewed"
ALLOWED_ENTITY_TYPES = {"SYNDROME", "SYMPTOM", "FORMULA", "HERB", "THERAPY", "ADMINISTRATION"}
ALLOWED_RELATION_TYPES = {
    "SYNDROME_HAS_SYMPTOM",
    "SYNDROME_TO_FORMULA",
    "FORMULA_CONTAINS_HERB",
    "FORMULA_HAS_ADMINISTRATION",
    "SYNDROME_TO_THERAPY",
}


def determine_entry_type(entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> str:
    entity_types = {str(entity.get("type") or "") for entity in entities}
    relation_types = {str(relation.get("type") or "") for relation in relations}
    if "FORMULA_CONTAINS_HERB" in relation_types or "FORMULA_HAS_ADMINISTRATION" in relation_types:
        return "formula_entry"
    if "FORMULA" in entity_types and ("HERB" in entity_types or "ADMINISTRATION" in entity_types):
        return "formula_entry"
    if "SYNDROME" in entity_types or "SYNDROME_TO_FORMULA" in relation_types or "SYNDROME_HAS_SYMPTOM" in relation_types:
        return "syndrome_entry"
    return "reviewed_entry"


def entity_signature(entity: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(entity.get("type") or "").strip(),
        str(entity.get("text") or "").strip(),
        int(entity.get("start") or 0),
        int(entity.get("end") or 0),
    )


def normalize_entities(payload: dict[str, Any], source_text: str) -> list[dict[str, Any]]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        entity_type = str(node.get("type") or "").strip()
        text = str(node.get("text") or "").strip()
        start = node.get("start")
        end = node.get("end")
        if entity_type not in ALLOWED_ENTITY_TYPES or not text or start is None or end is None:
            continue

        start = int(start)
        end = int(end)
        if start < 0 or end > len(source_text) or start >= end:
            continue
        if source_text[start:end] != text:
            continue

        signature = (entity_type, text, start, end)
        if signature in seen:
            continue
        seen.add(signature)
        normalized.append(
            {
                "id": str(node.get("key") or f"node-{index}"),
                "type": entity_type,
                "text": text,
                "start": start,
                "end": end,
            }
        )

    normalized.sort(key=lambda item: (int(item["start"]), int(item["end"]), str(item["type"])))
    return normalized


def normalize_relations(payload: dict[str, Any], entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges = payload.get("edges")
    if not isinstance(edges, list):
        return []

    entity_id_by_signature = {entity_signature(entity): str(entity["id"]) for entity in entities}
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        relation_type = str(edge.get("label") or "").strip()
        if relation_type not in ALLOWED_RELATION_TYPES:
            continue
        head = edge.get("head")
        tail = edge.get("tail")
        if not isinstance(head, dict) or not isinstance(tail, dict):
            continue

        head_signature = (
            str(head.get("type") or "").strip(),
            str(head.get("text") or "").strip(),
            int(head.get("start") or 0),
            int(head.get("end") or 0),
        )
        tail_signature = (
            str(tail.get("type") or "").strip(),
            str(tail.get("text") or "").strip(),
            int(tail.get("start") or 0),
            int(tail.get("end") or 0),
        )
        head_id = entity_id_by_signature.get(head_signature)
        tail_id = entity_id_by_signature.get(tail_signature)
        if not head_id or not tail_id or head_id == tail_id:
            continue

        signature = (relation_type, head_id, tail_id)
        if signature in seen:
            continue
        seen.add(signature)
        normalized.append(
            {
                "type": relation_type,
                "head": head_id,
                "tail": tail_id,
            }
        )

    return normalized


def build_reviewed_records(statuses: list[str], limit: int | None = None) -> list[dict[str, Any]]:
    queryset = AnnotationCandidate.objects.filter(status__in=statuses).order_by("-updated_at", "-id")
    if limit is not None:
        queryset = queryset[:limit]

    reviewed_records: list[dict[str, Any]] = []
    for candidate in queryset:
        payload = candidate.session_payload if isinstance(candidate.session_payload, dict) else {}
        source_text = str(candidate.source_text or "")
        entities = normalize_entities(payload, source_text=source_text)
        relations = normalize_relations(payload, entities=entities)
        reviewed_records.append(
            {
                "id": candidate.record_id,
                "text": source_text,
                "entities": entities,
                "relations": relations,
                "meta": {
                    "line_number": 0,
                    "entry_type": determine_entry_type(entities, relations),
                    "source_status": candidate.status,
                    "source_page": candidate.source_page,
                    "updated_at": candidate.updated_at.isoformat(),
                },
            }
        )
    return reviewed_records


def export_reviewed_graph(
    output_dir: Path,
    *,
    statuses: list[str],
    limit: int | None = None,
    run_name: str | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    records = build_reviewed_records(statuses=statuses, limit=limit)
    summary = export_graph_records(
        records,
        output_dir,
        run_name=run_name or "graph-reviewed",
        activate=activate,
        input_path=DATA_DIR / "processed" / "annotation" / "accepted_candidates.jsonl",
        source_type="accepted_reviewed",
    )
    summary["filters"] = {"statuses": statuses, "limit": limit}
    (output_dir / "reviewed_graph_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export accepted/reviewed annotation candidates to graph CSV files.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--statuses", nargs="+", default=["accepted", "reviewed"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-name", type=str, default="graph-reviewed")
    parser.add_argument("--no-activate", action="store_true")
    args = parser.parse_args()

    summary = export_reviewed_graph(
        output_dir=args.output_dir,
        statuses=[str(status).strip() for status in args.statuses if str(status).strip()],
        limit=args.limit,
        run_name=args.run_name or None,
        activate=not args.no_activate,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
