#!/usr/bin/env python3
"""
工具基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class Tool(ABC):
    """工具基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """输入模式"""
        pass
    
    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> Any:
        """执行工具"""
        pass
