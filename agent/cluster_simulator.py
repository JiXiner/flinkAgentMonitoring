import math
import time


class LocalDataClusterSimulator:
    """生成明确标记为模拟数据的本机大数据基础设施节点。"""

    SERVICES = (
        ("kafka", "Kafka", ("broker-1", "broker-2", "broker-3")),
        ("redis", "Redis", ("master", "replica-1", "replica-2")),
        ("mysql", "MySQL", ("primary", "replica")),
        ("flink", "Flink", ("jobmanager", "taskmanager-1", "taskmanager-2")),
        ("hdfs", "HDFS", ("namenode", "datanode-1", "datanode-2", "datanode-3")),
        ("yarn", "YARN", ("resourcemanager", "nodemanager-1", "nodemanager-2")),
        ("zookeeper", "ZooKeeper", ("leader", "follower-1", "follower-2")),
        ("elasticsearch", "Elasticsearch", ("master", "data-1", "data-2")),
    )

    def snapshot(self, host_metric):
        tick = time.monotonic()
        clusters = []
        for service_index, (key, label, roles) in enumerate(self.SERVICES):
            nodes = []
            for node_index, role in enumerate(roles):
                factor = 0.045 + service_index * 0.006 + node_index * 0.012
                wave = math.sin(tick / 11 + service_index + node_index) * 1.8
                cpu = max(0.3, min(100, host_metric["cpu"] * factor + wave + 1.8))
                memory_mb = 220 + service_index * 85 + node_index * 105 + host_metric["memory"] * 2
                nodes.append(
                    {
                        "id": f"{key}-{role}",
                        "name": f"{label} {role}",
                        "role": role,
                        "pid": 20000 + service_index * 100 + node_index,
                        "status": "running",
                        "cpu": round(cpu, 1),
                        "memory_mb": round(memory_mb, 1),
                        "network_in": round(host_metric.get("net_in", 0) * factor, 1),
                        "network_out": round(host_metric.get("net_out", 0) * factor, 1),
                        "simulated": True,
                    }
                )
            clusters.append(
                {
                    "key": key,
                    "name": label,
                    "mode": "simulated",
                    "status": "healthy",
                    "nodes": nodes,
                    "metrics": self._service_metrics(key, host_metric, len(nodes)),
                }
            )
        return clusters

    @staticmethod
    def _service_metrics(key, host_metric, node_count):
        cpu = host_metric["cpu"]
        metrics = {
            "kafka": {"partitions": 72, "consumer_lag": max(0, int((cpu - 70) * 4)), "brokers": node_count},
            "redis": {"hit_rate": round(max(85, 99.2 - cpu / 80), 2), "ops_per_sec": int(850 + cpu * 12), "nodes": node_count},
            "mysql": {"connections": int(22 + cpu / 3), "qps": int(180 + cpu * 9), "replication_lag_ms": max(0, int(cpu - 75) * 8)},
            "flink": {"running_jobs": 3, "available_slots": max(0, 12 - int(cpu / 18)), "checkpoint_ms": int(420 + cpu * 8)},
            "hdfs": {"capacity_used": round(min(95, host_metric["disk"] * 0.78), 1), "under_replicated_blocks": 0, "datanodes": node_count - 1},
            "yarn": {"running_apps": 4, "available_vcores": max(0, 24 - int(cpu / 5)), "nodes": node_count - 1},
            "zookeeper": {"connections": 28, "watch_count": 146, "avg_latency_ms": round(1.2 + cpu / 90, 1)},
            "elasticsearch": {"documents": 1284300, "search_qps": int(90 + cpu * 2), "unassigned_shards": 0},
        }
        return metrics[key]


cluster_simulator = LocalDataClusterSimulator()
