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
        if not keyword:
            return Response(
                {"detail": "keyword query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(search_corpus(keyword=keyword))
