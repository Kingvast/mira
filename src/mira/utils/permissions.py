#!/usr/bin/env python3
"""
权限系统 - 工具调用前的分级确认

会话内权限粒度（从细到粗）：
  文件级  — 允许对某个具体文件的所有操作
  目录级  — 允许对某个目录（含子目录）的所有操作
  工具级  — 允许某个工具的所有调用

确认菜单示例：
  1  允许本次
  2  允许此文件的所有操作  (本会话)
  3  允许此目录的所有操作  (本会话)
  4  允许此工具的所有操作  (本会话)
  5  拒绝
"""

import difflib
import json
import os
import sys
from pathlib import Path
from typing import Any, Tuple, Optional, Set

# ── 危险命令模式（Shell 工具额外检查）────────────────────────────────────────
_DANGEROUS_CMD_PATTERNS = [
    "rm -rf", "rmdir /s", "format ", "mkfs",
    ":(){:|:&};:",   # fork bomb
    "dd if=", "> /dev/", "shutdown", "reboot",
    "DROP TABLE", "DROP DATABASE",
]

# ── 会话级权限缓存（进程重启后清空）────────────────────────────────────────
_allowed_tools: Set[str] = set()        # tool.name
_allowed_files: Set[str] = set()        # 绝对路径
_allowed_dirs:  Set[str] = set()        # 绝对路径（末尾带 sep）


# ── 公开 API ─────────────────────────────────────────────────────────────────

def allow_tool(tool_name: str):
    """将工具加入会话允许集合"""
    _allowed_tools.add(tool_name)


def allow_file(file_path: str):
    """将文件加入会话允许集合（绝对路径）"""
    _allowed_files.add(os.path.abspath(file_path))


def allow_dir(dir_path: str):
    """将目录加入会话允许集合（绝对路径，含子目录）"""
    p = os.path.abspath(dir_path)
    if not p.endswith(os.sep):
        p += os.sep
    _allowed_dirs.add(p)


def revoke_tool(tool_name: str) -> bool:
    if tool_name in _allowed_tools:
        _allowed_tools.discard(tool_name)
        return True
    return False


def revoke_file(file_path: str) -> bool:
    p = os.path.abspath(file_path)
    if p in _allowed_files:
        _allowed_files.discard(p)
        return True
    return False


def revoke_dir(dir_path: str) -> bool:
    p = os.path.abspath(dir_path)
    if not p.endswith(os.sep):
        p += os.sep
    if p in _allowed_dirs:
        _allowed_dirs.discard(p)
        return True
    return False


def clear_all():
    """清空所有会话权限"""
    _allowed_tools.clear()
    _allowed_files.clear()
    _allowed_dirs.clear()


def get_status() -> dict:
    """返回当前权限状态快照"""
    return {
        "tools": sorted(_allowed_tools),
        "files": sorted(_allowed_files),
        "dirs":  sorted(_allowed_dirs),
    }


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _extract_file_path(tool_name: str, args: dict) -> Optional[str]:
    """从工具参数中提取文件/目录路径（返回绝对路径或 None）"""
    path = (
        args.get("path")
        or args.get("file_path")
        or args.get("source")
        or args.get("src")
    )
    if path and isinstance(path, str):
        return os.path.abspath(path)
    return None


def _is_permitted_by_session(tool_name: str, args: dict) -> bool:
    """检查是否已通过会话级权限"""
    if tool_name in _allowed_tools:
        return True
    file_path = _extract_file_path(tool_name, args)
    if file_path:
        if file_path in _allowed_files:
            return True
        # 前缀匹配目录权限
        fp_norm = file_path if file_path.endswith(os.sep) else file_path + os.sep
        for d in _allowed_dirs:
            if fp_norm.startswith(d) or file_path.startswith(d):
                return True
    return False


def _make_diff(path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
    """生成 FileEditTool 的 unified diff 预览（最多 60 行）"""
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
        if len(diff_lines) > 60:
            diff_lines = diff_lines[:60]
            diff_lines.append(f"\n… (已截断，共 {len(diff_lines)} 行)\n")
        return "".join(diff_lines)
    except Exception as e:
        return f"(无法生成预览: {e})"


def _color_diff_line(line: str) -> str:
    """给 diff 行添加 ANSI 颜色"""
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
        return _c("1;37", line)
    if line.startswith("@@"):
        return _c("36", line)
    if line.startswith("+"):
        return _c("32", line)
    if line.startswith("-"):
        return _c("31", line)
    return _c("2", line)


# ── 主判断逻辑 ────────────────────────────────────────────────────────────────

def needs_confirm(tool, args: Any) -> Tuple[bool, str]:
    """
    判断工具调用是否需要用户确认。
    返回 (需要确认, 确认说明/diff 字符串)
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    if not isinstance(args, dict):
        args = {}

    tool_name = tool.name if hasattr(tool, "name") else str(tool)

    # ── 文件编辑（展示 diff）──────────────────────────────────────────────────
    if tool_name == "FileEditTool":
        path = args.get("path", "")
        old_str = args.get("old_string", "")
        new_str = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        diff = _make_diff(path, old_str, new_str, replace_all)
        return True, f"编辑文件: {path}\n{diff}"

    # ── 创建/覆盖写入文件 ────────────────────────────────────────────────────
    if tool_name == "FileWriteTool":
        path = args.get("path", "")
        content = args.get("content", "")
        exists = os.path.exists(path)
        action = "覆盖" if exists else "新建"
        size = len(content.encode("utf-8"))
        lines = content.count("\n") + 1
        return True, f"{action}文件: {path}  ({lines} 行 / {size:,} 字节)"

    # ── 追加内容到文件 ────────────────────────────────────────────────────────
    if tool_name == "FileAppendTool":
        path = args.get("path", "")
        content = args.get("content", "")
        preview = content.strip()[:120].replace("\n", "↵")
        if len(content.strip()) > 120:
            preview += "…"
        return True, f"追加到文件: {path}\n  内容: {preview}"

    # ── 删除文件/目录 ────────────────────────────────────────────────────────
    if tool_name == "DeleteTool":
        path = args.get("path") or args.get("source") or ""
        is_dir = os.path.isdir(path)
        return True, f"永久删除{'目录' if is_dir else '文件'}: {path}"

    # ── 移动/重命名 ──────────────────────────────────────────────────────────
    if tool_name == "MoveTool":
        src = args.get("source") or args.get("src") or ""
        dst = args.get("destination") or args.get("dst") or ""
        return True, f"移动: {src}  →  {dst}"

    # ── Shell 命令：危险模式才确认 ─────────────────────────────────────────
    if tool_name in ("BashTool", "PowerShellTool"):
        cmd = args.get("command", "")
        for pattern in _DANGEROUS_CMD_PATTERNS:
            if pattern.lower() in cmd.lower():
                return True, f"[危险命令] {cmd[:300]}"
        return False, ""

    # ── Git Push（影响远端）────────────────────────────────────────────────
    if tool_name == "GitPushTool":
        branch = args.get("branch", "")
        return True, f"git push: {branch}"

    # ── Git Commit（写入历史）──────────────────────────────────────────────
    if tool_name == "GitCommitTool":
        msg = args.get("message", "")
        return True, f"git commit: {msg[:80]}"

    # ── 进程结束（不可逆）────────────────────────────────────────────────────
    if tool_name == "ProcessTool":
        if args.get("action", "").lower() == "kill":
            pid  = args.get("pid")
            name = args.get("name", "")
            target = f"PID {pid}" if pid else name
            return True, f"结束进程: {target}"

    # ── 压缩包创建（写入文件）────────────────────────────────────────────────
    if tool_name == "ArchiveTool":
        if args.get("action", "").lower() == "create":
            path = args.get("path", "")
            files = args.get("files", [])
            return True, f"创建压缩包: {path}  (打包 {len(files)} 个来源)"

    return False, ""


# ── 交互式确认（CLI 同步）────────────────────────────────────────────────────

def check_permission_sync(tool, args: Any) -> bool:
    """
    CLI 交互式权限确认。
    先检查会话缓存，未命中才弹出编号菜单。
    返回 True = 允许执行，False = 拒绝。
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    if not isinstance(args, dict):
        args = {}

    tool_name = tool.name if hasattr(tool, "name") else str(tool)

    needed, prompt_text = needs_confirm(tool, args)
    if not needed:
        return True

    # 命中会话级缓存 → 直接放行
    if _is_permitted_by_session(tool_name, args):
        return True

    # ── 构建菜单选项 ────────────────────────────────────────────────────────
    file_path = _extract_file_path(tool_name, args)
    abs_file  = os.path.abspath(file_path) if file_path else None
    abs_dir   = (str(Path(abs_file).parent) + os.sep) if abs_file else None

    try:
        # 打印分隔框
        W = 56
        _supports = (
            hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
            and not os.environ.get("NO_COLOR")
        )
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleMode(
                    ctypes.windll.kernel32.GetStdHandle(-11), 7)
                _supports = True
            except Exception:
                pass

        def _c(code, s):
            return f"\033[{code}m{s}\033[0m" if _supports else s

        print()
        print(f"  ┌─ {_c('1;33', '权限请求')} {'─' * (W - 6)}")

        # 展示 diff / 描述
        lines = prompt_text.splitlines()
        for line in lines:
            colored = _color_diff_line(line)
            print(f"  │ {colored}")
        print(f"  └{'─' * W}")
        print()

        # 构建选项列表
        options = []
        options.append(("允许本次", None))
        if abs_file:
            rel_file = _rel_display(abs_file)
            options.append((f"允许此文件的所有操作  {_c('2', rel_file)}", ("file", abs_file)))
        if abs_dir:
            rel_dir = _rel_display(abs_dir.rstrip(os.sep))
            options.append((f"允许此目录的所有操作  {_c('2', rel_dir + os.sep)}", ("dir", abs_dir)))
        options.append((f"允许 {_c('36', tool_name)} 的所有操作", ("tool", tool_name)))
        options.append((_c("31", "拒绝"), "deny"))

        for i, (label, _) in enumerate(options, 1):
            print(f"  {_c('1', str(i))}  {label}")
        print()

        raw = input(f"  请选择 [{_c('1;32', '1')}-{len(options)}]，直接回车=1: ").strip()
        choice = int(raw) if raw.isdigit() else 1

        if choice < 1 or choice > len(options):
            choice = 1

        _, action = options[choice - 1]

        # 最后一项 = 拒绝
        if action == "deny":
            _print_deny_hint(tool_name, abs_file, abs_dir, _c)
            return False

        # 允许本次
        if action is None:
            return True

        # 写入会话缓存
        kind, value = action
        if kind == "file":
            allow_file(value)
        elif kind == "dir":
            allow_dir(value)
        elif kind == "tool":
            allow_tool(value)

        return True

    except (EOFError, KeyboardInterrupt):
        return False


def _rel_display(path: str) -> str:
    """显示相对当前目录的路径（失败时显示绝对路径）"""
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


def _print_deny_hint(tool_name: str, abs_file: Optional[str],
                     abs_dir: Optional[str], _c):
    """拒绝后，打印如何后续授权的提示"""
    print()
    print(f"  {_c('31', '✗')} 已拒绝。若稍后想授权，可输入：")
    if abs_file:
        rel = _rel_display(abs_file)
        print(f"      {_c('36', '/permissions allow file')} {rel}")
    if abs_dir:
        rel = _rel_display(abs_dir.rstrip(os.sep))
        print(f"      {_c('36', '/permissions allow dir')}  {rel}")
    print(f"      {_c('36', '/permissions allow tool')} {tool_name}")
    print(f"  或在下次提示时选择对应选项。")
    print()


# ── 向后兼容 ──────────────────────────────────────────────────────────────────

def set_always_allowed(tool_name: str):
    """旧接口兼容（等同于 allow_tool）"""
    allow_tool(tool_name)
