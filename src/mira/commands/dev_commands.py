#!/usr/bin/env python3
"""
开发类命令 - /compact /model /doctor /init /memory /version /todo /diff /context
"""

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mira.commands.base import Command

if TYPE_CHECKING:
    from mira.query import QueryEngine


class VersionCommand(Command):
    """显示版本信息"""

    @property
    def name(self) -> str:
        return "version"

    @property
    def description(self) -> str:
        return "显示 Mira 的版本信息"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira import __version__
        print(f"Mira v{__version__}")
        print(f"Provider : {engine.provider}")
        print(f"Model    : {engine.model}")
        print(f"Python   : {sys.version.split()[0]}")
        print(f"CWD      : {os.getcwd()}")


class ModelCommand(Command):
    """切换 AI 模型或提供商"""

    @property
    def name(self) -> str:
        return "model"

    @property
    def description(self) -> str:
        return "切换模型。用法: /model [provider] [model_name]  示例: /model deepseek deepseek-reasoner"

    def execute(self, command: str, engine: "QueryEngine"):
        parts = command.strip().split()
        # /model
        if len(parts) == 1:
            self._show_models(engine)
            return
        # /model <provider>
        if len(parts) == 2:
            provider = parts[1]
            self._switch_provider(engine, provider, None)
            return
        # /model <provider> <model>
        provider = parts[1]
        model = parts[2]
        self._switch_provider(engine, provider, model)

    def _show_models(self, engine):
        from mira.utils.config import get_providers, get_models
        print("可用的提供商和模型:\n")
        for p in get_providers(engine.config):
            pid = p["id"]
            models = get_models(pid, engine.config)
            current = "◀ 当前" if pid == engine.provider else ""
            print(f"  {pid} ({p['name']}) {current}")
            for m in models[:5]:
                marker = "  ✓" if m == engine.model and pid == engine.provider else "   "
                print(f"   {marker} {m}")
        print("\n用法: /model <provider> [model_name]")

    def _switch_provider(self, engine, provider: str, model: str):
        from mira.utils.config import get_api_key, get_default_model, get_provider_base_url, PROVIDER_DEFAULTS
        from mira.services.api import create_api_client

        if provider not in PROVIDER_DEFAULTS and provider not in engine.config.get("custom_providers", {}):
            print(f"错误：未知提供商 '{provider}'")
            print(f"支持的提供商: {', '.join(PROVIDER_DEFAULTS.keys())}")
            return

        api_key = get_api_key(provider, engine.config)
        if not api_key:
            print(f"错误：未配置 {provider} 的 API 密钥")
            print(f"请在设置中添加密钥，或设置环境变量")
            return

        model = model or get_default_model(provider, engine.config)
        try:
            engine.api_client = create_api_client(provider, {
                "api_key": api_key,
                "model": model,
                "temperature": engine.config.get("temperature", 0.7),
                "base_url": get_provider_base_url(provider, engine.config),
            })
            engine.provider = provider
            engine.model = model
            # 持久化：下次启动自动使用此提供商和模型
            from mira.utils.config import save_config
            engine.config["default_provider"] = provider
            engine.config.setdefault("provider_selected_models", {})[provider] = model
            save_config(engine.config)
            print(f"✓ 已切换到 {provider} / {model}（已保存为默认）")
        except Exception as e:
            print(f"错误：切换失败 - {e}")


class CompactCommand(Command):
    """压缩对话历史以节省 token"""

    @property
    def name(self) -> str:
        return "compact"

    @property
    def description(self) -> str:
        return "将当前对话历史压缩为摘要，释放 token 空间（保留上下文）"

    def execute(self, command: str, engine: "QueryEngine"):
        parts = command.strip().split()
        # /compact snip → 快速裁剪（删除旧工具结果消息，无需 AI）
        if len(parts) > 1 and parts[1] == "snip":
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(engine._snip_history())
                else:
                    loop.run_until_complete(engine._snip_history())
            except RuntimeError:
                asyncio.run(engine._snip_history())
            return

        messages = engine.app_state.messages
        if len(messages) < 4:
            print("对话历史较短，无需压缩")
            return

        # 保留最新的 2 条消息，其余生成摘要
        history_to_summarize = messages[:-2]
        msg_count = len(history_to_summarize)

        # 构建摘要 prompt
        summary_text = "\n".join(
            f"[{m.get('role', 'unknown')}]: {str(m.get('content', ''))[:200]}"
            for m in history_to_summarize
        )
        summary_prompt = (
            f"请将以下对话历史浓缩为一段简洁的摘要，保留关键信息和上下文：\n\n{summary_text}"
        )

        print(f"正在压缩 {msg_count} 条对话历史...")
        import asyncio

        async def do_compact():
            import sys
            summary_parts = []
            msgs = [{"role": "user", "content": summary_prompt}]
            async for event in engine.api_client.stream_message(msgs, [], "你是一个对话摘要助手"):
                if event.get("type") == "content_block_delta":
                    text = event.get("text", "")
                    summary_parts.append(text)
                    sys.stdout.write(text)
                    sys.stdout.flush()
            return "".join(summary_parts)

        try:
            summary = asyncio.get_event_loop().run_until_complete(do_compact())
        except RuntimeError:
            summary = asyncio.run(do_compact())

        # 替换历史为摘要
        kept = messages[-2:]
        engine.app_state.clear_messages()
        engine.app_state.add_message({
            "role": "user",
            "content": f"[对话摘要] {summary}",
        })
        for m in kept:
            engine.app_state.add_message(m)

        print(f"\n✓ 已压缩 {msg_count} 条历史为摘要，保留最近 2 条消息")


class ContextCommand(Command):
    """显示当前上下文信息"""

    @property
    def name(self) -> str:
        return "context"

    @property
    def description(self) -> str:
        return "显示当前上下文：消息数量、token 估算、工具列表、工作目录等"

    def execute(self, command: str, engine: "QueryEngine"):
        messages = engine.app_state.messages
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        estimated_tokens = total_chars // 4  # 粗估

        print("─" * 50)
        print(f"  提供商   : {engine.provider}")
        print(f"  模型     : {engine.model}")
        print(f"  工作目录 : {os.getcwd()}")
        print(f"  消息条数 : {len(messages)}")
        print(f"  估算字符 : {total_chars:,}")
        print(f"  估算Token: ~{estimated_tokens:,}")
        print(f"  工具数量 : {len(engine.tools)}")
        print(f"  命令数量 : {len(engine.commands)}")
        print("─" * 50)
        print("工具列表:")
        for t in engine.tools:
            print(f"  • {t.name}")


class DoctorCommand(Command):
    """检查环境和配置健康状态"""

    @property
    def name(self) -> str:
        return "doctor"

    @property
    def description(self) -> str:
        return "检查 API Key 配置、依赖包和网络连接状态"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira.utils.config import PROVIDER_DEFAULTS, get_api_key
        print("Mira 健康检查\n")

        # 检查 API Keys
        print("API 密钥状态:")
        for pid, pdef in PROVIDER_DEFAULTS.items():
            key = get_api_key(pid, engine.config)
            if key:
                masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
                print(f"  ✓ {pid:<12} {masked}")
            else:
                print(f"  ✗ {pid:<12} 未配置")

        # 检查可选依赖
        print("\n可选依赖:")
        optional_deps = [
            ("PyPDF2", "PDF 文件读取"),
            ("fastapi", "Web UI 服务器"),
            ("uvicorn", "Web UI 服务器"),
            ("websockets", "WebSocket 支持"),
        ]
        for pkg, desc in optional_deps:
            try:
                __import__(pkg)
                print(f"  ✓ {pkg:<15} {desc}")
            except ImportError:
                print(f"  ✗ {pkg:<15} {desc} (pip install {pkg})")

        # 检查 Git
        print("\nGit:")
        import subprocess
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True)
            print(f"  ✓ {result.stdout.strip()}")
        except FileNotFoundError:
            print("  ✗ 未安装 Git")

        print(f"\n当前提供商: {engine.provider} / {engine.model}")
        print("健康检查完成")


class InitCommand(Command):
    """初始化项目笔记文件 NOTES.md"""

    @property
    def name(self) -> str:
        return "init"

    @property
    def description(self) -> str:
        return "在当前目录创建 NOTES.md 项目笔记文件"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira.utils.memory import init_notes, get_notes_path

        existing = get_notes_path()
        if existing and existing.parent == Path.cwd():
            print(f"NOTES.md 已存在: {existing}")
            ans = input("是否覆盖? [y/N] ").strip().lower()
            if ans != "y":
                print("已取消")
                return

        parts = command.strip().split(None, 2)
        project_name = parts[1] if len(parts) > 1 else Path.cwd().name
        description = parts[2] if len(parts) > 2 else ""

        path = init_notes(project_name, description)
        print(f"✓ 已创建 {path}")
        print("  可在此文件中记录项目约定、偏好设置和重要上下文")


class MemoryCommand(Command):
    """管理 NOTES.md 项目笔记文件"""

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "查看/编辑项目笔记 NOTES.md。用法: /memory [show|edit|add <内容>]"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira.utils.memory import load_notes, append_note, get_notes_path

        parts = command.strip().split(None, 2)
        sub = parts[1] if len(parts) > 1 else "show"

        if sub == "show":
            content = load_notes()
            path = get_notes_path()
            if not content:
                print("未找到 NOTES.md 项目笔记文件")
                print("运行 /init 创建一个")
            else:
                print(f"笔记文件: {path}\n{'─'*50}")
                print(content)

        elif sub == "add":
            text = parts[2] if len(parts) > 2 else ""
            if not text:
                print("用法: /memory add <要记录的内容>")
                return
            append_note(text)
            print("✓ 已记录到项目笔记")

        elif sub == "edit":
            path = get_notes_path()
            if not path:
                print("未找到 NOTES.md，运行 /init 创建一个")
                return
            editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "nano")
            os.system(f"{editor} {path}")

        else:
            print("用法: /memory [show|edit|add <内容>]")


class DiffCommand(Command):
    """显示文件差异"""

    @property
    def name(self) -> str:
        return "diff"

    @property
    def description(self) -> str:
        return "显示 Git 工作区差异，或比较两个文件。用法: /diff [文件路径] 或 /diff <文件A> <文件B>"

    def execute(self, command: str, engine: "QueryEngine"):
        parts = command.strip().split()

        if len(parts) == 1:
            # git diff
            from mira.tools.git_tools import GitDiffTool
            result = GitDiffTool().execute({})
            print(result)
        elif len(parts) == 2:
            # git diff <file>
            from mira.tools.git_tools import GitDiffTool
            result = GitDiffTool().execute({"file": parts[1]})
            print(result)
        elif len(parts) == 3:
            # diff <file_a> <file_b>
            from mira.tools.file_tools import DiffTool
            result = DiffTool().execute({"path_a": parts[1], "path_b": parts[2]})
            print(result)
        else:
            print("用法: /diff [文件路径] 或 /diff <文件A> <文件B>")


class TodoCommand(Command):
    """管理任务列表"""

    @property
    def name(self) -> str:
        return "todo"

    @property
    def description(self) -> str:
        return "管理任务列表。用法: /todo [list|add <内容>|done <id>|del <id>]"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira.tools.todo_tools import TodoWriteTool
        tool = TodoWriteTool()
        parts = command.strip().split(None, 2)
        sub = parts[1] if len(parts) > 1 else "list"

        if sub == "list":
            print(tool.execute({"action": "list"}))
        elif sub == "add":
            content = parts[2] if len(parts) > 2 else ""
            if not content:
                print("用法: /todo add <任务内容>")
                return
            print(tool.execute({"action": "create", "content": content}))
        elif sub == "done":
            tid = parts[2] if len(parts) > 2 else ""
            if not tid:
                print("用法: /todo done <任务ID>")
                return
            print(tool.execute({"action": "update", "id": tid, "status": "completed"}))
        elif sub == "del":
            tid = parts[2] if len(parts) > 2 else ""
            if not tid:
                print("用法: /todo del <任务ID>")
                return
            print(tool.execute({"action": "delete", "id": tid}))
        else:
            print("用法: /todo [list|add <内容>|done <id>|del <id>]")


class StatusCommand(Command):
    """显示当前会话完整状态"""

    @property
    def name(self) -> str:
        return "status"

    @property
    def description(self) -> str:
        return "显示当前会话状态：模型、上下文用量、费用、工具数等"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira.utils.context import get_context_usage, format_context_bar, get_context_window
        from mira.utils.sessions import list_sessions
        import datetime

        messages = engine.app_state.messages
        ctx = get_context_usage(messages, engine.model)
        cost = engine.cost_tracker.total_usd
        user_msgs = len([m for m in messages if m.get("role") == "user"])
        sessions = list_sessions(5)

        bar = format_context_bar(ctx["ratio"])
        warn = " ⚠ 建议 /compact" if ctx["warning"] else ""

        print("─" * 56)
        print(f"  {'会话 ID':<10} {engine.app_state.session_id}")
        print(f"  {'提供商':<10} {engine.provider}")
        print(f"  {'模型':<10} {engine.model}")
        print(f"  {'工作目录':<10} {os.getcwd()}")
        print(f"  {'时间':<10} {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("─" * 56)
        print(f"  {'消息条数':<10} {len(messages)}（用户 {user_msgs} 条）")
        print(f"  {'上下文':<10} {ctx['used']:,} / {ctx['window']:,} tokens")
        print(f"  {'用量':<10} {bar}{warn}")
        if cost > 0:
            cost_str = f"${cost:.5f}" if cost < 0.01 else f"${cost:.4f}"
            print(f"  {'费用':<10} {cost_str}")
        print(f"  {'工具数':<10} {len(engine.tools)}")
        print(f"  {'命令数':<10} {len(engine.commands)}")
        print("─" * 56)
        if sessions:
            print(f"  最近会话 (共 {len(list_sessions())} 条):")
            for s in sessions[:3]:
                upd = s.get("updated_at", "")[:16].replace("T", " ")
                print(f"    [{s['session_id']}] {upd}  {s['title'][:30]}")


class CostCommand(Command):
    """显示当前会话的 API 费用明细"""

    @property
    def name(self) -> str:
        return "cost"

    @property
    def description(self) -> str:
        return "显示当前会话的 API token 用量和费用明细"

    def execute(self, command: str, engine: "QueryEngine"):
        parts = command.strip().split()
        sub = parts[1] if len(parts) > 1 else "show"

        if sub == "reset":
            engine.cost_tracker.reset()
            print("✓ 已重置费用统计")
            return

        print("─" * 50)
        print("  当前会话 API 费用")
        print("─" * 50)
        print(engine.cost_tracker.format_display())
        print("─" * 50)
        print("  /cost reset  重置统计")


class CommitCommand(Command):
    """智能 Git 提交：生成 Conventional Commits 消息"""

    @property
    def name(self) -> str:
        return "commit"

    @property
    def description(self) -> str:
        return "智能 Git 提交：AI 分析 diff 并生成规范的提交消息，然后执行 git commit"

    def execute(self, command: str, engine: "QueryEngine"):
        import asyncio
        from mira.services.skills import get_skill

        skill = get_skill("commit")
        if not skill:
            print("✗ 未找到 commit skill")
            return

        async def run():
            await engine.process_message(skill["prompt"])

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                print("提示：/commit 在异步环境中需要在主交互循环中运行")
                return
            loop.run_until_complete(run())
        except RuntimeError:
            asyncio.run(run())


class AddDirCommand(Command):
    """添加额外允许访问的目录"""

    @property
    def name(self) -> str:
        return "add-dir"

    @property
    def description(self) -> str:
        return "添加额外允许 AI 访问的目录。用法: /add-dir <路径>"

    def execute(self, command: str, engine: "QueryEngine"):
        parts = command.strip().split(None, 1)
        if len(parts) < 2:
            print("当前额外目录:")
            if engine._extra_dirs:
                for d in engine._extra_dirs:
                    print(f"  • {d}")
            else:
                print("  （无）")
            print("\n用法: /add-dir <路径>")
            return

        path = parts[1].strip()
        abs_path = os.path.abspath(path)
        if not os.path.isdir(abs_path):
            print(f"✗ 目录不存在: {abs_path}")
            return
        if abs_path not in engine._extra_dirs:
            engine._extra_dirs.append(abs_path)
            # 持久化到配置文件
            from mira.utils.config import load_config, save_config
            cfg = load_config()
            cfg.setdefault("extra_dirs", [])
            if abs_path not in cfg["extra_dirs"]:
                cfg["extra_dirs"].append(abs_path)
                save_config(cfg)
            print(f"✓ 已添加: {abs_path}")


class PluginCommand(Command):
    """管理 Mira 插件"""

    @property
    def name(self) -> str:
        return "plugin"

    @property
    def description(self) -> str:
        return "管理插件。用法: /plugin list | /plugin reload | /plugin dir"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira.services.plugins import PLUGINS_DIR, load_plugins
        parts = command.strip().split()
        sub = parts[1] if len(parts) > 1 else "list"

        if sub == "dir":
            print(f"插件目录: {PLUGINS_DIR}")
            print(f"  存在: {'是' if PLUGINS_DIR.is_dir() else '否（尚未创建）'}")
            if PLUGINS_DIR.is_dir():
                files = list(PLUGINS_DIR.glob("*.py"))
                print(f"  文件数: {len(files)}")
            return

        if sub == "reload":
            print("重新加载所有插件…")
            extra_tools, extra_cmds = load_plugins()
            # 合并到 engine（移除旧插件工具，添加新的）
            engine.tools = [t for t in engine.tools if not getattr(t, "_from_plugin", False)]
            for t in extra_tools:
                t._from_plugin = True
                engine.tools.append(t)
            print(f"✓ 加载了 {len(extra_tools)} 个工具，{len(extra_cmds)} 个命令")
            return

        # 默认: list
        if not PLUGINS_DIR.is_dir() or not list(PLUGINS_DIR.glob("*.py")):
            print(f"暂无插件。将 .py 文件放入以下目录即可加载：\n  {PLUGINS_DIR}")
            return
        plugin_files = list(PLUGINS_DIR.glob("*.py"))
        print(f"\n已安装插件 ({len(plugin_files)}):")
        for pf in plugin_files:
            print(f"  • {pf.name}")
        print(f"\n插件目录: {PLUGINS_DIR}")
        print("用法: /plugin reload  重新加载插件")


class PlanCommand(Command):
    """计划模式 - 让 AI 先规划后执行"""

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return "切换计划模式。开启时 AI 工具调用只描述不执行，关闭后恢复正常执行。"

    def execute(self, command: str, engine: "QueryEngine"):
        parts = command.strip().split()
        sub = parts[1] if len(parts) > 1 else "toggle"

        if sub == "on":
            engine._plan_mode = True
            print("✓ 计划模式已开启 — 工具只描述，不真正执行")
            print("  输入 /plan off 恢复正常执行")
        elif sub == "off":
            engine._plan_mode = False
            print("✓ 计划模式已关闭 — 恢复正常工具执行")
        else:
            # toggle
            engine._plan_mode = not engine._plan_mode
            state = "开启" if engine._plan_mode else "关闭"
            print(f"✓ 计划模式已{state}")
            if engine._plan_mode:
                print("  工具调用将只显示描述，不会实际执行")
                print("  输入 /plan off 或让 AI 调用 ExitPlanMode 恢复执行")


class TaskCommand(Command):
    """/task — 查看后台子任务状态"""

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return "查看后台子任务。用法: /task [list|get <id>|output <id>|stop <id>]"

    def execute(self, command: str, engine: "QueryEngine"):
        from mira.tools.task_tools import list_tasks, get_task

        parts = command.strip().split()
        sub = parts[1] if len(parts) > 1 else "list"

        if sub == "list":
            tasks = list_tasks()
            if not tasks:
                print("暂无子任务")
                return
            icons = {
                "pending": "⏳", "running": "🔄",
                "completed": "✅", "failed": "❌", "cancelled": "⊘",
            }
            print(f"\n子任务列表（共 {len(tasks)} 个）:")
            for t in tasks:
                icon = icons.get(t.status, "?")
                print(f"  {icon} [{t.task_id}] {t.title}  ({t.status})  输出: {len(t.output)} 字符")

        elif sub == "get":
            tid = parts[2] if len(parts) > 2 else ""
            if not tid:
                print("用法: /task get <任务ID>")
                return
            task = get_task(tid)
            if not task:
                print(f"未找到任务 '{tid}'")
                return
            print(f"  ID:     {task.task_id}")
            print(f"  标题:   {task.title}")
            print(f"  状态:   {task.status}")
            print(f"  提示:   {task.prompt[:100]}")
            print(f"  输出:   {len(task.output)} 字符")
            print(f"  创建:   {task.created_at}")

        elif sub == "output":
            tid = parts[2] if len(parts) > 2 else ""
            if not tid:
                print("用法: /task output <任务ID>")
                return
            task = get_task(tid)
            if not task:
                print(f"未找到任务 '{tid}'")
                return
            output = task.output
            if not output:
                print(f"任务 '{tid}' 暂无输出（状态: {task.status}）")
            else:
                # 显示末尾 3000 字符
                if len(output) > 3000:
                    print(f"…（省略前 {len(output)-3000} 字符）")
                    print(output[-3000:])
                else:
                    print(output)

        elif sub == "stop":
            tid = parts[2] if len(parts) > 2 else ""
            if not tid:
                print("用法: /task stop <任务ID>")
                return
            task = get_task(tid)
            if not task:
                print(f"未找到任务 '{tid}'")
                return
            if task._async_task and not task._async_task.done():
                task._async_task.cancel()
                print(f"✓ 已发送取消信号给任务 [{tid}]")
            else:
                task.status = "cancelled"
                print(f"✓ 任务 [{tid}] 已标记为已取消")
        else:
            print("用法: /task [list|get <id>|output <id>|stop <id>]")


class UndoCommand(Command):
    """撤销上一轮 AI 操作（恢复被修改的文件）"""

    @property
    def name(self) -> str:
        return "undo"

    @property
    def description(self) -> str:
        return "撤销上一轮 AI 对文件的修改，恢复所有被改动的文件到改动前状态"

    def execute(self, command: str, engine: "QueryEngine"):
        if not engine._undo_stack:
            print("没有可撤销的操作")
            return

        changes = engine._undo_stack.pop()
        if not changes:
            print("没有可撤销的文件变更")
            return

        restored = 0
        for path, old_content in changes:
            try:
                if old_content is None:
                    # 文件原本不存在，删除它
                    if os.path.exists(path):
                        os.remove(path)
                        print(f"  已删除: {path}")
                else:
                    # 写回原内容
                    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(old_content)
                    print(f"  已还原: {path}")
                restored += 1
            except Exception as e:
                print(f"  还原失败 {path}: {e}")

        # 删除最后一轮 AI 的消息（最后一个 user 消息之后的所有 assistant 消息）
        messages = engine.app_state.messages
        # 找到最后一个 user 消息的索引
        last_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                last_user_idx = i
                break
        if last_user_idx >= 0:
            # 删除该 user 消息之后的所有消息（包括 assistant 和 tool_result）
            del messages[last_user_idx:]

        print(f"✓ 已撤销上一轮操作，还原了 {restored} 个文件")


class ExportCommand(Command):
    """导出对话为 Markdown 文件"""

    @property
    def name(self) -> str:
        return "export"

    @property
    def description(self) -> str:
        return "将当前对话导出为 Markdown 文件。用法: /export [文件名]"

    def execute(self, command: str, engine: "QueryEngine"):
        import datetime
        parts = command.strip().split(None, 1)
        if len(parts) > 1:
            filename = parts[1].strip()
        else:
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"mira-chat-{ts}.md"

        messages = engine.app_state.messages
        if not messages:
            print("当前对话为空，无内容可导出")
            return

        lines = [f"# Mira 对话导出\n"]
        lines.append(f"> 导出时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"> 提供商: {engine.provider} / {engine.model}\n\n")

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                lines.append(f"### 用户\n\n{content}\n\n")
            elif role == "assistant":
                # 跳过只有工具调用、没有文本内容的消息
                tool_calls = msg.get("tool_calls", [])
                if content:
                    lines.append(f"### Mira\n\n{content}\n\n")
                elif tool_calls:
                    # 只有工具调用，跳过
                    continue
            elif role == "tool_result":
                # 工具结果跳过
                continue

        md_content = "".join(lines)
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(md_content)
            print(f"✓ 已导出到: {os.path.abspath(filename)}")
        except Exception as e:
            print(f"✗ 导出失败: {e}")
