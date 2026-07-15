import json

import requests
from django.conf import settings


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    system_prompt = """你是 @Jix，一名高级大数据平台运维专家。你负责服务器、Flink、Kafka、Redis、MySQL、HDFS、YARN、ZooKeeper 和 Elasticsearch 的运维诊断。
回答必须基于提供的实时上下文，不得编造未提供的真实故障。明确区分模拟节点和真实节点。
回答结构优先包含：当前判断、是否需要干预、需要优化的项目、可执行步骤。正常且无需干预时简洁说明，不制造告警。"""

    def ask(self, question, context, json_mode=False):
        if not settings.DEEPSEEK_API_KEY:
            raise DeepSeekError("DeepSeek API 尚未配置")
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"运行上下文：\n{json.dumps(context, ensure_ascii=False)}\n\n用户问题：{question}"},
        ]
        payload = {
            "model": settings.DEEPSEEK_MODEL,
            "messages": messages,
            "stream": False,
            "max_tokens": 1200,
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = requests.post(
                settings.DEEPSEEK_API_URL,
                headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=(8, 60),
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            raise DeepSeekError("DeepSeek 服务调用失败") from exc


deepseek_client = DeepSeekClient()
