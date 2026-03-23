from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    activate_registered_model,
    InvalidModelInputError,
    ModelUnavailableError,
    get_model_summary,
    get_model_registry_status,
    get_ner_status,
    get_relation_status,
    predict_ner,
    predict_relation,
    run_accepted_pipeline_refresh,
)


class ModelSummaryView(APIView):
    def get(self, request):
        return Response(get_model_summary())


class ModelRegistryView(APIView):
    def get(self, request):
        return Response(get_model_registry_status())


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


class AcceptedPipelineRefreshView(APIView):
    def post(self, request):
        limit = request.data.get("limit")
        if limit in ("", None):
            limit = None
        elif not isinstance(limit, int) or limit <= 0:
            return Response({"detail": "limit must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(run_accepted_pipeline_refresh(limit=limit))


class ModelRegistryActivationView(APIView):
    def post(self, request):
        task = str(request.data.get("task") or "").strip().lower()
        model_id = str(request.data.get("model_id") or "").strip()
        if task not in {"ner", "relation"}:
            return Response({"detail": "task must be ner or relation."}, status=status.HTTP_400_BAD_REQUEST)
        if not model_id:
            return Response({"detail": "model_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            record = activate_registered_model(task=task, model_id=model_id)
        except KeyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "task": task,
                "record": record,
                "registry": get_model_registry_status(),
            }
        )
