from django.urls import path

from .views import CorpusOverviewView, CorpusSearchView

urlpatterns = [
    path("overview/", CorpusOverviewView.as_view(), name="corpus-overview"),
    path("search/", CorpusSearchView.as_view(), name="corpus-search"),
]
