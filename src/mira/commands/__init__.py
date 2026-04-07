#!/usr/bin/env python3
"""
命令系统注册表
"""

from mira.commands.base import Command
from mira.commands.session_commands import SessionCommand, ResumeCommand, ClearCommand
from mira.commands.config_commands import ConfigCommand, PermissionsCommand
from mira.commands.utility_commands import HelpCommand, ExitCommand
from mira.commands.dev_commands import (
    VersionCommand, ModelCommand, CompactCommand, ContextCommand,
    DoctorCommand, InitCommand, MemoryCommand, DiffCommand, TodoCommand,
    StatusCommand, CostCommand, CommitCommand, AddDirCommand, PluginCommand,
    PlanCommand, TaskCommand, UndoCommand, ExportCommand,
    SnipCommand, RunCommand,
    FindCommand, TokensCommand, LintCommand, TestCommand, FormatCommand,
)
from mira.commands.skill_command import SkillCommand


def get_commands(extra_commands=None):
    """获取所有已注册的命令（含插件扩展）"""
    base = [
        # 会话管理
        SessionCommand(),
        ResumeCommand(),
        ClearCommand(),
        # 配置
        ConfigCommand(),
        PermissionsCommand(),
        ModelCommand(),
        # 技能
        SkillCommand(),
        # 开发工具
        CompactCommand(),
        ContextCommand(),
        DiffCommand(),
        InitCommand(),
        MemoryCommand(),
        TodoCommand(),
        DoctorCommand(),
        VersionCommand(),
        # 状态与费用
        StatusCommand(),
        CostCommand(),
        # 工作流
        CommitCommand(),
        AddDirCommand(),
        PluginCommand(),
        PlanCommand(),
        TaskCommand(),
        UndoCommand(),
        ExportCommand(),
        SnipCommand(),
        RunCommand(),
        FindCommand(),
        TokensCommand(),
        LintCommand(),
        TestCommand(),
        FormatCommand(),
        # 通用
        HelpCommand(),
        ExitCommand(),
    ]
    if extra_commands:
        base.extend(extra_commands)
    return base
