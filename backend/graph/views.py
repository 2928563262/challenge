from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    activate_graph_version,
    GraphDataUnavailableError,
    build_graph_showcase,
    build_graph_summary,
    get_graph_registry_status,
    get_entity_detail,
    run_reviewed_graph_refresh,
    search_entities,
)


class GraphSummaryView(APIView):
    def get(self, request):
        try:
            return Response(build_graph_summary())
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class GraphRegistryView(APIView):
    def get(self, request):
        return Response(get_graph_registry_status())


class GraphRegistryActivationView(APIView):
    def post(self, request):
        graph_id = str(request.data.get("graph_id") or "").strip()
        if not graph_id:
            return Response({"detail": "graph_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            record = activate_graph_version(graph_id)
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response({"record": record, "registry": get_graph_registry_status()})


class ReviewedGraphRefreshView(APIView):
    def post(self, request):
        statuses = request.data.get("statuses")
        limit = request.data.get("limit")

        if statuses in (None, ""):
            normalized_statuses = ["accepted", "reviewed"]
        elif not isinstance(statuses, list):
            return Response({"detail": "statuses must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            normalized_statuses = [str(item).strip() for item in statuses if str(item).strip()]
            if not normalized_statuses:
                return Response({"detail": "statuses must not be empty."}, status=status.HTTP_400_BAD_REQUEST)

        if limit in ("", None):
            parsed_limit = None
        elif not isinstance(limit, int) or limit <= 0:
            return Response({"detail": "limit must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            parsed_limit = limit

        return Response(run_reviewed_graph_refresh(statuses=normalized_statuses, limit=parsed_limit))


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
