import logging
import threading

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import close_old_connections

from agent.collector import METRICS_GROUP


logger = logging.getLogger(__name__)


class InspectionScheduler:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="jix-12h-inspection", daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.wait(settings.JIX_INSPECTION_INTERVAL):
            try:
                execute_inspection()
            except Exception:
                logger.exception("@Jix scheduled inspection failed")


def execute_inspection():
    from monitoring.models import AIReport, Server
    from .analyzer import run_inspection

    close_old_connections()
    report, _ = run_inspection()
    local_server = Server.objects.filter(is_local=True).first()
    AIReport.objects.create(
        server=local_server,
        level=report.get("level", "info"),
        problem=report.get("problem", "")[:500],
        content=report,
    )
    if report.get("needs_intervention") or report.get("code_optimizations"):
        suggestions = "；".join(report.get("suggestions", []) + report.get("code_optimizations", []))
        message = f"12小时巡检完成：{report.get('problem', '巡检完成')}。优化建议：{suggestions}"
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(METRICS_GROUP, {"type": "jix.report", "report": message})
    close_old_connections()
    return report


inspection_scheduler = InspectionScheduler()
