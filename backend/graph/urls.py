from django.urls import path

from .views import GraphEntityDetailView, GraphEntitySearchView, GraphShowcaseView, GraphSummaryView

urlpatterns = [
    path("summary/", GraphSummaryView.as_view(), name="graph-summary"),
    path("showcase/", GraphShowcaseView.as_view(), name="graph-showcase"),
    path("entities/", GraphEntitySearchView.as_view(), name="graph-entity-search"),
    path("entities/<path:entity_id>/", GraphEntityDetailView.as_view(), name="graph-entity-detail"),
]
