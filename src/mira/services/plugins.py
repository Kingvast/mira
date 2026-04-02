#!/usr/bin/env python3
"""
Plugin 系统 — 动态加载用户插件

插件目录：~/.mira/plugins/
每个 .py 文件是一个独立插件，可导出：
  - get_tools()    → List[Tool]    额外工具
  - get_commands() → List[Command] 额外命令

单个插件加载失败不影响其他插件，失败时打印警告。
"""

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import List, Tuple, Any

# 插件目录
PLUGINS_DIR = Path.home() / ".mira" / "plugins"


def load_plugins() -> Tuple[List[Any], List[Any]]:
    """
    扫描 ~/.mira/plugins/ 目录，动态 import 每个 .py 文件。

    返回 (extra_tools, extra_commands) 元组：
      - extra_tools:    所有插件 get_tools() 返回值的合并列表
      - extra_commands: 所有插件 get_commands() 返回值的合并列表

    目录不存在时安静返回空列表。
    单个插件加载或调用失败时打印警告，继续处理其他插件。
    """
    extra_tools: List[Any] = []
    extra_commands: List[Any] = []

    # 目录不存在则跳过
    if not PLUGINS_DIR.is_dir():
        return extra_tools, extra_commands

    plugin_files = sorted(PLUGINS_DIR.glob("*.py"))

    if not plugin_files:
        return extra_tools, extra_commands

    for plugin_path in plugin_files:
        module_name = f"_mira_plugin_{plugin_path.stem}"
        try:
            tools, commands = _load_single_plugin(plugin_path, module_name)
            extra_tools.extend(tools)
            extra_commands.extend(commands)
        except Exception:
            # 打印详细警告，但不中断整体流程
            print(
                f"[plugins] ⚠️  加载插件 '{plugin_path.name}' 失败，已跳过：\n"
                f"{traceback.format_exc(limit=3)}"
            )

    return extra_tools, extra_commands


def _load_single_plugin(
    plugin_path: Path, module_name: str
) -> Tuple[List[Any], List[Any]]:
    """
    加载单个插件文件并提取 tools / commands。

    内部函数，异常由调用者（load_plugins）统一捕获。
    """
    # 如果该模块已被加载过（例如 reload_plugins 场景），先移除缓存
    if module_name in sys.modules:
        del sys.modules[module_name]

    # 动态加载模块
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 '{plugin_path}' 创建模块 spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # 注册后再执行，支持插件内部相对引用
    spec.loader.exec_module(module)    # type: ignore[union-attr]

    # 提取 tools
    tools: List[Any] = []
    if hasattr(module, "get_tools") and callable(module.get_tools):
        result = module.get_tools()
        if isinstance(result, list):
            tools = result
        else:
            print(
                f"[plugins] ⚠️  插件 '{plugin_path.name}' 的 get_tools() "
                f"未返回列表，已忽略（返回类型：{type(result).__name__}）"
            )

    # 提取 commands
    commands: List[Any] = []
    if hasattr(module, "get_commands") and callable(module.get_commands):
        result = module.get_commands()
        if isinstance(result, list):
            commands = result
        else:
            print(
                f"[plugins] ⚠️  插件 '{plugin_path.name}' 的 get_commands() "
                f"未返回列表，已忽略（返回类型：{type(result).__name__}）"
            )

    loaded_info = []
    if tools:
        loaded_info.append(f"{len(tools)} 个工具")
    if commands:
        loaded_info.append(f"{len(commands)} 个命令")
    summary = "、".join(loaded_info) if loaded_info else "（无导出）"
    print(f"[plugins] 已加载插件 '{plugin_path.name}'：{summary}")

    return tools, commands


# ──────────────────────────────────────────────
# 简单自测（python -m ... 直接运行时）
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    import os

    print("=== Plugin 系统自测 ===")

    # 创建临时插件目录并写入测试插件
    with tempfile.TemporaryDirectory() as tmpdir:
        # 临时替换插件目录（仅用于测试）
        import mira.services.plugins as _self
        original_dir = _self.PLUGINS_DIR
        _self.PLUGINS_DIR = Path(tmpdir)

        # 写一个合法插件
        good_plugin = Path(tmpdir) / "good_plugin.py"
        good_plugin.write_text(
            "def get_tools():\n    return ['fake_tool']\n"
            "def get_commands():\n    return ['fake_cmd']\n",
            encoding="utf-8",
        )

        # 写一个有语法错误的插件
        bad_plugin = Path(tmpdir) / "bad_plugin.py"
        bad_plugin.write_text("def broken(:\n    pass\n", encoding="utf-8")

        tools, commands = load_plugins()
        print(f"\n加载结果：tools={tools}, commands={commands}")

        # 恢复
        _self.PLUGINS_DIR = original_dir

    print("\n=== 目录不存在时 ===")
    import mira.services.plugins as _self2
    original_dir = _self2.PLUGINS_DIR
    _self2.PLUGINS_DIR = Path("/nonexistent/path/mira/plugins")
    t, c = load_plugins()
    print(f"tools={t}, commands={c}")
    _self2.PLUGINS_DIR = original_dir
