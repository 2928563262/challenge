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
    get_training_jobs_status,
    get_relation_status,
    predict_ner,
    predict_relation,
    run_accepted_pipeline_refresh,
    run_training_job,
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


class TrainingJobListView(APIView):
    def get(self, request):
        limit_raw = request.query_params.get("limit")
        if not limit_raw:
            limit = 20
        else:
            try:
                limit = int(limit_raw)
            except ValueError:
                return Response({"detail": "limit must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
            if limit <= 0:
                return Response({"detail": "limit must be positive."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(get_training_jobs_status(limit=limit))


class TrainingJobStartView(APIView):
    def post(self, request):
        task = str(request.data.get("task") or "").strip().lower()
        dataset_source = str(request.data.get("dataset_source") or "merged").strip().lower()
        run_name_raw = request.data.get("run_name")
        run_name = str(run_name_raw).strip() if run_name_raw is not None else None
        epochs = request.data.get("epochs", 3)
        batch_size = request.data.get("batch_size", 4)
        learning_rate_raw = request.data.get("learning_rate")
        activate = bool(request.data.get("activate", False))

        try:
            epochs = int(epochs)
            batch_size = int(batch_size)
        except (TypeError, ValueError):
            return Response(
                {"detail": "epochs and batch_size must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        learning_rate = None
        if learning_rate_raw not in ("", None):
            try:
                learning_rate = float(learning_rate_raw)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "learning_rate must be a number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            record = run_training_job(
                task=task,
                dataset_source=dataset_source,
                run_name=run_name,
                epochs=epochs,
                batch_size=batch_size,
                learning_rate=learning_rate,
                activate=activate,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "job": record,
                "jobs": get_training_jobs_status(limit=20),
            },
            status=status.HTTP_202_ACCEPTED,
        )
