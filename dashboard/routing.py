from django.urls import path

from .consumers import MetricsConsumer


websocket_urlpatterns = [
    path("ws/metrics/", MetricsConsumer.as_asgi()),
    path("ws/metrics/<int:server_id>/", MetricsConsumer.as_asgi()),
]
