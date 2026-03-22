from django.urls import path

from .views import AnnotationCandidateDetailView, AnnotationCandidateListCreateView

urlpatterns = [
    path("candidates/", AnnotationCandidateListCreateView.as_view(), name="annotation-candidates"),
    path("candidates/<str:record_id>/", AnnotationCandidateDetailView.as_view(), name="annotation-candidate-detail"),
]
