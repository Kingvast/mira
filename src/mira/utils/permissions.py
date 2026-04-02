#!/usr/bin/env python3
"""
权限检查 - 工具调用前的安全确认
"""

import json
import os
import difflib
from typing import Any, Tuple

# 需要明确确认的 Shell 危险命令模式
_DANGEROUS_CMD_PATTERNS = [
    "rm -rf", "rmdir /s", "format ", "mkfs",
    ":(){:|:&};:",  # fork bomb
    "dd if=", "> /dev/", "shutdown", "reboot",
    "DROP TABLE", "DROP DATABASE",
]

# 已被用户选择"始终允许"的工具集（运行时缓存，本次启动有效）
_always_allowed: set = set()


def set_always_allowed(tool_name: str):
    """将工具加入始终允许集合（本次运行有效）"""
    _always_allowed.add(tool_name)


def _make_diff(path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
    """生成 FileEditTool 的 unified diff 预览（最多 80 行）"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            orig = f.read()
        if replace_all:
            new_content = orig.replace(old_str, new_str)
        else:
            new_content = orig.replace(old_str, new_str, 1)
        diff_lines = list(difflib.unified_diff(
            orig.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(path)}",
            tofile=f"b/{os.path.basename(path)}",
            n=3,
        ))
        if not diff_lines:
            return "(无变化)"
        if len(diff_lines) > 80:
            diff_lines = diff_lines[:80]
            diff_lines.append(f"\n... (共 {len(diff_lines)} 行，已截断)\n")
        return "".join(diff_lines)
    except Exception as e:
        return f"(无法生成预览: {e})"


def needs_confirm(tool, args: Any) -> Tuple[bool, str]:
    """
    判断工具调用是否需要用户确认。
    返回 (需要确认, 确认提示语/diff)
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    if not isinstance(args, dict):
        args = {}

    # 已被用户授权"始终允许"
    if tool.name in _always_allowed:
        return False, ""

    # ── 文件编辑（展示 diff）────────────────────────────────────────────────
    if tool.name == "FileEditTool":
        path = args.get("path", "")
        old_str = args.get("old_string", "")
        new_str = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        diff = _make_diff(path, old_str, new_str, replace_all)
        return True, f"编辑文件: {path}\n{diff}"

    # ── 创建/覆盖写入文件 ──────────────────────────────────────────────────
    if tool.name == "FileWriteTool":
        path = args.get("path", "")
        content = args.get("content", "")
        exists = os.path.exists(path)
        action = "覆盖" if exists else "新建"
        size = len(content.encode("utf-8"))
        lines = content.count("\n") + 1
        return True, f"{action}文件: {path}  ({lines} 行 / {size:,} 字节)"

    # ── 追加内容到文件 ─────────────────────────────────────────────────────
    if tool.name == "FileAppendTool":
        path = args.get("path", "")
        content = args.get("content", "")
        preview = content.strip()[:120].replace("\n", "↵")
        if len(content.strip()) > 120:
            preview += "…"
        return True, f"追加到文件: {path}\n  内容: {preview}"

    # ── 删除文件/目录 ──────────────────────────────────────────────────────
    if tool.name == "DeleteTool":
        path = args.get("path") or args.get("source") or ""
        is_dir = os.path.isdir(path)
        return True, f"永久删除{'目录' if is_dir else '文件'}: {path}"

    # ── 移动/重命名 ────────────────────────────────────────────────────────
    if tool.name == "MoveTool":
        src = args.get("source") or args.get("src") or ""
        dst = args.get("destination") or args.get("dst") or ""
        return True, f"移动: {src}  →  {dst}"

    # ── Shell 命令：危险模式才确认 ─────────────────────────────────────────
    if tool.name in ("BashTool", "PowerShellTool"):
        cmd = args.get("command", "")
        for pattern in _DANGEROUS_CMD_PATTERNS:
            if pattern.lower() in cmd.lower():
                return True, f"[危险命令] {cmd[:300]}"
        return False, ""

    # ── Git Push（影响远端）────────────────────────────────────────────────
    if tool.name == "GitPushTool":
        branch = args.get("branch", "")
        return True, f"git push: {branch}"

    # ── Git Commit（写入历史）──────────────────────────────────────────────
    if tool.name == "GitCommitTool":
        msg = args.get("message", "")
        return True, f"git commit: {msg[:80]}"

    return False, ""


def _color_diff_line(line: str) -> str:
    """给 diff 行添加 ANSI 颜色（自动检测终端支持）"""
    import sys
    # 检查终端是否支持颜色
    supports = (
        hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        and not os.environ.get("NO_COLOR")
    )
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            supports = False

    if not supports:
        return line

    def _c(code, s): return f"\033[{code}m{s}\033[0m"

    if line.startswith("+++") or line.startswith("---"):
        return _c("1;37", line)          # 白色加粗（文件名行）
    if line.startswith("@@"):
        return _c("36", line)            # 青色（hunk header）
    if line.startswith("+"):
        return _c("32", line)            # 绿色（新增）
    if line.startswith("-"):
        return _c("31", line)            # 红色（删除）
    return _c("2", line)                 # 暗色（上下文行）


def check_permission_sync(tool, args: Any) -> bool:
    """CLI 同步确认（交互模式下使用）"""
    needed, prompt = needs_confirm(tool, args)
    if not needed:
        return True
    try:
        import sys
        W = 54
        print()
        print(f"  ┌─ 确认操作 {'─' * (W - 6)}")
        lines = prompt.splitlines()
        for line in lines:
            colored = _color_diff_line(line)
            print(f"  │ {colored}")
        print(f"  └{'─' * W}")
        ans = input("  继续? [y/N/a=始终允许本工具] ").strip().lower()
        if ans in ("a", "always", "始终", "始终允许"):
            set_always_allowed(tool.name)
            return True
        return ans in ("y", "yes", "是")
    except (EOFError, KeyboardInterrupt):
        return False
