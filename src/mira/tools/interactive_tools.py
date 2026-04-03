#!/usr/bin/env python3
"""
交互式工具 - 需要用户参与的工具，以及 SleepTool、计划模式工具
"""
import asyncio
import time
from mira.tools.base import Tool
from typing import Dict, Any, Callable


class AskUserQuestionTool(Tool):
    """向用户提问并等待回答"""

    @property
    def name(self):
        return "AskUserQuestion"

    @property
    def description(self):
        return "当需要用户提供信息、做出决策或澄清时使用此工具向用户提问"

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "要问用户的问题"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选的选项列表（可选）",
                },
            },
            "required": ["question"],
        }

    async def execute_async(self, args: Dict[str, Any], callback: Callable,
                             engine=None) -> str:
        question = args.get("question", "")
        options = args.get("options", [])
        # Web 模式：通过 WebSocket 发给浏览器等待回复
        if engine is not None and getattr(engine, "_ask_fn", None):
            return await engine._ask_fn(question, options)
        # CLI 降级：在终端交互
        return await asyncio.to_thread(self._cli_ask, question, options)

    def _cli_ask(self, question: str, options: list) -> str:
        print(f"\n  ❓ {question}")
        if options:
            for i, opt in enumerate(options, 1):
                print(f"     {i}. {opt}")
            print()
        try:
            answer = input("  → ").strip()
            return answer if answer else "(用户未输入)"
        except (EOFError, KeyboardInterrupt):
            return "(用户中断)"

    def execute(self, args: Dict[str, Any]) -> str:
        question = args.get("question", "")
        options = args.get("options", [])

        print(f"\n  ❓ {question}")
        if options:
            for i, opt in enumerate(options, 1):
                print(f"     {i}. {opt}")
            print()

        try:
            answer = input("  → ").strip()
            return answer if answer else "(用户未输入)"
        except (EOFError, KeyboardInterrupt):
            return "(用户中断)"


class NotesWriteTool(Tool):
    """向项目记忆文件 NOTES.md 追加笔记（interactive_tools 版本，委托给 file_tools）"""

    @property
    def name(self):
        return "NotesWrite"

    @property
    def description(self):
        return "向项目 NOTES.md 写入重要信息、约定或上下文，供后续会话使用"

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "要写入的内容"},
                "category": {
                    "type": "string",
                    "description": "分类标题",
                    "default": "笔记",
                },
            },
            "required": ["content"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        from mira.utils.memory import append_note

        content = args.get("content", "")
        category = args.get("category", "笔记")
        append_note(content, category)
        return f"已写入笔记（分类: {category}）"


class SleepTool(Tool):
    """等待指定的秒数（用于定时/节流场景）"""

    @property
    def name(self) -> str:
        return "Sleep"

    @property
    def description(self) -> str:
        return "等待指定秒数后继续。适用于需要等待外部操作完成、限流保护或定时执行的场景。最大等待 60 秒。"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "number",
                    "description": "等待的秒数（0.1 ~ 60）",
                    "minimum": 0.1,
                    "maximum": 60,
                },
                "reason": {
                    "type": "string",
                    "description": "等待原因（可选，用于日志）",
                },
            },
            "required": ["seconds"],
        }

    async def execute_async(self, args: Dict[str, Any], callback: Callable,
                             engine=None) -> str:
        seconds = float(args.get("seconds", 1))
        seconds = max(0.1, min(60.0, seconds))
        reason = args.get("reason", "")
        await asyncio.sleep(seconds)
        msg = f"已等待 {seconds:.1f} 秒"
        if reason:
            msg += f"（{reason}）"
        return msg

    def execute(self, args: Dict[str, Any]) -> str:
        seconds = float(args.get("seconds", 1))
        seconds = max(0.1, min(60.0, seconds))
        time.sleep(seconds)
        return f"已等待 {seconds:.1f} 秒"


class EnterPlanModeTool(Tool):
    """进入计划模式（AI 只描述行动计划，不真正执行工具）"""

    @property
    def name(self) -> str:
        return "EnterPlanMode"

    @property
    def description(self) -> str:
        return (
            "进入计划模式。在此模式下，AI 可以描述打算执行的操作步骤，但实际工具调用不会被执行。"
            "用于在获得用户确认前先展示完整执行计划。使用 ExitPlanMode 退出并开始实际执行。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "进入计划模式的原因（可选）",
                },
            },
        }

    async def execute_async(self, args: Dict[str, Any], callback: Callable,
                             engine=None) -> str:
        if engine is not None:
            engine._plan_mode = True
        reason = args.get("reason", "")
        msg = "已进入计划模式（Plan Mode）。后续工具调用将只显示描述，不会真正执行。"
        if reason:
            msg += f"\n原因: {reason}"
        return msg

    def execute(self, args: Dict[str, Any]) -> str:
        return "已进入计划模式（工具不会实际执行）"


class ExitPlanModeTool(Tool):
    """退出计划模式，恢复正常工具执行"""

    @property
    def name(self) -> str:
        return "ExitPlanMode"

    @property
    def description(self) -> str:
        return (
            "退出计划模式，恢复工具的实际执行。在用户确认计划后调用此工具开始真正执行操作。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute_async(self, args: Dict[str, Any], callback: Callable,
                             engine=None) -> str:
        if engine is not None:
            engine._plan_mode = False
        return "已退出计划模式，后续工具调用将正常执行。"

    def execute(self, args: Dict[str, Any]) -> str:
        return "已退出计划模式"
