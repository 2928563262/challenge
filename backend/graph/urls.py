from django.urls import path

from .views import (
    GraphEntityDetailView,
    GraphEntityPathwaysView,
    GraphEntitySearchView,
    GraphNeo4jSyncView,
    GraphRegistryActivationView,
    GraphRegistryView,
    ReviewedGraphRefreshView,
    GraphShowcaseView,
    GraphSummaryView,
)

urlpatterns = [
    path("summary/", GraphSummaryView.as_view(), name="graph-summary"),
    path("registry/", GraphRegistryView.as_view(), name="graph-registry"),
    path("registry/activate/", GraphRegistryActivationView.as_view(), name="graph-registry-activate"),
    path("neo4j/sync/", GraphNeo4jSyncView.as_view(), name="graph-neo4j-sync"),
    path("datasets/reviewed/refresh/", ReviewedGraphRefreshView.as_view(), name="reviewed-graph-refresh"),
    path("showcase/", GraphShowcaseView.as_view(), name="graph-showcase"),
    path("entities/", GraphEntitySearchView.as_view(), name="graph-entity-search"),
    path("entities/<path:entity_id>/pathways/", GraphEntityPathwaysView.as_view(), name="graph-entity-pathways"),
    path("entities/<path:entity_id>/", GraphEntityDetailView.as_view(), name="graph-entity-detail"),
]
