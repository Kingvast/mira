#!/usr/bin/env python3
"""
查询引擎 - 正确的 Agentic Loop 实现
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from typing import List, Dict, Any, Optional, Callable, AsyncGenerator

from mira.state.app_state import AppState
from mira.services.api import create_api_client
from mira.utils.config import (
    get_api_key, get_default_model, get_models, get_provider_base_url, load_config,
)
from mira.utils.memory import load_memory
from mira.utils.permissions import needs_confirm, check_permission_sync
from mira.utils.context import (
    get_context_window, get_context_usage, should_compact,
    estimate_messages_tokens, format_context_bar,
)
from mira.utils.cost import CostTracker


# ─── ANSI 颜色工具 ─────────────────────────────────────────────────────────────

def _supports_color() -> bool:
    """检测终端是否支持 ANSI 颜色"""
    if os.environ.get("NO_COLOR"):
        return False
    if sys.platform == "win32":
        # Windows 10+ 支持 ANSI（通过 ENABLE_VIRTUAL_TERMINAL_PROCESSING）
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

def _bold(s):    return _c("1", s)
def _dim(s):     return _c("2", s)
def _red(s):     return _c("31", s)
def _green(s):   return _c("32", s)
def _yellow(s):  return _c("33", s)
def _blue(s):    return _c("34", s)
def _cyan(s):    return _c("36", s)
def _magenta(s): return _c("35", s)
def _gray(s):    return _c("90", s)


# ─── Spinner ──────────────────────────────────────────────────────────────────

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_spinner_active = False


async def _run_spinner(label: str = "AI 思考中"):
    """在终端显示旋转指示器，直到被取消"""
    global _spinner_active
    _spinner_active = True
    i = 0
    try:
        while True:
            frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)] if _COLOR else "·"
            # 使用回车覆盖当前行（\r 而非换行）
            sys.stdout.write(f"\r  {_cyan(frame)} {_dim(label)}   ")
            sys.stdout.flush()
            i += 1
            await asyncio.sleep(0.08)
    except asyncio.CancelledError:
        # 清除 spinner 行
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()
        _spinner_active = False


# ─── 默认 CLI 回调（输出到 stdout）─────────────────────────────────────────────

_in_tool_block = False   # 追踪工具块状态，决定是否换行
_tool_start_time: float = 0.0  # 记录工具开始时间


async def _cli_callback(event: Dict):
    global _in_tool_block, _tool_start_time
    t = event.get("type")

    if t == "text":
        content = event.get("content", "")
        if content:
            if _in_tool_block:
                sys.stdout.write("\n")
                _in_tool_block = False
            sys.stdout.write(content)
            sys.stdout.flush()

    elif t == "tool_start":
        name = event.get("name", "")
        args = event.get("args", {})
        key_args = _format_tool_args(name, args)
        _tool_start_time = time.monotonic()
        # 工具名用青色加粗，参数用暗灰色，整体缩进显示
        sys.stdout.write(f"\n  {_gray('┌─')} {_cyan(_bold(name))}")
        if key_args:
            sys.stdout.write(f"  {_gray(key_args)}")
        sys.stdout.write("\n")
        sys.stdout.flush()
        _in_tool_block = True

    elif t == "tool_stream":
        # 实时输出流（BashTool 流式输出）
        text = event.get("text", "")
        if text:
            for line in text.splitlines(keepends=True):
                sys.stdout.write(f"  {_gray('│')} {_dim(line.rstrip())}\n" if line.strip() else "")
            sys.stdout.flush()

    elif t == "tool_result":
        content = str(event.get("content", ""))
        elapsed = time.monotonic() - _tool_start_time
        size = len(content)
        # 首行预览（去除多余空白，截断至 90 字符）
        first_line = content.strip().split("\n")[0][:90]
        if len(content.strip()) > len(first_line):
            first_line += " …"
        size_str = f"{size:,}字符" if size > 0 else "空"
        time_str = f"{elapsed*1000:.0f}ms" if elapsed < 1 else f"{elapsed:.1f}s"
        sys.stdout.write(
            f"  {_gray('└─')} {_green('✓')} {_dim(size_str)}"
            + (f"  {_dim(time_str)}" if elapsed > 0.05 else "")
            + (f"\n     {_gray(first_line)}" if first_line else "")
            + "\n"
        )
        sys.stdout.flush()

    elif t == "tool_error":
        content = str(event.get("content", ""))
        sys.stdout.write(f"  {_gray('└─')} {_red('✗')} {_red(content[:160])}\n")
        sys.stdout.flush()

    elif t == "tool_denied":
        content = str(event.get("content", ""))
        sys.stdout.write(f"  {_gray('└─')} {_yellow('⊘')} {_yellow(content[:120])}\n")
        sys.stdout.flush()

    elif t == "done":
        if not _in_tool_block:
            sys.stdout.write("\n")
        sys.stdout.flush()
        _in_tool_block = False

    elif t == "error":
        msg = event.get("message", "")
        sys.stdout.write(f"\n  {_red('●')} {_red(_bold('错误'))}: {msg}\n")
        sys.stdout.flush()
        _in_tool_block = False

    elif t == "warning":
        msg = event.get("message", "")
        sys.stdout.write(f"\n  {_yellow('⚠')} {_yellow(msg)}\n")
        sys.stdout.flush()

    elif t == "info":
        msg = event.get("message", "")
        sys.stdout.write(f"\n  {_cyan('ℹ')} {_dim(msg)}\n")
        sys.stdout.flush()

    elif t == "thinking":
        content = event.get("content", "")
        if content:
            preview = content.strip()[:200].replace("\n", " ")
            if len(content.strip()) > 200:
                preview += "…"
            sys.stdout.write(f"\n  {_dim('⟨思考⟩')} {_gray(preview)}\n")
            sys.stdout.flush()

    elif t == "usage":
        # 静默消费，CLI 不显示每次 token 计数
        pass

    elif t == "iteration":
        # 多步任务的迭代进度提示
        n = event.get("n", 0)
        if n > 1:  # 第1步不显示，避免干扰正常单步任务
            sys.stdout.write(f"\n  {_gray(f'── 步骤 {n} ──')}\n")
            sys.stdout.flush()


def _format_tool_args(name: str, args: dict) -> str:
    """将工具参数格式化为简短的单行字符串"""
    if not args:
        return ""
    # 优先展示最重要的参数
    priority = {
        "BashTool": ["command"],
        "PowerShellTool": ["command"],
        "FileReadTool": ["path"],
        "FileWriteTool": ["path"],
        "FileEditTool": ["path"],
        "FileAppendTool": ["path"],
        "GlobTool": ["pattern", "directory"],
        "GrepTool": ["pattern", "path"],
        "LSTool": ["path"],
        "WebSearchTool": ["query"],
        "WebFetchTool": ["url"],
        "GitStatusTool": [],
        "GitDiffTool": ["path"],
        "GitLogTool": [],
        "GitCommitTool": ["message"],
        "GitAddTool": ["files"],
        "GitPushTool": ["branch"],
    }
    keys = priority.get(name, list(args.keys())[:2])
    parts = []
    for k in keys:
        if k in args:
            v = args[k]
            if isinstance(v, list):
                v = " ".join(str(x) for x in v[:3])
            v = str(v).replace("\n", "↵")
            if len(v) > 60:
                v = v[:57] + "…"
            parts.append(f"{_dim(k+'=')+v}" if len(keys) > 1 else v)
    return " ".join(parts)


# ─── 消息归一化 ────────────────────────────────────────────────────────────────

def _build_vision_content(text: str, images: List[Dict], provider: str) -> Any:
    """构建包含图片的多模态 content 字段"""
    is_openai = provider in ("openai", "deepseek", "zhipu", "moonshot", "doubao", "minimax", "longcat")
    blocks = []
    for img in images:
        media_type = img.get("media_type", "image/png")
        b64_data = img.get("data", "")
        if is_openai:
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{b64_data}"},
            })
        else:
            # Anthropic 格式
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64_data},
            })
    if text:
        if is_openai:
            blocks.append({"type": "text", "text": text})
        else:
            blocks.append({"type": "text", "text": text})
    return blocks if blocks else text


def normalize_messages_for_api(messages: List[Dict], provider: str) -> List[Dict]:
    """将内部消息格式转换为 API 所需格式"""
    result = []
    for msg in messages:
        role = msg.get("role", "user")

        if role == "user":
            content = msg.get("content", "")
            images = msg.get("images", [])  # [{media_type, data}]
            if images:
                content = _build_vision_content(content, images, provider)
            result.append({"role": "user", "content": content})

        elif role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                if msg.get("content"):
                    result.append({"role": "assistant", "content": msg["content"]})
            else:
                if provider in ("openai", "deepseek", "zhipu", "moonshot", "doubao", "minimax", "longcat"):
                    # OpenAI 格式
                    result.append({
                        "role": "assistant",
                        "content": msg.get("content") or None,
                        "tool_calls": [
                            {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                                },
                            }
                            for tc in tool_calls
                        ],
                    })
                else:
                    # Anthropic 格式
                    content_blocks = []
                    if msg.get("content"):
                        content_blocks.append({"type": "text", "text": msg["content"]})
                    for tc in tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "input": tc.get("args", {}),
                        })
                    result.append({"role": "assistant", "content": content_blocks})

        elif role == "tool_result":
            tool_results = msg.get("tool_results", [])
            if provider in ("openai", "deepseek", "zhipu", "moonshot", "doubao", "minimax", "longcat"):
                for tr in tool_results:
                    result.append({
                        "role": "tool",
                        "tool_call_id": tr.get("tool_call_id", ""),
                        "content": tr.get("content", ""),
                    })
            else:
                # Anthropic: 将所有 tool_result 合并为一个 user 消息
                result.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tr.get("tool_call_id", ""),
                            "content": tr.get("content", ""),
                        }
                        for tr in tool_results
                    ],
                })

    return result


# ─── 事件解析 ─────────────────────────────────────────────────────────────────

def _parse_stream_event(event: Dict, tc_buffer: Dict) -> tuple:
    """
    解析流式事件，返回 (text, completed_tool_calls)
    tc_buffer 用于累积 OpenAI 流式 tool call 参数
    """
    text = ""
    completed_tcs = []

    # ── OpenAI 风格 ───────────────────────────────────────────
    if "choices" in event:
        choice = event["choices"][0]
        delta = choice.get("delta", {})

        # 文本内容
        if delta.get("content"):
            text = delta["content"]

        # 工具调用（流式，需要累积）
        for tc in delta.get("tool_calls", []):
            idx = tc.get("index", 0)
            if idx not in tc_buffer:
                tc_buffer[idx] = {"id": "", "name": "", "args_str": ""}
            if tc.get("id"):
                tc_buffer[idx]["id"] = tc["id"]
            func = tc.get("function", {})
            if func.get("name"):
                tc_buffer[idx]["name"] = func["name"]
            if func.get("arguments"):
                tc_buffer[idx]["args_str"] += func["arguments"]

        # 结束原因
        finish = choice.get("finish_reason")
        if finish in ("tool_calls", "stop") and tc_buffer:
            for idx in sorted(tc_buffer.keys()):
                tc = tc_buffer[idx]
                try:
                    args = json.loads(tc["args_str"]) if tc["args_str"] else {}
                except json.JSONDecodeError:
                    args = {}
                completed_tcs.append({"id": tc["id"], "name": tc["name"], "args": args})
            tc_buffer.clear()

    # ── 自定义 / Anthropic 风格 ───────────────────────────────
    else:
        etype = event.get("type")
        if etype == "content_block_delta":
            text = event.get("text", "")
        elif etype == "tool_use":
            tu = event.get("tool_use", {})
            completed_tcs.append({
                "id": tu.get("id", ""),
                "name": tu.get("name", ""),
                "args": tu.get("args", tu.get("input", {})),
            })

    return text, completed_tcs


# ─── 查询引擎 ────────────────────────────────────────────────────────────────

class QueryEngine:
    """AI 代码助手查询引擎（Agentic Loop）"""

    def __init__(self, config: dict, provider: str = None, model: str = None,
                 skip_permissions: bool = False, confirm_fn=None):
        self.config = config
        self.provider = provider or config.get("default_provider", "deepseek")
        self.skip_permissions = skip_permissions or config.get("dangerously_skip_permissions", False)
        # confirm_fn: async callable(tool_name, args, prompt) -> bool
        # None = CLI sync fallback
        self._confirm_fn = confirm_fn

        api_key = get_api_key(self.provider, config)
        if not api_key:
            raise ValueError(f"未找到 {self.provider} 的 API 密钥，请在配置中设置")

        self.model = model or get_default_model(self.provider, config)
        self.api_client = create_api_client(self.provider, {
            "api_key": api_key,
            "model": self.model,
            "temperature": config.get("temperature", 0.7),
            "base_url": get_provider_base_url(self.provider, config),
        })

        self.app_state    = AppState()
        self.cost_tracker = CostTracker()
        self._extra_dirs: List[str] = []   # /add-dir 追加的目录
        self._plan_mode: bool = False       # 计划模式：工具只描述不执行
        self._undo_stack: list = []         # 每轮文件快照 [(path, old_content), ...]
        self._current_turn_changes: list = []  # 当前轮次的变更
        self.tools    = self._load_tools()
        self.commands = self._load_commands()
        self._session_id = None

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def _load_tools(self):
        from mira.tools import get_tools
        tools = get_tools()
        # 加载插件工具
        try:
            from mira.services.plugins import load_plugins
            extra_tools, _ = load_plugins()
            tools.extend(extra_tools)
        except Exception:
            pass
        # 加载 MCP 工具（同步包装）
        try:
            from mira.services.mcp_client import load_mcp_tools
            mcp_tools = asyncio.run(load_mcp_tools()) if not self._loop_running() else []
            tools.extend(mcp_tools)
        except Exception:
            pass
        return tools

    def _loop_running(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            return loop.is_running()
        except Exception:
            return False

    def _load_commands(self):
        from mira.commands import get_commands
        extra_cmds = []
        try:
            from mira.services.plugins import load_plugins
            _, extra_cmds = load_plugins()
        except Exception:
            pass
        return get_commands(extra_cmds)

    def _build_system_prompt(self) -> str:
        """构建系统提示：时间/OS/CWD、Git 状态、项目检测、工具列表、NOTES.md"""
        import datetime
        cwd = os.getcwd()
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # ── Git 状态 ──────────────────────────────────────────
        git_section = self._git_status_brief()

        # ── 项目检测 ─────────────────────────────────────────
        project_section = self._detect_project(cwd)

        # ── 额外目录 ─────────────────────────────────────────
        extra_dirs_section = ""
        if self._extra_dirs:
            dirs_list = "\n".join(f"- {d}" for d in self._extra_dirs)
            extra_dirs_section = f"\n## 额外允许访问的目录\n{dirs_list}"

        # ── 记忆文件 ─────────────────────────────────────────
        memory = load_memory()
        memory_section = f"\n## 项目笔记 (NOTES.md)\n{memory}" if memory else ""

        # ── 工具列表 ─────────────────────────────────────────
        tools_desc = "\n".join(f"- {t.name}: {t.description}" for t in self.tools)

        # ── 上下文使用率 ──────────────────────────────────────
        ctx = get_context_usage(self.app_state.messages, self.model)
        ctx_info = (f"  上下文: {ctx['used']:,} / {ctx['window']:,} tokens "
                    f"({ctx['ratio']*100:.0f}%)")

        return f"""你是 Mira，一个专业的 AI 编程助手，运行在命令行终端中。

## 环境信息
- 当前时间: {now}
- 工作目录: {cwd}
- 操作系统: {os.name} / {sys.platform}
- Shell: {"PowerShell/cmd" if sys.platform == "win32" else os.environ.get("SHELL", "bash")}
{ctx_info}
{git_section}{project_section}{extra_dirs_section}
## 可用工具
{tools_desc}

## 行为准则
1. 优先使用工具完成任务，而不是仅仅给出建议
2. 读文件前先用 LSTool 或 GlobTool 确认文件是否存在
3. 修改文件前先用 FileReadTool 读取当前内容
4. 执行破坏性操作（删除、大范围修改）前需确认
5. 用简洁中文回答，代码用代码块展示
6. 任务完成后简洁说明做了什么{memory_section}"""

    def _git_status_brief(self) -> str:
        """返回简短的 Git 状态字符串（用于系统提示）"""
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=os.getcwd(), stderr=subprocess.DEVNULL, timeout=3,
                encoding="utf-8", errors="replace"
            ).strip()
            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=os.getcwd(), stderr=subprocess.DEVNULL, timeout=3,
                encoding="utf-8", errors="replace"
            )
            changed = len([l for l in status.splitlines() if l.strip()])
            if changed:
                return f"\n## Git 状态\n- 分支: {branch}\n- 变更文件: {changed} 个\n"
            return f"\n## Git 状态\n- 分支: {branch}（工作区干净）\n"
        except Exception:
            return ""

    def _detect_project(self, cwd: str) -> str:
        """检测项目类型（Python/Node/Go/Rust/Java 等）"""
        indicators = {
            "Python":     ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
            "Node.js":    ["package.json"],
            "Go":         ["go.mod"],
            "Rust":       ["Cargo.toml"],
            "Java/Kotlin":["pom.xml", "build.gradle", "build.gradle.kts"],
            "C/C++":      ["CMakeLists.txt", "Makefile"],
            "Ruby":       ["Gemfile"],
            "PHP":        ["composer.json"],
        }
        detected = []
        for lang, files in indicators.items():
            if any(os.path.exists(os.path.join(cwd, f)) for f in files):
                detected.append(lang)
        if detected:
            return f"\n## 项目类型\n- 检测到: {', '.join(detected)}\n"
        return ""

    def _get_tools_def(self) -> List[Dict]:
        """获取工具定义（用于 API 调用）"""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self.tools
        ]

    # 模型有时会用不同的名字调用工具，这里做别名映射
    _TOOL_ALIASES = {
        "ReadFile": "FileReadTool",
        "Read": "FileReadTool",
        "read_file": "FileReadTool",
        "WriteFile": "FileWriteTool",
        "Write": "FileWriteTool",
        "write_file": "FileWriteTool",
        "EditFile": "FileEditTool",
        "edit_file": "FileEditTool",
        "AppendFile": "FileAppendTool",
        "ListFiles": "LSTool",
        "list_files": "LSTool",
        "LS": "LSTool",
        "ls": "LSTool",
        "Bash": "BashTool",
        "bash": "BashTool",
        "run_command": "BashTool",
        "RunCommand": "BashTool",
        "Shell": "BashTool",
        "Search": "GrepTool",
        "Grep": "GrepTool",
        "grep": "GrepTool",
        "Glob": "GlobTool",
        "glob": "GlobTool",
        "DeleteFile": "DeleteTool",
        "delete_file": "DeleteTool",
        "MoveFile": "MoveTool",
        "move_file": "MoveTool",
        "CopyFile": "CopyTool",
        "copy_file": "CopyTool",
        "GitCommit": "GitCommitTool",
        "git_commit": "GitCommitTool",
        "GitPush": "GitPushTool",
        "git_push": "GitPushTool",
    }

    def _find_tool(self, name: str):
        for t in self.tools:
            if t.name == name:
                return t
        # 尝试别名
        canonical = self._TOOL_ALIASES.get(name)
        if canonical:
            for t in self.tools:
                if t.name == canonical:
                    return t
        # 不区分大小写的模糊匹配
        name_lower = name.lower().replace("_", "").replace("-", "")
        for t in self.tools:
            if t.name.lower().replace("_", "").replace("-", "") == name_lower:
                return t
        return None

    # ── 公共接口 ──────────────────────────────────────────────────────────────

    def run(self, args=None):
        """命令行入口"""
        if args and getattr(args, "print", False):
            asyncio.run(self._run_non_interactive(args))
        else:
            asyncio.run(self._run_interactive())

    def clear_history(self):
        self.app_state.clear_messages()

    # ── 非交互模式 ────────────────────────────────────────────────────────────

    async def _run_non_interactive(self, args):
        prompt = " ".join(args.prompt) if args.prompt else ""
        if not prompt:
            print("错误：请提供提示内容")
            return
        await self.process_message(prompt, callback=_cli_callback)

    # ── 交互模式 REPL ─────────────────────────────────────────────────────────

    def _print_banner(self) -> None:
        """打印启动 ASCII art 大字 Logo"""
        from mira import __version__
        cwd = os.getcwd()
        W = 54

        # 5 行高的 ASCII art "MIRA"（figlet Standard 风格）
        _ART = [
            r" __  __  ___  ____      _   ",
            r"|  \/  ||_ _||  _ \    / \  ",
            r"| |\/| | | | | |_) |  / _ \ ",
            r"| |  | | | | |  _ <  / ___ \ ",
            r"|_|  |_||___|_| \_\/_/   \_\ ",
        ]

        print()
        # 渐变色：顶部亮青 → 底部蓝
        color_fns = [_cyan, _cyan, _blue, _blue, _blue]
        for cfn, line in zip(color_fns, _ART):
            print("  " + cfn(_bold(line)))
        print()
        sub_pad = (W - 23) // 2
        sub_pad = max(sub_pad, 0)
        print("  " + _gray("─" * sub_pad) + " " + _bold(_cyan("A I  C O D I N G  A S S I S T A N T")) + " " + _gray("─" * sub_pad))
        print()
        sep = "  " + _gray("─" * W)
        print(sep)
        ver_line = f"  {_dim('版本')}  {_bold(_cyan('v' + __version__))}"
        print(ver_line)
        print(f"  {_dim('模型')}  {_yellow(self.provider)}{_gray('/')}{_bold(self.model)}")
        print(f"  {_dim('目录')}  {_gray(cwd)}")
        print(f"  {_dim('会话')}  {_gray(self.app_state.session_id)}")
        print(sep)
        print(f"  {_dim('/help')} 帮助  "
              f"{_dim('/status')} 状态  "
              f"{_dim('/cost')} 费用  "
              f"{_dim('/compact')} 压缩  "
              f"{_dim('/exit')} 退出")
        print()

    async def _run_interactive(self):
        self._print_banner()

        while True:
            try:
                # 提示符：显示当前目录的最后一段 + 轮次
                cwd_short = os.path.basename(os.getcwd()) or os.getcwd()
                msg_count = len([m for m in self.app_state.messages if m.get("role") == "user"])
                count_hint = _gray(f"[{msg_count}]") if msg_count > 0 else ""
                prompt = f"\n{_gray(cwd_short)}{count_hint} {_cyan('❯')} "
                user_input = input(prompt).strip()
                # 支持 \ 续行
                while user_input.endswith('\\'):
                    user_input = user_input[:-1]
                    cont = input("  ... ").strip()
                    user_input += '\n' + cont
                if not user_input:
                    continue

                # 处理斜杠命令
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                # 正常对话
                t0 = time.monotonic()
                await self.process_message(user_input, callback=_cli_callback)
                elapsed = time.monotonic() - t0
                if elapsed > 2:
                    print(_gray(f"  ⏱ {elapsed:.1f}s"))

            except KeyboardInterrupt:
                print(f"\n  {_dim('Ctrl+C — 使用 /exit 退出，/clear 清空历史')}")
            except EOFError:
                break

    def _handle_command(self, raw: str):
        cmd_name = raw[1:].split()[0].lower()
        for cmd in self.commands:
            if cmd.name == cmd_name:
                cmd.execute(raw[1:], self)
                return
        # 内置快捷命令
        if cmd_name == "exit":
            raise SystemExit(0)
        if cmd_name == "cwd":
            parts = raw.split(maxsplit=1)
            if len(parts) > 1:
                new_path = parts[1].strip()
                if os.path.isdir(new_path):
                    os.chdir(new_path)
                    print(f"  {_green('✓')} 工作目录: {_cyan(os.getcwd())}")
                else:
                    print(f"  {_red('✗')} 目录不存在: {new_path}")
            else:
                print(f"  {_dim('当前目录:')} {_cyan(os.getcwd())}")
            return
        # 计算编辑距离，找出最相似的命令
        all_cmd_names = [c.name for c in self.commands] + ["exit", "cwd"]

        def _edit_distance(a: str, b: str) -> int:
            m, n = len(a), len(b)
            dp = list(range(n + 1))
            for i in range(1, m + 1):
                prev = dp[0]
                dp[0] = i
                for j in range(1, n + 1):
                    temp = dp[j]
                    if a[i - 1] == b[j - 1]:
                        dp[j] = prev
                    else:
                        dp[j] = 1 + min(prev, dp[j], dp[j - 1])
                    prev = temp
            return dp[n]

        scored = sorted(
            all_cmd_names,
            key=lambda c: _edit_distance(cmd_name, c),
        )
        suggestions = scored[:3]
        sugg_str = ", ".join(f"{_cyan('/'+s)}" for s in suggestions)
        print(f"  {_yellow('?')} 未知命令 {_bold('/' + cmd_name)}")
        print(f"  你是想用: {sugg_str}?")
        print(f"  输入 {_cyan('/help')} 查看所有命令")

    # ── 核心：Agentic Loop ────────────────────────────────────────────────────

    async def process_message(self, user_input: str, callback: Callable = None,
                              images: List[Dict] = None):
        """处理用户消息，执行完整的 Agentic Loop 直至无工具调用

        Args:
            user_input: 用户文本输入
            callback: 事件回调
            images: 图片列表 [{media_type, data}]，用于视觉模型
        """
        if callback is None:
            callback = _cli_callback

        self._current_turn_changes = []

        if user_input or images:
            msg: Dict[str, Any] = {"role": "user", "content": user_input or ""}
            if images:
                msg["images"] = images
            self.app_state.add_message(msg)

        system_prompt = self._build_system_prompt()
        tools_def = self._get_tools_def()

        # 检查上下文是否接近限制，需要时自动紧凑化
        await self._check_context_and_compact(system_prompt, callback)

        await self._agentic_loop(system_prompt, tools_def, callback)

        # 将本轮文件变更推入 undo 栈
        if self._current_turn_changes:
            self._undo_stack.append(list(self._current_turn_changes))
            if len(self._undo_stack) > 20:
                self._undo_stack = self._undo_stack[-20:]
            self._current_turn_changes = []

        # 自动保存会话
        await self._auto_save_session()

    async def _check_context_and_compact(self, system_prompt: str, callback: Callable):
        """检查上下文用量，超过阈值时自动紧凑化"""
        compact_needed, ratio, used, window = should_compact(
            self.app_state.messages, self.model, system_prompt
        )
        if not compact_needed:
            if ratio >= 0.70:
                await callback({
                    "type": "warning",
                    "message": f"上下文使用率 {ratio*100:.0f}%（{used:,}/{window:,} tokens），建议使用 /compact 压缩",
                })
            return

        await callback({
            "type": "info",
            "message": f"上下文已用 {ratio*100:.0f}%（{used:,}/{window:,} tokens），自动压缩历史…",
        })
        await self._do_compact(callback)

    async def _do_compact(self, callback: Callable):
        """将对话历史压缩为摘要"""
        messages = self.app_state.messages
        if len(messages) < 4:
            return

        keep_count = max(2, self.config.get("context.compact_keep_recent", 6))
        to_summarize = messages[:-keep_count] if len(messages) > keep_count else messages[:]
        if not to_summarize:
            return

        # Extract a title hint from the first user message
        first_user = next(
            (m for m in to_summarize if m.get("role") == "user"), None
        )
        title_hint = ""
        if first_user:
            raw = str(first_user.get("content", "")).strip()
            raw = raw.split("\n")[0][:80]
            title_hint = f"（主题: {raw}）" if raw else ""

        summary_text = "\n".join(
            f"[{m.get('role','?')}]: {str(m.get('content',''))[:300]}"
            for m in to_summarize
        )
        summary_prompt = (
            f"请将以下对话历史{title_hint}浓缩为简洁摘要，保留关键决策、代码修改和上下文：\n\n"
            + summary_text
        )

        summary_parts: List[str] = []
        tc_buf: Dict = {}
        try:
            msgs = [{"role": "user", "content": summary_prompt}]
            stream = self.api_client.stream_message(msgs, [], "你是一个对话摘要助手，请简洁总结。")
            async for event in stream:
                text, _ = _parse_stream_event(event, tc_buf)
                if text:
                    summary_parts.append(text)
        except Exception:
            return

        summary = "".join(summary_parts).strip()
        if not summary:
            return

        kept = messages[-keep_count:] if len(messages) > keep_count else []
        self.app_state.clear_messages()
        self.app_state.add_message({
            "role": "user",
            "content": f"[对话历史摘要{title_hint}]\n{summary}",
        })
        for m in kept:
            self.app_state.add_message(m)

        await callback({
            "type": "info",
            "message": f"✓ 已压缩 {len(to_summarize)} 条历史，保留最近 {len(kept)} 条",
        })

    async def _snip_history(self, callback: Callable = None):
        """轻量级历史精简：删除旧的 tool_result 消息，保留对话流"""
        messages = self.app_state.messages
        if len(messages) < 6:
            return

        # Keep the most recent N messages intact
        keep_recent = self.config.get("context.compact_keep_recent", 6)
        old = messages[:-keep_recent]
        recent = messages[-keep_recent:]

        # From old messages, drop tool_result role entries
        snipped = [m for m in old if m.get("role") != "tool_result"]
        removed = len(old) - len(snipped)

        if removed == 0:
            return

        self.app_state.clear_messages()
        for m in snipped:
            self.app_state.add_message(m)
        for m in recent:
            self.app_state.add_message(m)

        if callback:
            await callback({
                "type": "info",
                "message": f"✓ 已精简 {removed} 条工具结果消息",
            })

    async def _auto_save_session(self):
        """自动保存当前会话到磁盘（超过3轮时尝试用AI生成标题）"""
        messages = self.app_state.export_messages()
        if not messages:
            return
        try:
            from mira.utils.sessions import save_session, generate_title_with_ai

            # 第3次保存时尝试用 AI 生成更好的标题（只做一次）
            ai_title = None
            user_turns = sum(1 for m in messages if m.get("role") == "user")
            if user_turns == 3 and not getattr(self, "_ai_title_generated", False):
                try:
                    ai_title = await generate_title_with_ai(messages, self.api_client)
                    if ai_title:
                        self._ai_title_generated = True
                        self.app_state._ai_title = ai_title
                except Exception:
                    pass

            title = getattr(self.app_state, "_ai_title", None)
            save_session(
                self.app_state.session_id,
                messages,
                {
                    "provider":   self.provider,
                    "model":      self.model,
                    "created_at": self.app_state.created_at,
                    "cwd":        os.getcwd(),
                    "title":      title,
                },
            )
        except Exception:
            pass

    async def _agentic_loop(self, system_prompt: str, tools_def: List[Dict], callback: Callable):
        """Agentic Loop：循环调用 API 直到不再有工具调用（默认无步数上限）"""
        # max_iterations=0 表示无限制；可在 config.json 设置 "max_iterations": N 来限制
        max_iterations = int(self.config.get("max_iterations", 0))
        iteration = 0

        while True:
            # 可选步数限制
            if max_iterations and iteration >= max_iterations:
                await callback({"type": "error", "message": f"已达到最大工具调用次数（{max_iterations}）"})
                break

            # 构建当前消息列表
            messages = normalize_messages_for_api(self.app_state.messages, self.provider)

            # 多步任务：显示迭代进度
            if iteration > 0:
                await callback({"type": "iteration", "n": iteration + 1})

            # 流式调用 API（带 spinner）
            text_parts = []
            tool_calls = []
            tc_buffer = {}
            got_first_token = False

            # 启动 spinner（仅 CLI 模式，Web 模式有自己的 typing 动画）
            spinner_task = None
            if callback is _cli_callback or callback.__name__ == "_cli_callback":
                spinner_task = asyncio.create_task(
                    _run_spinner("AI 思考中" if iteration == 0 else f"继续处理（步骤 {iteration+1}）")
                )

            try:
                stream = self.api_client.stream_message(messages, tools_def, system_prompt)
                async for event in stream:
                    # 第一个 token 到来时停止 spinner
                    if not got_first_token and spinner_task:
                        spinner_task.cancel()
                        try:
                            await spinner_task
                        except asyncio.CancelledError:
                            pass
                        spinner_task = None
                        got_first_token = True

                    # 捕获 usage 事件（Anthropic / 部分 OpenAI 兼容提供商）
                    if event.get("type") == "usage":
                        inp  = event.get("input_tokens", 0)
                        out  = event.get("output_tokens", 0)
                        cach = event.get("cache_read_tokens", 0)
                        if inp or out:
                            self.cost_tracker.add(self.model, inp, out, cach)
                            await callback({
                                "type":          "usage",
                                "input_tokens":  inp,
                                "output_tokens": out,
                                "cache_read":    cach,
                                "cost_usd":      self.cost_tracker.total_usd,
                            })
                        continue

                    # 捕获 thinking 事件（扩展思考）
                    if event.get("type") == "thinking":
                        content = event.get("content", "")
                        if content:
                            await callback({"type": "thinking", "content": content})
                        continue

                    text, new_tcs = _parse_stream_event(event, tc_buffer)
                    if text:
                        text_parts.append(text)
                        await callback({"type": "text", "content": text})
                    tool_calls.extend(new_tcs)
            except Exception as e:
                if spinner_task:
                    spinner_task.cancel()
                    try:
                        await spinner_task
                    except asyncio.CancelledError:
                        pass
                await callback({"type": "error", "message": str(e)})
                break
            finally:
                if spinner_task and not spinner_task.done():
                    spinner_task.cancel()
                    try:
                        await spinner_task
                    except asyncio.CancelledError:
                        pass

            # 处理 buffer 中剩余的 tool calls（部分 provider 不触发 finish_reason）
            for idx in sorted(tc_buffer.keys()):
                tc = tc_buffer[idx]
                if tc.get("name"):
                    try:
                        args = json.loads(tc["args_str"]) if tc["args_str"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({"id": tc["id"], "name": tc["name"], "args": args})

            full_text = "".join(text_parts)

            # 无工具调用：对话结束
            if not tool_calls:
                if full_text:
                    self.app_state.add_message({"role": "assistant", "content": full_text})
                await callback({"type": "done"})
                break

            # 有工具调用：保存 assistant 消息
            self.app_state.add_message({
                "role": "assistant",
                "content": full_text,
                "tool_calls": tool_calls,
            })

            # 执行所有工具调用
            tool_results = []
            for tc in tool_calls:
                result = await self._execute_tool(tc, callback)
                tool_results.append(result)

            # 保存工具结果
            self.app_state.add_message({
                "role": "tool_result",
                "tool_results": tool_results,
            })
            iteration += 1
            # 继续循环

    async def _execute_tool(self, tool_call: Dict, callback: Callable) -> Dict:
        """执行单个工具调用"""
        name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        tc_id = tool_call.get("id", "")

        # 通知工具开始
        await callback({"type": "tool_start", "name": name, "args": args, "id": tc_id})

        # 查找工具
        tool = self._find_tool(name)
        if not tool:
            content = f"错误：未知工具 '{name}'"
            await callback({"type": "tool_error", "name": name, "content": content, "id": tc_id})
            return {"tool_call_id": tc_id, "name": name, "content": content}

        # 文件变更快照（供 /undo 使用）
        _FILE_MUTATING_TOOLS = (
            'FileWriteTool', 'FileEditTool', 'FileAppendTool',
            'DeleteTool', 'MoveTool', 'CopyTool',
        )
        canonical_name = (tool.name if tool else name)
        if canonical_name in _FILE_MUTATING_TOOLS:
            snap_path = args.get('path', '')
            if snap_path:
                try:
                    old_content = open(snap_path, 'r', encoding='utf-8', errors='replace').read()
                except FileNotFoundError:
                    old_content = None
                except Exception:
                    old_content = None
                self._current_turn_changes.append((snap_path, old_content))

        # 权限检查
        if not self.skip_permissions:
            needed, prompt = needs_confirm(tool, args)
            if needed:
                approved = False
                try:
                    if self._confirm_fn:
                        # 异步确认（Web UI 通过 WebSocket）
                        approved = await self._confirm_fn(name, args, prompt)
                    else:
                        # CLI 同步确认（包装为线程，不阻塞事件循环）
                        approved = await asyncio.to_thread(
                            check_permission_sync, tool, args
                        )
                except Exception:
                    approved = False
                if not approved:
                    content = f"已拒绝: {prompt}"
                    await callback({"type": "tool_denied", "name": name, "content": content, "id": tc_id})
                    return {"tool_call_id": tc_id, "name": name, "content": content}

        # 计划模式：不执行工具，只返回描述
        if self._plan_mode and name not in ("EnterPlanMode", "ExitPlanMode"):
            args_summary = ", ".join(
                f"{k}={str(v)[:60]}" for k, v in args.items()
            ) if args else "无参数"
            content = f"[计划模式] 将调用 {name}({args_summary})"
            await callback({
                "type": "tool_result", "name": name, "content": content,
                "id": tc_id, "elapsed_ms": 0, "size": len(content),
            })
            return {"tool_call_id": tc_id, "name": name, "content": content}

        # 执行工具（计时），支持 execute_async / execute_stream / execute
        try:
            _t0 = time.monotonic()
            if hasattr(tool, "execute_async"):
                # 异步执行：工具需要访问 engine 或 asyncio 功能
                result = await tool.execute_async(args, callback, engine=self)
            elif hasattr(tool, "execute_stream"):
                # 流式执行：实时推送输出行
                async def _stream_cb(ev):
                    await callback(ev)
                result = await tool.execute_stream(args, _stream_cb)
            else:
                result = await asyncio.to_thread(tool.execute, args)
            elapsed_ms = int((time.monotonic() - _t0) * 1000)
            content = str(result) if result is not None else ""
            await callback({
                "type": "tool_result", "name": name, "content": content,
                "id": tc_id, "elapsed_ms": elapsed_ms, "size": len(content),
            })
            return {"tool_call_id": tc_id, "name": name, "content": content}
        except Exception as e:
            content = f"错误：{e}"
            await callback({"type": "tool_error", "name": name, "content": content, "id": tc_id})
            return {"tool_call_id": tc_id, "name": name, "content": content}
