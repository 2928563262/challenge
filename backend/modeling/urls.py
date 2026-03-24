from django.urls import path

from .views import (
    AcceptedPipelineRefreshView,
    ModelRegistryActivationView,
    ModelRegistryView,
    ModelSummaryView,
    NerPredictView,
    NerStatusView,
    RelationPredictView,
    RelationStatusView,
    TrainingJobListView,
    TrainingJobStartView,
)

urlpatterns = [
    path("summary/", ModelSummaryView.as_view(), name="model-summary"),
    path("registry/", ModelRegistryView.as_view(), name="model-registry"),
    path("registry/activate/", ModelRegistryActivationView.as_view(), name="model-registry-activate"),
    path("jobs/", TrainingJobListView.as_view(), name="training-job-list"),
    path("jobs/start/", TrainingJobStartView.as_view(), name="training-job-start"),
    path("datasets/accepted/refresh/", AcceptedPipelineRefreshView.as_view(), name="accepted-pipeline-refresh"),
    path("ner/status/", NerStatusView.as_view(), name="ner-status"),
    path("ner/predict/", NerPredictView.as_view(), name="ner-predict"),
    path("relation/status/", RelationStatusView.as_view(), name="relation-status"),
    path("relation/predict/", RelationPredictView.as_view(), name="relation-predict"),
]
