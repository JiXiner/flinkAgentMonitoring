"""服务器监控服务入口；第二阶段将在此聚合磁盘、网络与进程指标。"""

from .collector import collector


def get_local_snapshot():
    return collector.collect_once()
