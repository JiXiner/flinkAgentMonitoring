import re
import time
from datetime import datetime

import paramiko
from django.utils import timezone


class RemoteMonitorError(RuntimeError):
    pass


class RemoteServerMonitor:
    def __init__(self, timeout=8):
        self.timeout = timeout
        self._network_counters = {}

    def _connect(self, server):
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=server.ip,
            port=server.port,
            username=server.username,
            password=server.password or None,
            timeout=self.timeout,
            auth_timeout=self.timeout,
            banner_timeout=self.timeout,
        )
        return client

    def test_connection(self, server):
        client = self._connect(server)
        try:
            return self._run(client, "printf FLINK_AGENT_OK") == "FLINK_AGENT_OK"
        finally:
            client.close()

    def collect(self, server):
        client = self._connect(server)
        try:
            cpu_text = self._run(client, "LC_ALL=C top -bn1 | head -5")
            memory_text = self._run(client, "LC_ALL=C free -b")
            disk_text = self._run(client, "LC_ALL=C df -B1 / | tail -1")
            network_text = self._run(client, "cat /proc/net/dev")
            process_text = self._run(
                client,
                "LC_ALL=C ps -eo pid,comm,user,%cpu,%mem --no-headers --sort=-%cpu | head -20",
            )
        except Exception as exc:
            raise RemoteMonitorError(str(exc)) from exc
        finally:
            client.close()

        cpu = self._parse_cpu(cpu_text)
        memory, memory_total, memory_used = self._parse_memory(memory_text)
        disk, disk_total, disk_used = self._parse_disk(disk_text)
        net_in, net_out = self._parse_network_rate(server.id, network_text)
        processes = self._parse_processes(process_text)
        now = timezone.localtime()
        return {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": now.isoformat(),
            "server_id": server.id,
            "server_name": server.name,
            "source": "remote",
            "cpu": cpu,
            "cpu_cores": 0,
            "cpu_frequency_mhz": None,
            "memory": memory,
            "memory_total": memory_total,
            "memory_used": memory_used,
            "disk": disk,
            "disk_total": disk_total,
            "disk_used": disk_used,
            "disk_read": 0,
            "disk_write": 0,
            "net_in": net_in,
            "net_out": net_out,
            "top_processes": processes,
            "service_clusters": [],
        }

    def _run(self, client, command):
        _, stdout, stderr = client.exec_command(command, timeout=self.timeout)
        output = stdout.read().decode("utf-8", errors="replace").strip()
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if error and not output:
            raise RemoteMonitorError(error)
        return output

    @staticmethod
    def _parse_cpu(text):
        match = re.search(r"([\d.]+)\s*id", text)
        return round(max(0, 100 - float(match.group(1))), 1) if match else 0

    @staticmethod
    def _parse_memory(text):
        line = next((line for line in text.splitlines() if line.lower().startswith("mem:")), "")
        values = re.findall(r"\d+", line)
        if len(values) < 2:
            return 0, 0, 0
        total, used = int(values[0]), int(values[1])
        return round(used / total * 100, 1) if total else 0, total, used

    @staticmethod
    def _parse_disk(text):
        values = text.split()
        if len(values) < 5:
            return 0, 0, 0
        total, used = int(values[1]), int(values[2])
        return float(values[4].rstrip("%")), total, used

    def _parse_network_rate(self, server_id, text):
        received = sent = 0
        for line in text.splitlines():
            if ":" not in line or line.strip().startswith("lo:"):
                continue
            values = line.split(":", 1)[1].split()
            if len(values) >= 9:
                received += int(values[0]); sent += int(values[8])
        now = time.monotonic()
        previous = self._network_counters.get(server_id)
        self._network_counters[server_id] = (received, sent, now)
        if not previous or now <= previous[2]:
            return 0, 0
        elapsed = now - previous[2]
        return round(max(0, received - previous[0]) / elapsed, 1), round(max(0, sent - previous[1]) / elapsed, 1)

    @staticmethod
    def _parse_processes(text):
        rows = []
        for line in text.splitlines():
            values = line.split(None, 4)
            if len(values) != 5:
                continue
            try:
                rows.append({"pid": int(values[0]), "name": values[1], "username": values[2], "cpu": float(values[3]), "memory": float(values[4])})
            except ValueError:
                continue
        return {
            "cpu": sorted(rows, key=lambda item: item["cpu"], reverse=True)[:10],
            "memory": sorted(rows, key=lambda item: item["memory"], reverse=True)[:10],
        }


remote_monitor = RemoteServerMonitor()
