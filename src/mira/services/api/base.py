#!/usr/bin/env python3
"""
API 客户端基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator


class BaseAPIClient(ABC):
    """API 客户端基类"""
    
    def __init__(self, config: dict):
        self.config = config
        self.api_key = config.get("api_key")
        self.model = config.get("model")
        self.temperature = config.get("temperature", 0.7)
    
    @abstractmethod
    def stream_message(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], system: str) -> AsyncGenerator[Dict[str, Any], None]:
        """流式发送消息"""
        pass
    
    @abstractmethod
    def get_tool_schema(self, tool) -> Dict[str, Any]:
        """获取工具的 API schema"""
        pass
