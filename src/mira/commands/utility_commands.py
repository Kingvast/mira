#!/usr/bin/env python3
"""
实用工具命令
"""

from mira.commands.base import Command


class HelpCommand(Command):
    """帮助命令"""

    @property
    def name(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "显示帮助信息"

    def execute(self, command: str, engine) -> None:
        try:
            from mira.query import _cyan, _bold, _dim, _gray, _yellow
        except ImportError:
            def _cyan(s): return s
            def _bold(s): return s
            def _dim(s): return s
            def _gray(s): return s
            def _yellow(s): return s

        sep = _gray("─" * 46)
        print(f"\n{sep}")
        print(f"  {_bold('可用命令')}")
        print(sep)
        for cmd in engine.commands:
            pad = 18 - len(cmd.name)
            print(f"  {_cyan('/' + cmd.name)}{' ' * pad}{_dim(cmd.description)}")
        print(sep)
        print(f"  {_dim('示例:')}  {_yellow('分析当前目录的代码结构')}")
        print(f"  {_dim('示例:')}  {_yellow('/session save  →  保存当前会话')}")
        print(sep + "\n")


class ExitCommand(Command):
    """退出命令"""
    
    @property
    def name(self) -> str:
        return "exit"
    
    @property
    def description(self) -> str:
        return "退出 CLI"
    
    def execute(self, command: str, engine) -> None:
        raise SystemExit(0)
