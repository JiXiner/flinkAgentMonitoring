import logging
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import close_old_connections
from django.utils import timezone

from .remote_monitor import remote_monitor


logger = logging.getLogger(__name__)


def server_group(server_id):
    return f"server-metrics-{server_id}"


class ClusterCollectorManager:
    def __init__(self, interval=5, history_limit=120):
        self.interval = interval
        self._history = defaultdict(lambda: deque(maxlen=history_limit))
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._last_persist = {}

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="remote-cluster-collector", daemon=True)
            self._thread.start()

    def get_history(self, server_id):
        return list(self._history[int(server_id)])

    def _run(self):
        while not self._stop.is_set():
            started = time.monotonic()
            close_old_connections()
            try:
                from monitoring.models import Server

                servers = list(Server.objects.filter(enabled=True, is_local=False))
                if servers:
                    with ThreadPoolExecutor(max_workers=min(8, len(servers))) as executor:
                        futures = {executor.submit(remote_monitor.collect, server): server for server in servers}
                        for future in as_completed(futures):
                            server = futures[future]
                            try:
                                self._handle_metric(server, future.result())
                            except Exception as exc:
                                Server.objects.filter(pk=server.pk).update(last_status="offline", last_error=str(exc)[:500])
            except Exception:
                logger.exception("Remote cluster collection cycle failed")
            close_old_connections()
            self._stop.wait(max(0.1, self.interval - (time.monotonic() - started)))

    def _handle_metric(self, server, metric):
        from monitoring.models import MetricRecord, Server

        self._history[server.id].append(metric)
        Server.objects.filter(pk=server.pk).update(last_status="online", last_error="")
        now = time.monotonic()
        if now - self._last_persist.get(server.id, 0) >= 60:
            MetricRecord.objects.create(
                server=server,
                cpu=metric["cpu"], memory=metric["memory"], disk=metric["disk"],
                network_in=metric["net_in"], network_out=metric["net_out"], details=metric,
            )
            self._last_persist[server.id] = now
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(server_group(server.id), {"type": "metrics.update", "metric": metric})


cluster_collector = ClusterCollectorManager()
