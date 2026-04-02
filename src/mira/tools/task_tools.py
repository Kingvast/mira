#!/usr/bin/env python3
"""
任务管理工具 - 创建、跟踪和管理异步子任务

允许 AI 启动后台子代理任务并查询其状态/输出，
对于需要并行执行的复杂多步工作流非常有用。
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable

from mira.tools.base import Tool

# ─── 全局任务注册表 ────────────────────────────────────────────────────────────

_task_registry: Dict[str, "TaskInfo"] = {}


class TaskInfo:
    """单个任务的状态记录"""

    def __init__(self, task_id: str, title: str, prompt: str):
        self.task_id = task_id
        self.title = title
        self.prompt = prompt
        self.status = "pending"          # pending/running/completed/failed/cancelled
        self.output_parts: List[str] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self._async_task: Optional[asyncio.Task] = None

    def add_output(self, text: str):
        self.output_parts.append(text)
        self.updated_at = datetime.now().isoformat()

    @property
    def output(self) -> str:
        return "".join(self.output_parts)

    def to_dict(self) -> Dict:
        return {
            "task_id":    self.task_id,
            "title":      self.title,
            "prompt":     self.prompt[:120] + ("…" if len(self.prompt) > 120 else ""),
            "status":     self.status,
            "output_len": len(self.output),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def get_task(task_id: str) -> Optional[TaskInfo]:
    return _task_registry.get(task_id)


def list_tasks() -> List[TaskInfo]:
    return sorted(_task_registry.values(), key=lambda t: t.created_at, reverse=True)


# ─── 子任务执行协程 ────────────────────────────────────────────────────────────

async def _run_task_coroutine(task_info: TaskInfo, engine_config: dict,
                               provider: str, model: str):
    """在子 QueryEngine 中运行任务提示"""
    from mira.query import QueryEngine

    async def _cb(event):
        t = event.get("type")
        if t == "text":
            task_info.add_output(event.get("content", ""))
        elif t == "tool_start":
            task_info.add_output(f"\n[工具: {event.get('name', '')}]\n")
        elif t == "tool_result":
            snippet = str(event.get("content", ""))[:200]
            task_info.add_output(f"[结果: {snippet}]\n")
        elif t == "error":
            task_info.add_output(f"\n[错误: {event.get('message', '')}]\n")

    task_info.status = "running"
    task_info.updated_at = datetime.now().isoformat()
    try:
        sub_engine = QueryEngine(
            config=engine_config,
            provider=provider,
            model=model,
            skip_permissions=True,  # 子任务静默执行
        )
        await sub_engine.process_message(task_info.prompt, callback=_cb)
        task_info.status = "completed"
    except asyncio.CancelledError:
        task_info.status = "cancelled"
    except Exception as e:
        task_info.status = "failed"
        task_info.add_output(f"\n[任务失败: {e}]\n")
    finally:
        task_info.updated_at = datetime.now().isoformat()


# ─── 工具实现 ─────────────────────────────────────────────────────────────────

class TaskCreateTool(Tool):
    """创建一个异步后台子代理任务"""

    @property
    def name(self) -> str:
        return "TaskCreate"

    @property
    def description(self) -> str:
        return (
            "创建一个异步子代理任务，让 AI 在后台执行指定提示，同时父代理继续工作。\n"
            "适用于：独立的并行子任务、耗时操作、需要隔离执行的工作。\n"
            "返回 task_id，可用 TaskGet/TaskOutput/TaskStop 查询或停止任务。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title":  {"type": "string", "description": "任务的简短标题"},
                "prompt": {"type": "string", "description": "要执行的任务提示内容"},
            },
            "required": ["title", "prompt"],
        }

    async def execute_async(self, args: Dict[str, Any], callback: Callable,
                             engine=None) -> str:
        title  = args.get("title", "子任务")
        prompt = args.get("prompt", "")
        if not prompt:
            return "错误：prompt 不能为空"

        task_id = str(uuid.uuid4())[:8]
        task_info = TaskInfo(task_id, title, prompt)
        _task_registry[task_id] = task_info

        if engine is not None:
            # 在当前事件循环中创建后台 asyncio.Task
            config  = engine.config
            provider = engine.provider
            model   = engine.model
            coro = _run_task_coroutine(task_info, config, provider, model)
            task_info._async_task = asyncio.create_task(coro)
        else:
            task_info.status = "failed"
            task_info.add_output("错误：无法获取引擎配置，任务未启动")

        return (
            f"任务已创建\n"
            f"- ID: {task_id}\n"
            f"- 标题: {title}\n"
            f"- 状态: {task_info.status}\n"
            f"使用 TaskGet(task_id='{task_id}') 查询进度"
        )

    def execute(self, args: Dict[str, Any]) -> str:
        return "错误：TaskCreate 需要在异步上下文中调用（engine 未传递）"


class TaskListTool(Tool):
    """列出所有子任务及其状态"""

    @property
    def name(self) -> str:
        return "TaskList"

    @property
    def description(self) -> str:
        return "列出所有已创建的子代理任务及其当前状态（pending/running/completed/failed/cancelled）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "pending", "running", "completed", "failed", "cancelled"],
                    "description": "按状态过滤（默认 all）",
                },
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        status_filter = args.get("status_filter", "all")
        tasks = list_tasks()
        if status_filter != "all":
            tasks = [t for t in tasks if t.status == status_filter]
        if not tasks:
            return "没有任务" if status_filter == "all" else f"没有状态为 '{status_filter}' 的任务"

        icons = {
            "pending": "⏳", "running": "🔄",
            "completed": "✅", "failed": "❌", "cancelled": "⊘",
        }
        lines = [f"任务列表（共 {len(tasks)} 个）:\n"]
        for t in tasks:
            icon = icons.get(t.status, "?")
            lines.append(f"{icon} [{t.task_id}] {t.title}  ({t.status})  输出: {len(t.output)} 字符")
        return "\n".join(lines)


class TaskGetTool(Tool):
    """获取单个任务的详情"""

    @property
    def name(self) -> str:
        return "TaskGet"

    @property
    def description(self) -> str:
        return "获取指定任务的详情：状态、标题、提示词、输出长度"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
            },
            "required": ["task_id"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        task_id = args.get("task_id", "")
        task = get_task(task_id)
        if not task:
            return f"错误：未找到任务 '{task_id}'"
        d = task.to_dict()
        return (
            f"任务详情:\n"
            f"- ID:       {d['task_id']}\n"
            f"- 标题:     {d['title']}\n"
            f"- 状态:     {d['status']}\n"
            f"- 提示:     {d['prompt']}\n"
            f"- 输出长度: {d['output_len']} 字符\n"
            f"- 创建:     {d['created_at']}\n"
            f"- 更新:     {d['updated_at']}\n"
        )


class TaskOutputTool(Tool):
    """获取任务的输出内容"""

    @property
    def name(self) -> str:
        return "TaskOutput"

    @property
    def description(self) -> str:
        return "获取指定任务生成的完整输出内容（AI 回复 + 工具结果摘要）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
                "tail":    {
                    "type": "integer",
                    "description": "仅返回末尾 N 个字符（0 = 全部，默认 2000）",
                },
            },
            "required": ["task_id"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        task_id = args.get("task_id", "")
        task = get_task(task_id)
        if not task:
            return f"错误：未找到任务 '{task_id}'"
        output = task.output
        if not output:
            return f"任务 '{task_id}' 暂无输出（状态: {task.status}）"
        tail = args.get("tail", 2000)
        if tail and len(output) > tail:
            output = f"…（省略前 {len(output)-tail} 字符）\n" + output[-tail:]
        return f"任务 [{task_id}] 输出（状态: {task.status}）:\n\n{output}"


class TaskUpdateTool(Tool):
    """更新任务的标题或备注"""

    @property
    def name(self) -> str:
        return "TaskUpdate"

    @property
    def description(self) -> str:
        return "更新任务的标题（不影响执行状态）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
                "title":   {"type": "string", "description": "新标题"},
            },
            "required": ["task_id"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        task_id = args.get("task_id", "")
        task = get_task(task_id)
        if not task:
            return f"错误：未找到任务 '{task_id}'"
        new_title = args.get("title", "").strip()
        if new_title:
            old_title = task.title
            task.title = new_title
            task.updated_at = datetime.now().isoformat()
            return f"任务 [{task_id}] 标题已更新: '{old_title}' → '{new_title}'"
        return "错误：title 不能为空"


class TaskStopTool(Tool):
    """停止正在运行的任务"""

    @property
    def name(self) -> str:
        return "TaskStop"

    @property
    def description(self) -> str:
        return "取消/停止指定的后台任务（仅对 running/pending 状态有效）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "要停止的任务 ID"},
            },
            "required": ["task_id"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        task_id = args.get("task_id", "")
        task = get_task(task_id)
        if not task:
            return f"错误：未找到任务 '{task_id}'"
        if task.status in ("completed", "failed", "cancelled"):
            return f"任务 [{task_id}] 已处于终态（{task.status}），无需停止"
        if task._async_task and not task._async_task.done():
            task._async_task.cancel()
            return f"已发送取消信号给任务 [{task_id}]（{task.title}），等待停止中…"
        task.status = "cancelled"
        task.updated_at = datetime.now().isoformat()
        return f"任务 [{task_id}] 已标记为已取消"
