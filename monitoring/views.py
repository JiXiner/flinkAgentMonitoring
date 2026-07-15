from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from agent.collector import collector
from agent.remote_monitor import RemoteMonitorError, remote_monitor

from .models import AIReport, Server
from .serializers import AIReportSerializer, ServerSerializer


class ServerViewSet(viewsets.ModelViewSet):
    queryset = Server.objects.all()
    serializer_class = ServerSerializer

    def destroy(self, request, *args, **kwargs):
        if self.get_object().is_local:
            return Response({"detail": "本机节点不能删除。"}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def test_connection(self, request, pk=None):
        server = self.get_object()
        if server.is_local:
            return Response({"ok": True, "message": "本机 Agent 正常。"})
        try:
            ok = remote_monitor.test_connection(server)
            server.last_status = "online" if ok else "offline"
            server.last_error = ""
            server.save(update_fields=["last_status", "last_error", "updated_time"])
            return Response({"ok": ok, "message": "SSH 连接成功。" if ok else "SSH 未返回预期结果。"})
        except Exception as exc:
            server.last_status = "offline"
            server.last_error = str(exc)[:500]
            server.save(update_fields=["last_status", "last_error", "updated_time"])
            return Response({"ok": False, "message": "SSH 连接失败，请检查地址和凭据。"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def snapshot(self, request, pk=None):
        server = self.get_object()
        try:
            metric = collector.collect_once() if server.is_local else remote_monitor.collect(server)
            return Response(metric)
        except RemoteMonitorError:
            return Response({"detail": "远程采集失败，请先测试 SSH 连接。"}, status=status.HTTP_502_BAD_GATEWAY)


class AIReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AIReport.objects.select_related("server").all()
    serializer_class = AIReportSerializer
