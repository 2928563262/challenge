from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    GraphDataUnavailableError,
    build_graph_showcase,
    build_graph_summary,
    get_entity_detail,
    search_entities,
)


class GraphSummaryView(APIView):
    def get(self, request):
        try:
            return Response(build_graph_summary())
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class GraphShowcaseView(APIView):
    def get(self, request):
        try:
            return Response(build_graph_showcase())
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class GraphEntitySearchView(APIView):
    def get(self, request):
        keyword = (request.query_params.get("keyword") or "").strip()
        entity_type = (request.query_params.get("entity_type") or "").strip() or None
        limit = request.query_params.get("limit") or "20"
        try:
            parsed_limit = int(limit)
        except ValueError:
            return Response({"detail": "limit query parameter must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = search_entities(keyword=keyword, entity_type=entity_type, limit=parsed_limit)
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(payload)


class GraphEntityDetailView(APIView):
    def get(self, request, entity_id: str):
        relation_limit = request.query_params.get("relation_limit") or "20"
        evidence_limit = request.query_params.get("evidence_limit") or "20"
        try:
            parsed_relation_limit = int(relation_limit)
            parsed_evidence_limit = int(evidence_limit)
        except ValueError:
            return Response(
                {"detail": "relation_limit and evidence_limit must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = get_entity_detail(
                entity_id=entity_id,
                relation_limit=parsed_relation_limit,
                evidence_limit=parsed_evidence_limit,
            )
        except KeyError:
            return Response({"detail": "entity not found."}, status=status.HTTP_404_NOT_FOUND)
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(payload)
