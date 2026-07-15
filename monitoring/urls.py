from rest_framework.routers import DefaultRouter

from .views import AIReportViewSet, ServerViewSet


router = DefaultRouter()
router.register("servers", ServerViewSet)
router.register("reports", AIReportViewSet)
urlpatterns = router.urls
