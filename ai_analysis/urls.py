from django.urls import path

from .views import JixChatView, JixInspectionView


urlpatterns = [
    path("chat/", JixChatView.as_view(), name="jix-chat"),
    path("inspect/", JixInspectionView.as_view(), name="jix-inspect"),
]
