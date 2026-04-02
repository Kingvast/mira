#!/usr/bin/env python3
"""
Todo 管理工具 - 追踪任务状态
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from mira.tools.base import Tool

_TODO_FILE = Path.home() / ".mira" / "todos.json"


def _load_todos() -> List[Dict]:
    _TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _TODO_FILE.exists():
        try:
            return json.loads(_TODO_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_todos(todos: List[Dict]):
    _TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TODO_FILE.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")


class TodoWriteTool(Tool):
    """创建和管理 Todo 任务列表"""

    @property
    def name(self) -> str:
        return "TodoWriteTool"

    @property
    def description(self) -> str:
        return (
            "管理任务列表（Todo）。操作：\n"
            "- create: 创建任务（需要 content，可选 priority: high/medium/low）\n"
            "- update: 更新任务状态（需要 id 和 status: pending/in_progress/completed）\n"
            "- delete: 删除任务（需要 id）\n"
            "- list: 列出所有任务"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "delete", "list"],
                    "description": "操作类型",
                },
                "content": {"type": "string", "description": "任务内容（create 时必填）"},
                "id": {"type": "string", "description": "任务 ID（update/delete 时必填）"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "任务状态（update 时填写）",
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "优先级（create 时可选）",
                },
            },
            "required": ["action"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        action = args.get("action", "list")
        todos = _load_todos()

        if action == "list":
            return self._list(todos)
        elif action == "create":
            return self._create(todos, args)
        elif action == "update":
            return self._update(todos, args)
        elif action == "delete":
            return self._delete(todos, args)
        else:
            return f"错误：未知操作 {action}"

    def _list(self, todos: List[Dict]) -> str:
        if not todos:
            return "任务列表为空"
        icons = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}
        priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        lines = ["任务列表:\n"]
        for t in todos:
            status_icon = icons.get(t.get("status", "pending"), "⬜")
            priority_icon = priority_icons.get(t.get("priority", "medium"), "🟡")
            lines.append(f"{status_icon} {priority_icon} [{t['id']}] {t['content']}")
        return "\n".join(lines)

    def _create(self, todos: List[Dict], args: Dict) -> str:
        content = args.get("content", "")
        if not content:
            return "错误：创建任务需要 content 参数"
        import uuid
        new_id = str(uuid.uuid4())[:8]
        todo = {
            "id": new_id,
            "content": content,
            "status": "pending",
            "priority": args.get("priority", "medium"),
            "created_at": datetime.now().isoformat(),
        }
        todos.append(todo)
        _save_todos(todos)
        return f"已创建任务 [{new_id}]: {content}"

    def _update(self, todos: List[Dict], args: Dict) -> str:
        todo_id = args.get("id")
        status = args.get("status")
        if not todo_id:
            return "错误：update 操作需要 id 参数"
        for t in todos:
            if t["id"] == todo_id:
                if status:
                    t["status"] = status
                t["updated_at"] = datetime.now().isoformat()
                _save_todos(todos)
                return f"已更新任务 [{todo_id}] 状态为 {status}"
        return f"错误：未找到任务 {todo_id}"

    def _delete(self, todos: List[Dict], args: Dict) -> str:
        todo_id = args.get("id")
        if not todo_id:
            return "错误：delete 操作需要 id 参数"
        orig_len = len(todos)
        todos = [t for t in todos if t["id"] != todo_id]
        if len(todos) == orig_len:
            return f"错误：未找到任务 {todo_id}"
        _save_todos(todos)
        return f"已删除任务 [{todo_id}]"
