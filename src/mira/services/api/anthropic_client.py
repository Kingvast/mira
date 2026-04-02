#!/usr/bin/env python3
"""
Anthropic API 客户端 - 真正的异步流式实现
"""

import asyncio
import json
import httpx
from typing import List, Dict, Any, AsyncGenerator

from mira.services.api.base import BaseAPIClient

_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MAX_TOKENS = 8096


class AnthropicClient(BaseAPIClient):
    """Anthropic API 异步流式客户端"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.anthropic.com").rstrip("/")
        self.api_url  = f"{self.base_url}/v1/messages"

    async def stream_message(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """异步流式发送消息，解析 Anthropic SSE 事件"""
        if not self.api_key:
            raise ValueError("请设置 ANTHROPIC_API_KEY 环境变量")

        tool_schemas = [
            {
                "name":         t["name"],
                "description":  t["description"],
                "input_schema": t["input_schema"],
            }
            for t in tools
        ]

        extended_thinking = self.config.get("extended_thinking", False)
        prompt_caching    = self.config.get("prompt_caching", True)

        # Extended thinking requires a higher max_tokens budget
        max_tokens = _DEFAULT_MAX_TOKENS
        if extended_thinking:
            max_tokens = max(max_tokens, 16000)

        payload: Dict[str, Any] = {
            "model":      self.model,
            "messages":   messages,
            "system":     system,
            "max_tokens": max_tokens,
            "stream":     True,
        }
        if tool_schemas:
            payload["tools"] = tool_schemas

        # Extended thinking (Claude 3.7+)
        if extended_thinking:
            payload["thinking"] = {
                "type":         "enabled",
                "budget_tokens": 10000,
            }

        headers = {
            "Content-Type":      "application/json",
            "X-API-Key":         self.api_key,
            "anthropic-version": "2023-06-01",
        }

        # Prompt caching: mark system prompt and last user message
        if prompt_caching:
            headers["anthropic-beta"] = "prompt-caching-2024-07-31"
            payload["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
            # Mark last user message if it has enough content (>1024 tokens estimated)
            msgs = payload["messages"]
            for i in range(len(msgs) - 1, -1, -1):
                msg = msgs[i]
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str) and len(content) > 4096:
                        msgs[i] = dict(msg)
                        msgs[i]["content"] = [
                            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                        ]
                    break
        else:
            payload["system"] = system

        # tool_use block 的累加缓冲 {index: {id, name, input_json}}
        tool_blocks: Dict[int, Dict[str, Any]] = {}
        current_block_idx: int = -1
        current_block_type: str = ""
        thinking_blocks: Dict[int, str] = {}  # index -> accumulated thinking text

        _max_retries = 3
        _retry_delay = 1.0

        for _attempt in range(_max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    async with client.stream(
                        "POST", self.api_url, headers=headers, json=payload
                    ) as response:
                        if response.status_code in (429, 529):
                            body = await response.aread()
                            if _attempt < _max_retries:
                                await asyncio.sleep(_retry_delay * (2 ** _attempt))
                                continue
                            raise Exception(
                                f"Anthropic API HTTP {response.status_code} (rate limit/overload): "
                                f"{body.decode('utf-8', errors='replace')[:400]}"
                            )
                        if response.status_code >= 400:
                            body = await response.aread()
                            raise Exception(
                                f"Anthropic API HTTP {response.status_code}: "
                                f"{body.decode('utf-8', errors='replace')[:400]}"
                            )

                        async for raw_line in response.aiter_lines():
                            raw_line = raw_line.strip()
                            if not raw_line:
                                continue

                            # SSE event type line (e.g. "event: content_block_delta")
                            if raw_line.startswith("event:"):
                                continue

                            if not raw_line.startswith("data:"):
                                continue

                            data_str = raw_line[5:].strip()
                            if data_str in ("[DONE]", ""):
                                continue

                            try:
                                ev = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            etype = ev.get("type", "")

                            # ── message_start: 包含初始 usage ─────────────────────────
                            if etype == "message_start":
                                msg = ev.get("message", {})
                                usage = msg.get("usage", {})
                                if usage:
                                    yield {
                                        "type":               "usage",
                                        "input_tokens":       usage.get("input_tokens", 0),
                                        "output_tokens":      usage.get("output_tokens", 0),
                                        "cache_read_tokens":  usage.get("cache_read_input_tokens", 0),
                                        "cache_write_tokens": usage.get("cache_creation_input_tokens", 0),
                                    }

                            # ── content_block_start ────────────────────────────────────
                            elif etype == "content_block_start":
                                block = ev.get("content_block", {})
                                current_block_idx  = ev.get("index", 0)
                                current_block_type = block.get("type", "")
                                if current_block_type == "tool_use":
                                    tool_blocks[current_block_idx] = {
                                        "id":         block.get("id", ""),
                                        "name":       block.get("name", ""),
                                        "input_json": "",
                                    }
                                elif current_block_type == "thinking":
                                    thinking_blocks[current_block_idx] = ""

                            # ── content_block_delta ────────────────────────────────────
                            elif etype == "content_block_delta":
                                delta = ev.get("delta", {})
                                dtype = delta.get("type", "")

                                if dtype == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        yield {"type": "content_block_delta", "text": text}

                                elif dtype == "input_json_delta":
                                    partial = delta.get("partial_json", "")
                                    idx = ev.get("index", current_block_idx)
                                    if idx in tool_blocks:
                                        tool_blocks[idx]["input_json"] += partial

                                elif dtype == "thinking_delta":
                                    thinking_text = delta.get("thinking", "")
                                    idx = ev.get("index", current_block_idx)
                                    if idx in thinking_blocks:
                                        thinking_blocks[idx] += thinking_text

                            # ── content_block_stop ─────────────────────────────────────
                            elif etype == "content_block_stop":
                                idx = ev.get("index", current_block_idx)
                                if idx in tool_blocks:
                                    blk = tool_blocks.pop(idx)
                                    try:
                                        args = json.loads(blk["input_json"]) if blk["input_json"] else {}
                                    except json.JSONDecodeError:
                                        args = {}
                                    yield {
                                        "type":     "tool_use",
                                        "tool_use": {
                                            "id":   blk["id"],
                                            "name": blk["name"],
                                            "args": args,
                                        },
                                    }
                                elif idx in thinking_blocks:
                                    content = thinking_blocks.pop(idx)
                                    if content.strip():
                                        yield {"type": "thinking", "content": content}

                            # ── message_delta: 最终 usage 更新 ────────────────────────
                            elif etype == "message_delta":
                                usage = ev.get("usage", {})
                                if usage:
                                    yield {
                                        "type":          "usage",
                                        "input_tokens":  0,
                                        "output_tokens": usage.get("output_tokens", 0),
                                        "cache_read_tokens": 0,
                                    }

                            # ── message_stop ───────────────────────────────────────────
                            elif etype == "message_stop":
                                yield {"type": "message_stop"}

                        # Successfully completed — break retry loop
                        return

            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "529" in err_str or "rate limit" in err_str.lower()) and _attempt < _max_retries:
                    await asyncio.sleep(_retry_delay * (2 ** _attempt))
                    continue
                raise

    def get_tool_schema(self, tool) -> Dict[str, Any]:
        return tool.input_schema
