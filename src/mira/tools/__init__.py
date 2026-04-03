#!/usr/bin/env python3
"""
工具系统注册表
"""

from mira.tools.base import Tool
from mira.tools.file_tools import (
    FileReadTool, FileEditTool, FileWriteTool, FileAppendTool,
    LSTool, MkdirTool, DeleteTool, MoveTool, CopyTool,
    GlobTool, GrepTool, DiffTool, NotesWriteTool,
)
from mira.tools.command_tools import BashTool, PowerShellTool
from mira.tools.ai_tools import WebSearchTool, WebFetchTool
from mira.tools.todo_tools import TodoWriteTool
from mira.tools.interactive_tools import (
    AskUserQuestionTool, SleepTool, EnterPlanModeTool, ExitPlanModeTool,
)
from mira.tools.task_tools import (
    TaskCreateTool, TaskListTool, TaskGetTool,
    TaskOutputTool, TaskUpdateTool, TaskStopTool,
)
from mira.tools.git_tools import (
    GitStatusTool, GitDiffTool, GitLogTool,
    GitAddTool, GitCommitTool, GitBranchTool, GitPushTool,
)
from mira.tools.system_tools import (
    HttpRequestTool, ArchiveTool, EnvTool, ProcessTool,
    DateTimeTool, HashTool, Base64Tool,
)


def get_tools():
    """获取所有已注册的工具"""
    return [
        # ── 文件读写 ──────────────────────────────────────────
        FileReadTool(),
        FileEditTool(),
        FileWriteTool(),
        FileAppendTool(),
        # ── 目录与文件系统 ─────────────────────────────────────
        LSTool(),
        MkdirTool(),
        DeleteTool(),
        MoveTool(),
        CopyTool(),
        # ── 搜索与比较 ─────────────────────────────────────────
        GlobTool(),
        GrepTool(),
        DiffTool(),
        # ── 命令执行 ──────────────────────────────────────────
        BashTool(),
        PowerShellTool(),
        # ── 网络 ─────────────────────────────────────────────
        WebSearchTool(),
        WebFetchTool(),
        # ── 任务与笔记 ─────────────────────────────────────────
        TodoWriteTool(),
        NotesWriteTool(),
        # ── 交互式 ───────────────────────────────────────────
        AskUserQuestionTool(),
        SleepTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        # ── 任务管理 ──────────────────────────────────────────
        TaskCreateTool(),
        TaskListTool(),
        TaskGetTool(),
        TaskOutputTool(),
        TaskUpdateTool(),
        TaskStopTool(),
        # ── Git ──────────────────────────────────────────────
        GitStatusTool(),
        GitDiffTool(),
        GitLogTool(),
        GitAddTool(),
        GitCommitTool(),
        GitBranchTool(),
        GitPushTool(),
        # ── 系统工具 ──────────────────────────────────────────
        HttpRequestTool(),
        ArchiveTool(),
        EnvTool(),
        ProcessTool(),
        DateTimeTool(),
        HashTool(),
        Base64Tool(),
    ]


def get_tool_by_name(name: str):
    """按名称获取工具实例"""
    for tool in get_tools():
        if tool.name == name:
            return tool
    return None
