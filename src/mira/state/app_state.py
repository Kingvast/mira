#!/usr/bin/env python3
"""
应用状态管理
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional


class AppState:
    """应用状态 - 管理对话历史和会话元数据"""

    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self.is_loading: bool = False
        self.error: Optional[str] = None
        self.session_id: str = str(uuid.uuid4())[:8]
        self.created_at: str = datetime.now().isoformat()

    def add_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """添加消息，自动附加 id 和时间戳"""
        msg = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            **message,
        }
        self.messages.append(msg)
        return msg

    def clear_messages(self):
        """清除所有消息"""
        self.messages = []

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages

    def estimate_tokens(self) -> int:
        """粗估 token 数（字符数 / 4）"""
        return sum(len(str(m.get("content", ""))) for m in self.messages) // 4

    def export_messages(self) -> List[Dict[str, Any]]:
        """导出消息（去除 id/timestamp 等元数据，保留所有语义字段）"""
        keep = {"role", "content", "tool_calls", "tool_call_id", "name", "tool_results"}
        result = []
        for m in self.messages:
            msg = {k: v for k, v in m.items() if k in keep}
            if msg:
                result.append(msg)
        return result

    def to_dict(self, provider: str = "", model: str = "") -> Dict[str, Any]:
        """序列化为会话字典（用于持久化）"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "messages": self.export_messages(),
        }

    def load_from_dict(self, data: Dict[str, Any]):
        """从持久化字典恢复状态"""
        self.session_id = data.get("session_id", self.session_id)
        self.created_at = data.get("created_at", self.created_at)
        self.messages = []
        for msg in data.get("messages", []):
            self.add_message(msg)
