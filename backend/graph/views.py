from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    add_manual_relation_suppress,
    add_manual_relation_upsert,
    activate_graph_version,
    delete_manual_relation,
    GraphDataUnavailableError,
    GraphSyncError,
    build_entity_pathways,
    build_graph_showcase,
    build_graph_summary,
    get_graph_registry_status,
    get_graph_sync_status,
    get_entity_detail,
    get_clause_detail,
    list_manual_relations,
    run_neo4j_sync,
    run_reviewed_graph_refresh,
    search_clauses,
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
        sync_neo4j = bool(request.data.get("sync_neo4j", False))

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

        try:
            return Response(run_reviewed_graph_refresh(statuses=normalized_statuses, limit=parsed_limit, sync_neo4j=sync_neo4j))
        except GraphSyncError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class GraphNeo4jSyncView(APIView):
    def get(self, request):
        return Response(get_graph_sync_status())

    def post(self, request):
        try:
            return Response({"sync": run_neo4j_sync(), "status": get_graph_sync_status()})
        except GraphSyncError as exc:
            return Response({"detail": str(exc), "status": get_graph_sync_status()}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class GraphManualRelationListCreateView(APIView):
    def get(self, request):
        graph_id = str(request.query_params.get("graph_id") or "").strip() or None
        return Response(list_manual_relations(graph_id=graph_id))

    def post(self, request):
        action = str(request.data.get("action") or "upsert").strip().lower()
        start_id = str(request.data.get("start_id") or "").strip()
        end_id = str(request.data.get("end_id") or "").strip()
        relation_type = str(request.data.get("relation_type") or "").strip().upper()
        example_text = str(request.data.get("example_text") or "").strip()
        evidence_count = request.data.get("evidence_count", 1)
        record_ids = request.data.get("record_ids")

        if not start_id or not end_id or not relation_type:
            return Response(
                {"detail": "start_id, end_id and relation_type are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if record_ids is not None and not isinstance(record_ids, list):
            return Response({"detail": "record_ids must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            evidence_count = int(evidence_count)
        except (TypeError, ValueError):
            return Response({"detail": "evidence_count must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if action == "suppress":
                record = add_manual_relation_suppress(
                    start_id=start_id,
                    end_id=end_id,
                    relation_type=relation_type,
                    example_text=example_text,
                )
            elif action == "upsert":
                record = add_manual_relation_upsert(
                    start_id=start_id,
                    end_id=end_id,
                    relation_type=relation_type,
                    example_text=example_text,
                    evidence_count=evidence_count,
                    record_ids=[str(item) for item in (record_ids or [])],
                )
            else:
                return Response({"detail": "action must be upsert or suppress."}, status=status.HTTP_400_BAD_REQUEST)
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"record": record, "manual_relations": list_manual_relations()}, status=status.HTTP_201_CREATED)


class GraphManualRelationDeleteView(APIView):
    def delete(self, request, override_id: str):
        try:
            record = delete_manual_relation(override_id)
        except KeyError:
            return Response({"detail": "manual relation override not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"record": record, "manual_relations": list_manual_relations()})


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


class GraphClauseSearchView(APIView):
    def get(self, request):
        keyword = (request.query_params.get("keyword") or "").strip()
        entry_type = (request.query_params.get("entry_type") or "").strip() or None
        page = request.query_params.get("page") or "1"
        page_size = request.query_params.get("page_size") or "20"
        try:
            parsed_page = int(page)
            parsed_page_size = int(page_size)
        except ValueError:
            return Response({"detail": "page and page_size query parameters must be integers."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = search_clauses(keyword=keyword, entry_type=entry_type, page=parsed_page, page_size=parsed_page_size)
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(payload)


class GraphClauseDetailView(APIView):
    def get(self, request, clause_id: str):
        try:
            payload = get_clause_detail(clause_id=clause_id)
        except KeyError:
            return Response({"detail": "clause not found."}, status=status.HTTP_404_NOT_FOUND)
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


class GraphEntityPathwaysView(APIView):
    def get(self, request, entity_id: str):
        limit = request.query_params.get("limit") or "20"
        try:
            parsed_limit = int(limit)
        except ValueError:
            return Response({"detail": "limit query parameter must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = build_entity_pathways(entity_id=entity_id, limit=parsed_limit)
        except KeyError:
            return Response({"detail": "entity not found."}, status=status.HTTP_404_NOT_FOUND)
        except GraphDataUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(payload)
