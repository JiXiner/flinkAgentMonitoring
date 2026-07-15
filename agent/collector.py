import logging
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import psutil
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.utils import timezone

from .cluster_simulator import cluster_simulator


logger = logging.getLogger(__name__)
METRICS_GROUP = "local-server-metrics"


class LocalMetricCollector:
    """以独立守护线程采集指标，不占用 Django 请求线程。"""

    def __init__(self, interval=None, history_limit=None):
        self.interval = interval or getattr(settings, "AGENT_COLLECT_INTERVAL", 1.0)
        limit = history_limit or getattr(settings, "AGENT_HISTORY_LIMIT", 120)
        self._history = deque(maxlen=limit)
        self._history_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._start_lock = threading.Lock()
        self._last_net_io = None
        self._last_disk_io = None
        self._last_counter_time = None
        self._process_cache = {"cpu": [], "memory": []}
        self._last_process_scan = 0.0

    def start(self):
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            psutil.cpu_percent(interval=None)
            self._thread = threading.Thread(
                target=self._run,
                name="local-metric-collector",
                daemon=True,
            )
            self._thread.start()
            logger.info("Local metric collector started")

    def stop(self, timeout=2.0):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def collect_once(self):
        memory = psutil.virtual_memory()
        frequency = psutil.cpu_freq()
        disk = psutil.disk_usage(Path.home().anchor or "/")
        net_io = psutil.net_io_counters()
        disk_io = psutil.disk_io_counters()
        counter_time = time.monotonic()
        elapsed = (
            counter_time - self._last_counter_time
            if self._last_counter_time is not None
            else None
        )
        net_in, net_out = self._counter_rates(
            net_io,
            self._last_net_io,
            elapsed,
            "bytes_recv",
            "bytes_sent",
        )
        disk_read, disk_write = self._counter_rates(
            disk_io,
            self._last_disk_io,
            elapsed,
            "read_bytes",
            "write_bytes",
        )
        self._last_net_io = net_io
        self._last_disk_io = disk_io
        self._last_counter_time = counter_time

        if counter_time - self._last_process_scan >= 5:
            self._process_cache = self._collect_top_processes()
            self._last_process_scan = counter_time
        now = timezone.localtime()
        metric = {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": now.isoformat(),
            "cpu": round(psutil.cpu_percent(interval=None), 1),
            "cpu_cores": psutil.cpu_count(logical=True) or 0,
            "cpu_frequency_mhz": round(frequency.current, 1) if frequency else None,
            "memory": round(memory.percent, 1),
            "memory_total": int(memory.total),
            "memory_used": int(memory.used),
            "disk": round(disk.percent, 1),
            "disk_total": int(disk.total),
            "disk_used": int(disk.used),
            "disk_read": disk_read,
            "disk_write": disk_write,
            "net_in": net_in,
            "net_out": net_out,
            "top_processes": self._process_cache,
        }
        metric["service_clusters"] = cluster_simulator.snapshot(metric)
        return metric

    @staticmethod
    def _counter_rates(current, previous, elapsed, first_field, second_field):
        if current is None or previous is None or not elapsed or elapsed <= 0:
            return 0, 0
        first = max(0, getattr(current, first_field) - getattr(previous, first_field))
        second = max(0, getattr(current, second_field) - getattr(previous, second_field))
        return round(first / elapsed, 1), round(second / elapsed, 1)

    @staticmethod
    def _collect_top_processes():
        processes = []
        for process in psutil.process_iter(
            ["pid", "name", "username", "cpu_percent", "memory_percent"]
        ):
            try:
                info = process.info
                processes.append(
                    {
                        "pid": info["pid"],
                        "name": info.get("name") or "unknown",
                        "username": info.get("username") or "-",
                        "cpu": round(info.get("cpu_percent") or 0, 1),
                        "memory": round(info.get("memory_percent") or 0, 1),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return {
            "cpu": sorted(processes, key=lambda item: item["cpu"], reverse=True)[:10],
            "memory": sorted(
                processes, key=lambda item: item["memory"], reverse=True
            )[:10],
        }

    def get_history(self):
        with self._history_lock:
            return list(self._history)

    def _run(self):
        while not self._stop_event.is_set():
            started_at = datetime.now().timestamp()
            try:
                metric = self.collect_once()
                with self._history_lock:
                    self._history.append(metric)
                self._publish(metric)
            except Exception:
                logger.exception("Metric collection failed")

            elapsed = datetime.now().timestamp() - started_at
            self._stop_event.wait(max(0.05, self.interval - elapsed))

    @staticmethod
    def _publish(metric):
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            METRICS_GROUP,
            {"type": "metrics.update", "metric": metric},
        )


collector = LocalMetricCollector()
