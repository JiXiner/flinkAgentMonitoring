from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.db import connection

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from agent.collector import METRICS_GROUP, LocalMetricCollector, collector
from agent.cluster_simulator import cluster_simulator
from config.asgi import application
from monitoring.models import Server


class DashboardViewTests(SimpleTestCase):
    def test_dashboard_is_available(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flink-Agent")
        self.assertContains(response, "metricsChart")
        self.assertContains(response, "智能运维助手")


class LocalMetricCollectorTests(SimpleTestCase):
    @patch("agent.collector.timezone.localtime")
    @patch("agent.collector.psutil.cpu_freq")
    @patch("agent.collector.psutil.cpu_count", return_value=8)
    @patch("agent.collector.psutil.cpu_percent", return_value=26.5)
    @patch("agent.collector.psutil.virtual_memory")
    def test_collect_once_returns_normalized_metric(
        self, virtual_memory, _cpu_percent, _cpu_count, cpu_freq, localtime
    ):
        import datetime

        virtual_memory.return_value = SimpleNamespace(
            percent=61.2, total=16 * 1024**3, used=10 * 1024**3
        )
        cpu_freq.return_value = SimpleNamespace(current=3200.0)
        localtime.return_value = datetime.datetime(2026, 7, 16, 10, 0, 0)

        metric = LocalMetricCollector().collect_once()

        self.assertEqual(metric["time"], "2026-07-16 10:00:00")
        self.assertEqual(metric["cpu"], 26.5)
        self.assertEqual(metric["memory"], 61.2)
        self.assertEqual(metric["cpu_cores"], 8)
        self.assertEqual(metric["cpu_frequency_mhz"], 3200.0)
        self.assertIn("disk", metric)
        self.assertIn("net_in", metric)
        self.assertIn("net_out", metric)
        self.assertIn("top_processes", metric)

    def test_simulated_data_infrastructure_contains_expected_services(self):
        clusters = cluster_simulator.snapshot({"cpu": 20, "memory": 40, "disk": 30, "net_in": 1000, "net_out": 500})
        keys = {cluster["key"] for cluster in clusters}
        self.assertTrue({"kafka", "redis", "mysql", "flink", "hdfs", "yarn", "zookeeper", "elasticsearch"}.issubset(keys))
        self.assertTrue(all(cluster["mode"] == "simulated" for cluster in clusters))


class MetricsWebSocketTests(SimpleTestCase):
    async def test_websocket_pushes_metric_update(self):
        communicator = WebsocketCommunicator(application, "/ws/metrics/")
        with patch.object(collector, "start"):
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            history = await communicator.receive_json_from()
            self.assertEqual(history["type"], "metrics.history")

            metric = {"time": "2026-07-16 10:00:00", "cpu": 25, "memory": 50}
            await get_channel_layer().group_send(
                METRICS_GROUP, {"type": "metrics.update", "metric": metric}
            )
            update = await communicator.receive_json_from()
            self.assertEqual(update["type"], "metrics.update")
            self.assertEqual(update["metric"], metric)
            await communicator.disconnect()


class ServerApiTests(TestCase):
    def test_server_password_is_encrypted_and_never_returned(self):
        response = self.client.post(
            "/api/servers/",
            data={"name": "worker-01", "ip": "192.168.10.21", "port": 22, "username": "ops", "password": "secret-value"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.json())
        server = Server.objects.get(name="worker-01")
        self.assertEqual(server.password, "secret-value")
        with connection.cursor() as cursor:
            cursor.execute("SELECT password FROM monitoring_server WHERE id=%s", [server.id])
            self.assertTrue(cursor.fetchone()[0].startswith("enc::"))

    @patch("ai_analysis.views.answer_question", return_value="@Jix 智能回答")
    def test_jix_chat_endpoint(self, _answer):
        response = self.client.post("/api/jix/chat/", data={"question": "当前需要优化什么？"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "@Jix 智能回答")

    @patch("ai_analysis.views.execute_inspection")
    def test_manual_inspection_endpoint(self, execute):
        execute.return_value = {"level": "info", "problem": "正常", "suggestions": []}
        response = self.client.post("/api/jix/inspect/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["problem"], "正常")
