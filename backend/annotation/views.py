from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AnnotationCandidate, STATUS_CHOICES


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
VALID_STATUSES = {item[0] for item in STATUS_CHOICES}


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
        raw_limit = request.query_params.get("limit") or str(DEFAULT_LIST_LIMIT)
        status_filter = str(request.query_params.get("status") or "").strip()
        try:
            limit = max(1, min(int(raw_limit), MAX_LIST_LIMIT))
        except ValueError:
            return Response({"detail": "limit query parameter must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = AnnotationCandidate.objects.all()
        if status_filter:
            if status_filter not in VALID_STATUSES:
                return Response(
                    {"detail": f"status must be one of: {', '.join(sorted(VALID_STATUSES))}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=status_filter)

        total = queryset.count()
        queryset = queryset[:limit]
        return Response(
            {
                "total": total,
                "limit": limit,
                "results": [serialize_candidate(item) for item in queryset],
            }
        )

    def post(self, request):
        source_text = str(request.data.get("source_text") or "").strip()
        session_payload = request.data.get("session_payload")
        source_page = str(request.data.get("source_page") or "explore").strip() or "explore"
        ner_model_dir = str(request.data.get("ner_model_dir") or "").strip()
        relation_model_dir = str(request.data.get("relation_model_dir") or "").strip()

        if not source_text:
            return Response({"detail": "source_text is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(session_payload, dict):
            return Response({"detail": "session_payload must be an object."}, status=status.HTTP_400_BAD_REQUEST)

        node_count = session_payload.get("node_count") or len(session_payload.get("nodes") or [])
        edge_count = session_payload.get("edge_count") or len(session_payload.get("edges") or [])

        candidate = AnnotationCandidate.objects.create(
            source_text=source_text,
            source_page=source_page,
            node_count=int(node_count),
            edge_count=int(edge_count),
            session_payload=session_payload,
            ner_model_dir=ner_model_dir,
            relation_model_dir=relation_model_dir,
        )
        return Response(serialize_candidate(candidate, include_payload=True), status=status.HTTP_201_CREATED)


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
        return Response(serialize_candidate(candidate, include_payload=True))
