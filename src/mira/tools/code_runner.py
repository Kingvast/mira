#!/usr/bin/env python3
"""
代码运行工具 — 在隔离环境中执行多种语言的代码片段
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from mira.tools.base import Tool

# ── 支持的语言配置 ──────────────────────────────────────────────────────────────

_LANG_CONFIG = {
    "python": {
        "ext": ".py",
        "cmd": [sys.executable],
        "comment": "Python",
    },
    "py": {
        "ext": ".py",
        "cmd": [sys.executable],
        "comment": "Python",
    },
    "javascript": {
        "ext": ".js",
        "cmd": ["node"],
        "comment": "JavaScript (Node.js)",
    },
    "js": {
        "ext": ".js",
        "cmd": ["node"],
        "comment": "JavaScript (Node.js)",
    },
    "typescript": {
        "ext": ".ts",
        "cmd": ["npx", "--yes", "ts-node", "--skip-project"],
        "comment": "TypeScript",
    },
    "ts": {
        "ext": ".ts",
        "cmd": ["npx", "--yes", "ts-node", "--skip-project"],
        "comment": "TypeScript",
    },
    "shell": {
        "ext": ".sh",
        "cmd": ["bash"] if sys.platform != "win32" else ["bash"],
        "comment": "Shell",
    },
    "bash": {
        "ext": ".sh",
        "cmd": ["bash"],
        "comment": "Bash",
    },
    "ruby": {
        "ext": ".rb",
        "cmd": ["ruby"],
        "comment": "Ruby",
    },
    "rb": {
        "ext": ".rb",
        "cmd": ["ruby"],
        "comment": "Ruby",
    },
    "php": {
        "ext": ".php",
        "cmd": ["php"],
        "comment": "PHP",
    },
    "go": {
        "ext": ".go",
        "cmd": ["go", "run"],
        "comment": "Go",
    },
    "rust": {
        "ext": ".rs",
        "cmd": None,  # 需要特殊处理（编译后运行）
        "comment": "Rust",
    },
    "r": {
        "ext": ".R",
        "cmd": ["Rscript"],
        "comment": "R",
    },
    "lua": {
        "ext": ".lua",
        "cmd": ["lua"],
        "comment": "Lua",
    },
    "perl": {
        "ext": ".pl",
        "cmd": ["perl"],
        "comment": "Perl",
    },
    "powershell": {
        "ext": ".ps1",
        "cmd": ["powershell", "-ExecutionPolicy", "Bypass", "-File"],
        "comment": "PowerShell",
    },
    "ps1": {
        "ext": ".ps1",
        "cmd": ["powershell", "-ExecutionPolicy", "Bypass", "-File"],
        "comment": "PowerShell",
    },
}

_DEFAULT_TIMEOUT = 30
_MAX_OUTPUT = 8000


# ══════════════════════════════════════════════════════════════════════════════
#  CodeRunnerTool
# ══════════════════════════════════════════════════════════════════════════════

class CodeRunnerTool(Tool):
    """在临时文件中执行代码片段，捕获 stdout/stderr 并返回。"""

    @property
    def name(self) -> str:
        return "CodeRunnerTool"

    @property
    def description(self) -> str:
        return (
            "在隔离的临时环境中运行代码片段并返回执行结果（stdout + stderr）。\n"
            "支持语言：python、javascript（Node.js）、typescript、shell/bash、"
            "ruby、php、go、r、lua、perl、powershell。\n"
            "适合：验证算法逻辑、测试数据转换、调试函数、运行数学计算、"
            "快速原型验证。代码在临时目录中执行，完成后自动清理。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": (
                        "编程语言。可选：python/py、javascript/js、typescript/ts、"
                        "shell/bash、ruby/rb、php、go、r、lua、perl、powershell/ps1"
                    ),
                },
                "code": {
                    "type": "string",
                    "description": "要执行的完整代码内容",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"超时秒数（默认 {_DEFAULT_TIMEOUT}，最大 120）",
                    "minimum": 1,
                    "maximum": 120,
                },
                "stdin": {
                    "type": "string",
                    "description": "标准输入内容（可选）",
                },
                "env": {
                    "type": "object",
                    "description": "额外的环境变量（JSON 对象）",
                },
                "working_dir": {
                    "type": "string",
                    "description": "工作目录路径（默认为当前工作目录）",
                },
            },
            "required": ["language", "code"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        language = str(args.get("language", "")).lower().strip()
        code = str(args.get("code", ""))
        timeout = min(int(args.get("timeout", _DEFAULT_TIMEOUT)), 120)
        stdin_text = args.get("stdin", "")
        extra_env = args.get("env") or {}
        working_dir = args.get("working_dir", "") or os.getcwd()

        if not language:
            return "错误: language 参数不能为空"
        if not code.strip():
            return "错误: code 参数不能为空"
        if language not in _LANG_CONFIG:
            supported = ", ".join(sorted(set(_LANG_CONFIG.keys())))
            return f"错误: 不支持的语言 '{language}'。支持: {supported}"

        cfg = _LANG_CONFIG[language]
        comment = cfg["comment"]

        # 特殊处理 Rust（需要编译）
        if language == "rust":
            return self._run_rust(code, timeout, working_dir, extra_env)

        ext = cfg["ext"]
        cmd_prefix = cfg["cmd"]

        # 检查解释器是否可用
        if cmd_prefix:
            runner = cmd_prefix[0]
            if not self._check_command(runner):
                return f"错误: 未找到 {comment} 解释器 '{runner}'，请先安装"

        # 写入临时文件并执行
        with tempfile.TemporaryDirectory(prefix="mira_run_") as tmpdir:
            src_file = Path(tmpdir) / f"script{ext}"
            src_file.write_text(code, encoding="utf-8")

            full_cmd = cmd_prefix + [str(src_file)]

            env = {**os.environ, **{str(k): str(v) for k, v in extra_env.items()}}

            start = time.monotonic()
            try:
                proc = subprocess.run(
                    full_cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    cwd=working_dir,
                    env=env,
                    input=stdin_text or None,
                )
                elapsed = time.monotonic() - start
                return self._format_result(
                    comment, proc.returncode, proc.stdout, proc.stderr, elapsed
                )
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - start
                return (
                    f"⏱ {comment} 代码执行超时（>{timeout}s）\n"
                    f"代码可能存在无限循环或 I/O 阻塞"
                )
            except FileNotFoundError:
                return f"错误: 找不到解释器 '{cmd_prefix[0]}'"
            except Exception as e:
                return f"执行失败: {e}"

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _run_rust(
        self, code: str, timeout: int, working_dir: str, extra_env: dict
    ) -> str:
        """编译并运行 Rust 代码（需要 rustc）"""
        if not self._check_command("rustc"):
            return "错误: 未找到 Rust 编译器 'rustc'，请先安装 Rust"

        with tempfile.TemporaryDirectory(prefix="mira_rust_") as tmpdir:
            src = Path(tmpdir) / "main.rs"
            out = Path(tmpdir) / ("main.exe" if sys.platform == "win32" else "main")
            src.write_text(code, encoding="utf-8")

            env = {**os.environ, **{str(k): str(v) for k, v in extra_env.items()}}

            # 编译
            compile_proc = subprocess.run(
                ["rustc", str(src), "-o", str(out)],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=60, cwd=working_dir, env=env,
            )
            if compile_proc.returncode != 0:
                return (
                    "Rust 编译失败:\n"
                    + (compile_proc.stderr or compile_proc.stdout or "（无输出）")
                )

            # 运行
            start = time.monotonic()
            try:
                run_proc = subprocess.run(
                    [str(out)],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=timeout, cwd=working_dir, env=env,
                )
                elapsed = time.monotonic() - start
                return self._format_result(
                    "Rust", run_proc.returncode,
                    run_proc.stdout, run_proc.stderr, elapsed,
                )
            except subprocess.TimeoutExpired:
                return f"⏱ Rust 程序执行超时（>{timeout}s）"

    @staticmethod
    def _check_command(cmd: str) -> bool:
        """检查命令是否可用"""
        import shutil
        return shutil.which(cmd) is not None

    @staticmethod
    def _format_result(
        lang: str, returncode: int,
        stdout: str, stderr: str, elapsed: float,
    ) -> str:
        """格式化执行结果"""
        status = "✓ 成功" if returncode == 0 else f"✗ 退出码 {returncode}"
        lines = [f"── {lang} 执行结果  {status}  ({elapsed:.3f}s) " + "─" * 20]

        if stdout:
            out = stdout
            if len(out) > _MAX_OUTPUT:
                out = out[:_MAX_OUTPUT] + f"\n… (已截断，共 {len(stdout):,} 字符)"
            lines.append(out.rstrip())

        if stderr:
            err = stderr
            if len(err) > _MAX_OUTPUT:
                err = err[:_MAX_OUTPUT] + f"\n… (已截断，共 {len(stderr):,} 字符)"
            lines.append("── stderr " + "─" * 40)
            lines.append(err.rstrip())

        if not stdout and not stderr:
            lines.append("（无输出）")

        return "\n".join(lines)
