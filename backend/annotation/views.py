from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AnnotationCandidate, STATUS_ACCEPTED, STATUS_CHOICES, STATUS_PENDING, STATUS_REVIEWED


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
VALID_STATUSES = {item[0] for item in STATUS_CHOICES}


def _run_accepted_pipeline_refresh_safe() -> dict[str, object]:
    try:
        from modeling.services import run_accepted_pipeline_refresh

        report = run_accepted_pipeline_refresh(limit=None)
    except Exception as exc:  # pragma: no cover
        return {
            "triggered": True,
            "ok": False,
            "detail": str(exc),
        }

    export_stats = ((report.get("export_report") or {}).get("stats") or {}) if isinstance(report, dict) else {}
    merge_stats = (report.get("merge_report") or {}).get("stats") if isinstance(report, dict) else {}
    merge_ner = ((merge_stats or {}).get("ner") or {}) if isinstance(merge_stats, dict) else {}
    merge_relation = ((merge_stats or {}).get("relation") or {}) if isinstance(merge_stats, dict) else {}

    return {
        "triggered": True,
        "ok": True,
        "detail": "accepted pipeline refreshed.",
        "export_record_count": int(export_stats.get("record_count") or 0),
        "merge_ner_added_count": int(merge_ner.get("added_count") or 0),
        "merge_relation_added_count": int(merge_relation.get("added_count") or 0),
    }


def _run_reviewed_graph_refresh_safe() -> dict[str, object]:
    try:
        from graph.services import run_reviewed_graph_refresh

        report = run_reviewed_graph_refresh(statuses=[STATUS_ACCEPTED, STATUS_REVIEWED], limit=None)
    except Exception as exc:  # pragma: no cover
        return {
            "triggered": True,
            "ok": False,
            "detail": str(exc),
        }

    graph_summary = report.get("graph_summary") if isinstance(report, dict) else None
    graph_version = (graph_summary or {}).get("graph_version") if isinstance(graph_summary, dict) else None
    return {
        "triggered": True,
        "ok": True,
        "detail": "reviewed graph refreshed.",
        "run_name": str((graph_version or {}).get("run_name") or ""),
        "entity_node_count": int((graph_summary or {}).get("entity_node_count") or 0),
        "entity_relation_count": int((graph_summary or {}).get("entity_relation_count") or 0),
    }


def serialize_candidate(candidate: AnnotationCandidate, include_payload: bool = False) -> dict[str, object]:
    payload = {
        "record_id": candidate.record_id,
        "status": candidate.status,
        "source_page": candidate.source_page,
        "source_text": candidate.source_text,
        "text_preview": candidate.source_text[:80],
        "node_count": candidate.node_count,
        "edge_count": candidate.edge_count,
        "ner_model_dir": candidate.ner_model_dir,
        "relation_model_dir": candidate.relation_model_dir,
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }
    if include_payload:
        payload["session_payload"] = candidate.session_payload
    return payload


class AnnotationCandidateListCreateView(APIView):
    def get(self, request):
        raw_limit = request.query_params.get("limit")
        raw_page = request.query_params.get("page") or "1"
        raw_page_size = request.query_params.get("page_size") or raw_limit or str(DEFAULT_LIST_LIMIT)
        status_filter = str(request.query_params.get("status") or "").strip()
        keyword = str(request.query_params.get("q") or "").strip()
        source_page_filter = str(request.query_params.get("source_page") or "").strip()
        try:
            page = max(1, int(raw_page))
        except ValueError:
            return Response({"detail": "page query parameter must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            page_size = max(1, min(int(raw_page_size), MAX_LIST_LIMIT))
        except ValueError:
            return Response({"detail": "page_size query parameter must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = AnnotationCandidate.objects.all()
        if status_filter:
            if status_filter not in VALID_STATUSES:
                return Response(
                    {"detail": f"status must be one of: {', '.join(sorted(VALID_STATUSES))}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=status_filter)
        if keyword:
            queryset = queryset.filter(
                Q(record_id__icontains=keyword) | Q(source_text__icontains=keyword) | Q(source_page__icontains=keyword)
            )
        if source_page_filter:
            queryset = queryset.filter(source_page=source_page_filter)

        total = queryset.count()
        total_pages = (total + page_size - 1) // page_size if total else 0
        if total_pages and page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size
        queryset = queryset[offset : offset + page_size]
        return Response(
            {
                "total": total,
                "limit": page_size,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1 and total_pages > 0,
                "q": keyword,
                "results": [serialize_candidate(item) for item in queryset],
            }
        )

    def post(self, request):
        source_text = str(request.data.get("source_text") or "").strip()
        session_payload = request.data.get("session_payload")
        source_page = str(request.data.get("source_page") or "explore").strip() or "explore"
        ner_model_dir = str(request.data.get("ner_model_dir") or "").strip()
        relation_model_dir = str(request.data.get("relation_model_dir") or "").strip()
        status_value = str(request.data.get("status") or "").strip()

        if not source_text:
            return Response({"detail": "source_text is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(session_payload, dict):
            return Response({"detail": "session_payload must be an object."}, status=status.HTTP_400_BAD_REQUEST)
        if status_value and status_value not in VALID_STATUSES:
            return Response(
                {"detail": f"status must be one of: {', '.join(sorted(VALID_STATUSES))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        node_count = session_payload.get("node_count") or len(session_payload.get("nodes") or [])
        edge_count = session_payload.get("edge_count") or len(session_payload.get("edges") or [])

        candidate = AnnotationCandidate.objects.create(
            source_text=source_text,
            source_page=source_page,
            status=status_value or STATUS_PENDING,
            node_count=int(node_count),
            edge_count=int(edge_count),
            session_payload=session_payload,
            ner_model_dir=ner_model_dir,
            relation_model_dir=relation_model_dir,
        )
        payload = serialize_candidate(candidate, include_payload=True)
        if candidate.status == STATUS_ACCEPTED:
            payload["auto_pipeline_refresh"] = _run_accepted_pipeline_refresh_safe()
        if candidate.status in {STATUS_ACCEPTED, STATUS_REVIEWED}:
            payload["auto_graph_refresh"] = _run_reviewed_graph_refresh_safe()
        return Response(payload, status=status.HTTP_201_CREATED)


class AnnotationCandidateBatchStatusView(APIView):
    def post(self, request):
        record_ids = request.data.get("record_ids")
        status_value = str(request.data.get("status") or "").strip()
        if not isinstance(record_ids, list) or not record_ids:
            return Response({"detail": "record_ids must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)
        if status_value not in VALID_STATUSES:
            return Response(
                {"detail": f"status must be one of: {', '.join(sorted(VALID_STATUSES))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_record_ids = [str(item).strip() for item in record_ids if str(item).strip()]
        if not normalized_record_ids:
            return Response({"detail": "record_ids must contain at least one valid id."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = AnnotationCandidate.objects.filter(record_id__in=normalized_record_ids)
        existing_ids = {item.record_id for item in queryset.only("record_id")}
        missing_ids = [item for item in normalized_record_ids if item not in existing_ids]
        if not existing_ids:
            return Response({"detail": "no candidates found for given record_ids."}, status=status.HTTP_404_NOT_FOUND)

        updated_count = queryset.update(status=status_value, updated_at=timezone.now())
        payload: dict[str, object] = {
            "updated_count": int(updated_count),
            "requested_count": len(normalized_record_ids),
            "status": status_value,
            "missing_ids": missing_ids,
        }
        if status_value == STATUS_ACCEPTED:
            payload["auto_pipeline_refresh"] = _run_accepted_pipeline_refresh_safe()
        if status_value in {STATUS_ACCEPTED, STATUS_REVIEWED}:
            payload["auto_graph_refresh"] = _run_reviewed_graph_refresh_safe()
        return Response(payload, status=status.HTTP_200_OK)


class AnnotationCandidateDetailView(APIView):
    def get_candidate(self, record_id: str) -> AnnotationCandidate | None:
        try:
            return AnnotationCandidate.objects.get(record_id=record_id)
        except AnnotationCandidate.DoesNotExist:
            return None

    def get(self, request, record_id: str):
        candidate = self.get_candidate(record_id)
        if candidate is None:
            return Response({"detail": "candidate not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serialize_candidate(candidate, include_payload=True))

    def patch(self, request, record_id: str):
        candidate = self.get_candidate(record_id)
        if candidate is None:
            return Response({"detail": "candidate not found."}, status=status.HTTP_404_NOT_FOUND)

        previous_status = candidate.status
        status_value = request.data.get("status")
        source_text = request.data.get("source_text")
        session_payload = request.data.get("session_payload")

        update_fields = {"updated_at"}
        if status_value is None and source_text is None and session_payload is None:
            return Response(
                {"detail": "at least one of status, source_text or session_payload is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if status_value is not None:
            normalized_status = str(status_value).strip()
            if normalized_status not in VALID_STATUSES:
                return Response(
                    {"detail": f"status must be one of: {', '.join(sorted(VALID_STATUSES))}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            candidate.status = normalized_status
            update_fields.add("status")

        if source_text is not None:
            normalized_source_text = str(source_text).strip()
            if not normalized_source_text:
                return Response({"detail": "source_text cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
            candidate.source_text = normalized_source_text
            update_fields.add("source_text")

        if session_payload is not None:
            if not isinstance(session_payload, dict):
                return Response({"detail": "session_payload must be an object."}, status=status.HTTP_400_BAD_REQUEST)
            candidate.session_payload = session_payload
            candidate.node_count = int(session_payload.get("node_count") or len(session_payload.get("nodes") or []))
            candidate.edge_count = int(session_payload.get("edge_count") or len(session_payload.get("edges") or []))
            update_fields.update({"session_payload", "node_count", "edge_count"})

        candidate.save(update_fields=list(update_fields))
        payload = serialize_candidate(candidate, include_payload=True)

        should_refresh_accepted_pipeline = False
        should_refresh_graph = False
        if previous_status != candidate.status and (previous_status == STATUS_ACCEPTED or candidate.status == STATUS_ACCEPTED):
            should_refresh_accepted_pipeline = True
        if previous_status != candidate.status and (previous_status in {STATUS_ACCEPTED, STATUS_REVIEWED} or candidate.status in {STATUS_ACCEPTED, STATUS_REVIEWED}):
            should_refresh_graph = True
        if (source_text is not None or session_payload is not None) and candidate.status == STATUS_ACCEPTED:
            should_refresh_accepted_pipeline = True
        if (source_text is not None or session_payload is not None) and candidate.status in {STATUS_ACCEPTED, STATUS_REVIEWED}:
            should_refresh_graph = True

        if should_refresh_accepted_pipeline:
            payload["auto_pipeline_refresh"] = _run_accepted_pipeline_refresh_safe()
        if should_refresh_graph:
            payload["auto_graph_refresh"] = _run_reviewed_graph_refresh_safe()

        return Response(payload)

    def delete(self, request, record_id: str):
        candidate = self.get_candidate(record_id)
        if candidate is None:
            return Response({"detail": "candidate not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = {
            "record_id": candidate.record_id,
            "status": candidate.status,
        }
        candidate.delete()
        return Response({"deleted": True, "record": payload}, status=status.HTTP_200_OK)
