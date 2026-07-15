from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("monitoring.urls")),
    path("api/jix/", include("ai_analysis.urls")),
    path("", include("dashboard.urls")),
]
