from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import build_overview_payload, search_corpus


class CorpusOverviewView(APIView):
    def get(self, request):
        return Response(build_overview_payload())


class CorpusSearchView(APIView):
    def get(self, request):
        keyword = (request.query_params.get("keyword") or "").strip()
        limit = request.query_params.get("limit") or "20"
        page = request.query_params.get("page") or "1"
        page_size = request.query_params.get("page_size")
        formula_related_raw = (request.query_params.get("formula_related") or "").strip().lower()
        sort_by = (request.query_params.get("sort_by") or "id").strip().lower()
        sort_order = (request.query_params.get("sort_order") or "asc").strip().lower()

        try:
            parsed_limit = int(limit)
            parsed_page = int(page)
            parsed_page_size = int(page_size) if page_size not in (None, "") else None
        except ValueError:
            return Response({"detail": "limit, page and page_size must be integers."}, status=status.HTTP_400_BAD_REQUEST)

        if parsed_limit <= 0 or parsed_page <= 0 or (parsed_page_size is not None and parsed_page_size <= 0):
            return Response({"detail": "limit, page and page_size must be positive integers."}, status=status.HTTP_400_BAD_REQUEST)

        if formula_related_raw in {"", "all"}:
            formula_related = None
        elif formula_related_raw in {"true", "1", "yes"}:
            formula_related = True
        elif formula_related_raw in {"false", "0", "no"}:
            formula_related = False
        else:
            return Response({"detail": "formula_related must be all/true/false."}, status=status.HTTP_400_BAD_REQUEST)

        if sort_by not in {"id", "text_length", "formula_name"}:
            return Response({"detail": "sort_by must be one of id/text_length/formula_name."}, status=status.HTTP_400_BAD_REQUEST)
        if sort_order not in {"asc", "desc"}:
            return Response({"detail": "sort_order must be asc or desc."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            search_corpus(
                keyword=keyword,
                limit=parsed_limit,
                page=parsed_page,
                page_size=parsed_page_size,
                formula_related=formula_related,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        )
