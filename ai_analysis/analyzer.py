import json
from agent.collector import collector
from django.conf import settings

from .deepseek import DeepSeekError, deepseek_client


def _code_context(max_chars=16000):
    snippets = []
    used = 0
    for package in ("agent", "ai_analysis", "monitoring", "dashboard"):
        for path in sorted((settings.BASE_DIR / package).glob("*.py")):
            if path.name == "tests.py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")[:2400]
            if used + len(text) > max_chars:
                return snippets
            snippets.append({"file": str(path.relative_to(settings.BASE_DIR)), "source": text})
            used += len(text)
    return snippets


def current_context(include_code=False):
    metric = collector.get_history()[-1] if collector.get_history() else collector.collect_once()
    from monitoring.models import Server

    servers = list(Server.objects.values("id", "name", "ip", "is_local", "last_status", "last_error"))
    context = {"current_server_metric": metric, "servers": servers}
    if include_code:
        context["project_code"] = _code_context()
    return context


def local_answer(question, context):
    metric = context["current_server_metric"]
    peak = max(metric.get("cpu", 0), metric.get("memory", 0), metric.get("disk", 0))
    needs_action = peak >= 70
    lines = [
        f"当前本机 CPU {metric['cpu']:.1f}%，内存 {metric['memory']:.1f}%，磁盘 {metric['disk']:.1f}%。",
        "需要干预。" if needs_action else "当前不需要人工干预。",
    ]
    if metric.get("cpu", 0) >= 70:
        lines.append("需要优化：检查 CPU TOP 进程、Flink 并行度和任务 Slot 分配。")
    if metric.get("memory", 0) >= 70:
        lines.append("需要优化：检查 JVM/TaskManager 堆内存、缓存上限和异常对象增长。")
    if metric.get("disk", 0) >= 70:
        lines.append("需要优化：清理日志、调整 Checkpoint 保留策略并评估磁盘扩容。")
    if "kafka" in question.lower():
        kafka = next((item for item in metric.get("service_clusters", []) if item["key"] == "kafka"), None)
        if kafka:
            lines.append(f"Kafka 当前为本机模拟集群，共 {len(kafka['nodes'])} 个 Broker，Consumer Lag 为 {kafka['metrics']['consumer_lag']}。")
    if any(key in question.lower() for key in ("redis", "mysql", "flink", "hdfs", "yarn", "zookeeper", "elasticsearch")):
        lines.append("相关中间件节点目前是本机模拟数据；接入真实服务器后 @Jix 会基于真实指标诊断。")
    if not needs_action:
        lines.append("建议继续观察趋势；@Jix 只在达到干预阈值时主动提醒。")
    return "".join(lines)


def answer_question(question):
    context = current_context()
    try:
        return deepseek_client.ask(question, context)
    except DeepSeekError:
        return local_answer(question, context)


def run_inspection():
    context = current_context(include_code=True)
    prompt = "请执行一次12小时智能巡检，返回JSON，字段为 level、problem、reason、impact、suggestions、code_optimizations、needs_intervention。只在确有风险时要求干预。"
    try:
        raw = deepseek_client.ask(prompt, context, json_mode=True)
        report = json.loads(raw)
    except (DeepSeekError, json.JSONDecodeError):
        metric = context["current_server_metric"]
        peak = max(metric["cpu"], metric["memory"], metric["disk"])
        report = {
            "level": "warning" if peak >= 70 else "info",
            "problem": "资源负载需要关注" if peak >= 70 else "未发现需要干预的异常",
            "reason": "CPU、内存或磁盘达到关注阈值" if peak >= 70 else "核心指标均处于健康区间",
            "impact": "可能影响数据任务稳定性" if peak >= 85 else "当前影响较低",
            "suggestions": ["检查资源 TOP 进程", "复核任务并行度和容量水位"] if peak >= 70 else ["保持当前监控策略"],
            "code_optimizations": ["为外部 API 增加超时、重试和熔断", "避免无界历史数据与高频全量 DOM 更新"],
            "needs_intervention": peak >= 70,
        }
    return report, context
