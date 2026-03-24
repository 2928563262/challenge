from django.urls import path
from .views import (
    OverviewStatsView,
    HerbAnalysisView,
    FormulaAnalysisView,
    ClinicalPathView,
    TextAnalysisView,
)

urlpatterns = [
    path("overview/", OverviewStatsView.as_view(), name="stats-overview"),
    path("herbs/", HerbAnalysisView.as_view(), name="stats-herbs"),
    path("formulas/", FormulaAnalysisView.as_view(), name="stats-formulas"),
    path("clinical-path/", ClinicalPathView.as_view(), name="stats-clinical-path"),
    path("text/", TextAnalysisView.as_view(), name="stats-text"),
]
