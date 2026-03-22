from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    InvalidModelInputError,
    ModelUnavailableError,
    get_model_summary,
    get_ner_status,
    get_relation_status,
    predict_ner,
    predict_relation,
)


class ModelSummaryView(APIView):
    def get(self, request):
        return Response(get_model_summary())


class NerStatusView(APIView):
    def get(self, request):
        return Response(get_ner_status())


class RelationStatusView(APIView):
    def get(self, request):
        return Response(get_relation_status())


class NerPredictView(APIView):
    def post(self, request):
        text = str(request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "text is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            return Response(predict_ner(text))
        except ModelUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class RelationPredictView(APIView):
    def post(self, request):
        text = str(request.data.get("text") or "").strip()
        head = request.data.get("head") or {}
        tail = request.data.get("tail") or {}
        if not text:
            return Response({"detail": "text is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(head, dict) or not isinstance(tail, dict):
            return Response({"detail": "head and tail must be objects."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            return Response(predict_relation(text, head=head, tail=tail))
        except InvalidModelInputError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ModelUnavailableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
