from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    path("api/v1/corpus/", include("corpus.urls")),
    path("api/v1/graph/", include("graph.urls")),
    path("api/v1/model/", include("modeling.urls")),
    path("api/v1/annotation/", include("annotation.urls")),
]
