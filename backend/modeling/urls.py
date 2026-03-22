from django.urls import path

from .views import ModelSummaryView, NerPredictView, NerStatusView, RelationPredictView, RelationStatusView

urlpatterns = [
    path("summary/", ModelSummaryView.as_view(), name="model-summary"),
    path("ner/status/", NerStatusView.as_view(), name="ner-status"),
    path("ner/predict/", NerPredictView.as_view(), name="ner-predict"),
    path("relation/status/", RelationStatusView.as_view(), name="relation-status"),
    path("relation/predict/", RelationPredictView.as_view(), name="relation-predict"),
]
