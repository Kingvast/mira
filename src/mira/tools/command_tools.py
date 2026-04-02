#!/usr/bin/env python3
"""
命令执行工具 - BashTool / PowerShellTool
"""

import asyncio
import locale
import os
import sys
import threading
import subprocess
from typing import Dict, Any, Optional, Callable

from mira.tools.base import Tool

_MAX_OUTPUT = 20_000   # 单次最大输出字符数
_DEFAULT_TIMEOUT = 120  # 默认超时（秒）


def _run(cmd_args: list, cwd: str, timeout: int, env: dict = None) -> str:
    """运行子进程，返回合并后的输出字符串"""
    # 使用系统本地编码（Windows 中文环境为 GBK/CP936，避免 UTF-8 乱码）
    sys_enc = locale.getpreferredencoding(False) or "utf-8"
    try:
        proc = subprocess.run(
            cmd_args,
            cwd=cwd,
            capture_output=True,
            text=False,          # 获取原始 bytes，手动解码
            timeout=timeout,
            env=env or os.environ.copy(),
        )
        def _decode(b: bytes) -> str:
            if not b:
                return ""
            try:
                return b.decode(sys_enc, errors="replace")
            except Exception:
                return b.decode("utf-8", errors="replace")

        parts = []
        if proc.stdout:
            parts.append(_decode(proc.stdout))
        if proc.stderr:
            parts.append(_decode(proc.stderr))
        output = "\n".join(parts).rstrip()

        if proc.returncode != 0:
            output += f"\n[退出码 {proc.returncode}]"

        # 截断过长输出
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n... [输出已截断，共 {len(output)} 字符]"

        return output or "(无输出)"

    except subprocess.TimeoutExpired:
        return f"[超时] 命令执行超过 {timeout} 秒"
    except FileNotFoundError as e:
        return f"[错误] 命令未找到: {e}"
    except Exception as e:
        return f"[错误] {e}"


class BashTool(Tool):
    """执行 Shell / Bash 命令"""

    @property
    def name(self) -> str:
        return "BashTool"

    @property
    def description(self) -> str:
        return (
            "执行 Shell 命令。支持管道、重定向等 shell 语法。\n"
            "参数:\n"
            "  command (必填): 要执行的命令\n"
            "  cwd: 工作目录（默认当前目录）\n"
            "  timeout: 超时秒数（默认 120）\n"
            "  run_in_background: 后台运行，立即返回\n"
            "  description: 命令用途说明（可选）"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 Shell 命令"},
                "cwd": {"type": "string", "description": "工作目录（默认当前目录）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 120）"},
                "run_in_background": {"type": "boolean", "description": "后台运行（默认 false）"},
                "description": {"type": "string", "description": "命令说明"},
            },
            "required": ["command"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        command = args.get("command", "").strip()
        if not command:
            return "错误：command 参数不能为空"

        cwd = args.get("cwd") or os.getcwd()
        timeout = int(args.get("timeout") or _DEFAULT_TIMEOUT)
        bg = args.get("run_in_background", False)
        desc = args.get("description") or command[:80]

        if not os.path.isdir(cwd):
            return f"错误：工作目录不存在 - {cwd}"

        # 选择 shell
        if sys.platform == "win32":
            shell_cmd = ["cmd", "/c", command]
        else:
            shell_cmd = ["bash", "-c", command]
            # 如果 bash 不存在则回退 sh
            if not _which("bash"):
                shell_cmd = ["sh", "-c", command]

        if bg:
            def _run_bg():
                try:
                    subprocess.Popen(
                        shell_cmd, cwd=cwd,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            threading.Thread(target=_run_bg, daemon=True).start()
            return f"[后台运行] {desc}"

        return _run(shell_cmd, cwd=cwd, timeout=timeout)

    async def execute_stream(self, args: Dict[str, Any], stream_cb: Callable) -> str:
        """流式执行 Shell 命令，实时推送输出行"""
        command = args.get("command", "").strip()
        if not command:
            return "错误：command 参数不能为空"

        cwd = args.get("cwd") or os.getcwd()
        timeout = int(args.get("timeout") or _DEFAULT_TIMEOUT)
        bg = args.get("run_in_background", False)

        if not os.path.isdir(cwd):
            return f"错误：工作目录不存在 - {cwd}"

        if bg:
            if sys.platform == "win32":
                shell_cmd = ["cmd", "/c", command]
            else:
                shell_cmd = ["bash", "-c", command] if _which("bash") else ["sh", "-c", command]
            threading.Thread(
                target=lambda: subprocess.Popen(
                    shell_cmd, cwd=cwd,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ), daemon=True
            ).start()
            return f"[后台运行] {command[:80]}"

        sys_enc = locale.getpreferredencoding(False) or "utf-8"
        if sys.platform == "win32":
            shell_cmd = ["cmd", "/c", command]
        else:
            shell_cmd = ["bash", "-c", command] if _which("bash") else ["sh", "-c", command]

        collected: list = []
        chars_so_far = 0

        try:
            proc = await asyncio.create_subprocess_exec(
                *shell_cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=os.environ.copy(),
            )

            async def _read_stream():
                nonlocal chars_so_far
                assert proc.stdout
                while True:
                    try:
                        chunk = await asyncio.wait_for(proc.stdout.read(512), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    if not chunk:
                        break
                    try:
                        text = chunk.decode(sys_enc, errors="replace")
                    except Exception:
                        text = chunk.decode("utf-8", errors="replace")
                    collected.append(text)
                    chars_so_far += len(text)
                    if chars_so_far <= _MAX_OUTPUT:
                        await stream_cb({"type": "tool_stream", "text": text})

            try:
                await asyncio.wait_for(_read_stream(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                collected.append(f"\n[超时] 命令执行超过 {timeout} 秒")

            await proc.wait()
            rc = proc.returncode or 0
            if rc != 0:
                collected.append(f"\n[退出码 {rc}]")

        except FileNotFoundError as e:
            return f"[错误] 命令未找到: {e}"
        except Exception as e:
            return f"[错误] {e}"

        output = "".join(collected).rstrip()
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n... [输出已截断，共 {len(output)} 字符]"
        return output or "(无输出)"


class PowerShellTool(Tool):
    """执行 PowerShell 命令（Windows / macOS / Linux 均可用）"""

    @property
    def name(self) -> str:
        return "PowerShellTool"

    @property
    def description(self) -> str:
        return (
            "执行 PowerShell 命令（Windows 原生 powershell.exe 或跨平台 pwsh）。\n"
            "参数:\n"
            "  command (必填): PowerShell 命令\n"
            "  cwd: 工作目录（默认当前目录）\n"
            "  timeout: 超时秒数（默认 120）\n"
            "  run_in_background: 后台运行，立即返回"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "PowerShell 命令"},
                "cwd": {"type": "string", "description": "工作目录（默认当前目录）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 120）"},
                "run_in_background": {"type": "boolean", "description": "后台运行（默认 false）"},
            },
            "required": ["command"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        command = args.get("command", "").strip()
        if not command:
            return "错误：command 参数不能为空"

        cwd = args.get("cwd") or os.getcwd()
        timeout = int(args.get("timeout") or _DEFAULT_TIMEOUT)
        bg = args.get("run_in_background", False)

        if not os.path.isdir(cwd):
            return f"错误：工作目录不存在 - {cwd}"

        # 优先 pwsh（跨平台），其次 powershell（Windows 旧版）
        ps_bin = "pwsh" if _which("pwsh") else "powershell"
        shell_cmd = [
            ps_bin,
            "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", command,
        ]

        if bg:
            def _run_bg():
                try:
                    subprocess.Popen(
                        shell_cmd, cwd=cwd,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            threading.Thread(target=_run_bg, daemon=True).start()
            return f"[后台运行] {command[:80]}"

        return _run(shell_cmd, cwd=cwd, timeout=timeout)


def _which(name: str) -> bool:
    """检查命令是否在 PATH 中"""
    import shutil
    return shutil.which(name) is not None
