#!/usr/bin/env python3
"""
命令基类
"""

from abc import ABC, abstractmethod
from typing import Optional


class Command(ABC):
    """命令基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """命令名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """命令描述"""
        pass
    
    @abstractmethod
    def execute(self, command: str, engine) -> None:
        """执行命令"""
        pass
