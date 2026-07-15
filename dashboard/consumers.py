from channels.generic.websocket import AsyncJsonWebsocketConsumer

from agent.collector import METRICS_GROUP, collector
from agent.cluster_collector import cluster_collector, server_group


class MetricsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.server_id = self.scope["url_route"]["kwargs"].get("server_id")
        self.metrics_group = server_group(self.server_id) if self.server_id else METRICS_GROUP
        await self.channel_layer.group_add(self.metrics_group, self.channel_name)
        await self.accept()
        if self.server_id:
            cluster_collector.start()
            history = cluster_collector.get_history(self.server_id)
        else:
            collector.start()
            history = collector.get_history()
        await self.send_json(
            {"type": "metrics.history", "metrics": history}
        )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.metrics_group, self.channel_name)

    async def jix_report(self, event):
        await self.send_json({"type": "jix.report", "report": event["report"]})

    async def metrics_update(self, event):
        await self.send_json({"type": "metrics.update", "metric": event["metric"]})
