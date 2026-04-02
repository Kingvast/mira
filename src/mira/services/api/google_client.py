#!/usr/bin/env python3
"""
Google API 客户端
"""

import os
import warnings
from typing import List, Dict, Any, AsyncGenerator
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import google.generativeai as genai

from mira.services.api.base import BaseAPIClient


class GoogleClient(BaseAPIClient):
    """Google API 客户端"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        genai.configure(api_key=self.api_key)
        self.client = genai.GenerativeModel(self.model)
    
    def stream_message(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], system: str) -> AsyncGenerator[Dict[str, Any], None]:
        """流式发送消息"""
        # Google API 需要不同的消息格式
        chat_history = []
        for msg in messages:
            if msg["role"] == "user":
                chat_history.append({"role": "user", "parts": [msg["content"]]})
            elif msg["role"] == "assistant":
                chat_history.append({"role": "model", "parts": [msg["content"]]})
        
        # 发送请求
        response = self.client.generate_content(
            system + "\n\n" + "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages]),
            stream=True,
            generation_config=genai.types.GenerationConfig(
                temperature=self.temperature
            )
        )
        
        # 处理流式响应
        for chunk in response:
            if chunk.text:
                yield {
                    "type": "content_block_delta",
                    "text": chunk.text
                }
        
        yield {
            "type": "message_stop"
        }
    
    def get_tool_schema(self, tool) -> Dict[str, Any]:
        """获取工具的 API schema"""
        return tool.input_schema
