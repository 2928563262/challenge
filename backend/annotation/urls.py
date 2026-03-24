from django.urls import path

from .views import AnnotationCandidateBatchStatusView, AnnotationCandidateDetailView, AnnotationCandidateListCreateView

urlpatterns = [
    path("candidates/", AnnotationCandidateListCreateView.as_view(), name="annotation-candidates"),
    path("candidates/batch-status/", AnnotationCandidateBatchStatusView.as_view(), name="annotation-candidates-batch-status"),
    path("candidates/<str:record_id>/", AnnotationCandidateDetailView.as_view(), name="annotation-candidate-detail"),
]
