#!/usr/bin/env python3
"""
OpenAI 兼容客户端 - 适用于所有兼容 OpenAI chat/completions 接口的提供商
（OpenAI / DeepSeek / 智谱 / LongCat / 豆包 / 月之暗面 / MiniMax 等）
"""

import json
import httpx
from typing import List, Dict, Any, AsyncGenerator

from mira.services.api.base import BaseAPIClient


class OpenAICompatibleClient(BaseAPIClient):
    """
    通用 OpenAI 兼容客户端。
    流式返回原始 SSE JSON 事件（choices[].delta 格式），
    query.py 的 _parse_stream_event 会直接识别并处理。
    """

    def __init__(self, config: dict):
        super().__init__(config)
        base_url = config.get("base_url", "https://api.openai.com/v1").rstrip("/")
        # Allow providers to override the full chat endpoint URL
        self.chat_url = config.get("chat_url") or f"{base_url}/chat/completions"
        self.supports_tools = config.get("supports_tools", True)
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def stream_message(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            "temperature": self.temperature,
            "stream": True,
        }

        # 工具定义（转成 OpenAI function-calling 格式）
        if tools and self.supports_tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", self.chat_url, headers=self.headers, json=payload
                ) as response:
                    # 非 2xx：读取错误体抛出
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise Exception(
                            f"HTTP {response.status_code}: {body.decode('utf-8', errors='replace')[:300]}"
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException:
            raise Exception("请求超时，请检查网络或稍后重试")
        except httpx.ConnectError as e:
            raise Exception(f"无法连接到 API 服务器: {e}")

    def get_tool_schema(self, tool) -> Dict[str, Any]:
        return tool.input_schema
