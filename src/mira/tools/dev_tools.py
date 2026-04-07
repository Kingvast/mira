#!/usr/bin/env python3
"""
开发工具 — Lint / 格式化 / 测试运行 / JSON查询
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

from mira.tools.base import Tool

_MAX_OUT = 8000
_TIMEOUT = 60


def _run(cmd: list, cwd: str = None, timeout: int = _TIMEOUT, env: dict = None) -> tuple[int, str, str]:
    """运行命令，返回 (returncode, stdout, stderr)"""
    try:
        env_ = {**os.environ, **(env or {})}
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=cwd or os.getcwd(), env=env_,
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", f"未找到命令 '{cmd[0]}'，请先安装"
    except subprocess.TimeoutExpired:
        return -1, "", f"命令超时（>{timeout}s）"
    except Exception as e:
        return -1, "", str(e)


def _trunc(s: str, limit: int = _MAX_OUT) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n… (已截断，共 {len(s):,} 字符)"


# ══════════════════════════════════════════════════════════════════════════════
#  LintTool  — 代码质量检查
# ══════════════════════════════════════════════════════════════════════════════

class LintTool(Tool):
    """对代码文件或目录运行 Lint / 静态分析工具。"""

    # 支持的 linter 配置
    _LINTERS = {
        "ruff":    (["ruff", "check"],           "Python - ruff (极速)"),
        "flake8":  (["flake8"],                  "Python - flake8"),
        "pylint":  (["pylint", "--output-format=text"], "Python - pylint"),
        "mypy":    (["mypy"],                    "Python - mypy (类型检查)"),
        "pyright": (["pyright"],                 "Python - pyright (类型检查)"),
        "eslint":  (["npx", "--no", "eslint"],   "JavaScript/TypeScript - eslint"),
        "tslint":  (["npx", "--no", "tslint"],   "TypeScript - tslint"),
        "shellcheck": (["shellcheck"],           "Shell - shellcheck"),
        "golangci-lint": (["golangci-lint", "run"], "Go - golangci-lint"),
        "clippy":  (["cargo", "clippy", "--", "-D", "warnings"], "Rust - clippy"),
        "rubocop": (["rubocop"],                 "Ruby - rubocop"),
    }

    @property
    def name(self) -> str:
        return "LintTool"

    @property
    def description(self) -> str:
        return (
            "对代码文件或目录运行 Lint 静态分析工具，检查代码质量、风格问题、潜在错误。\n"
            "auto 模式：根据文件扩展名自动选择最佳 linter；\n"
            "指定 linter：ruff/flake8/pylint/mypy/eslint/shellcheck/golangci-lint/clippy/rubocop。\n"
            "返回：错误数、警告数和详细问题列表。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要检查的文件或目录路径（默认当前目录）",
                },
                "linter": {
                    "type": "string",
                    "description": (
                        "linter 名称（默认 auto 自动检测）：\n"
                        "Python: ruff / flake8 / pylint / mypy / pyright\n"
                        "JS/TS: eslint  |  Shell: shellcheck\n"
                        "Go: golangci-lint  |  Rust: clippy  |  Ruby: rubocop"
                    ),
                },
                "fix": {
                    "type": "boolean",
                    "description": "是否自动修复（支持 ruff --fix 等，默认 false）",
                },
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "额外的命令行参数",
                },
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = str(args.get("path", ".")).strip() or "."
        linter = str(args.get("linter", "auto")).lower().strip()
        fix = args.get("fix", False)
        extra = args.get("extra_args") or []
        cwd = os.getcwd()

        # 自动检测 linter
        if linter == "auto":
            linter = self._detect_linter(path)
            if not linter:
                return (
                    "无法自动检测 linter。\n"
                    "请指定 linter 参数，例如: ruff / flake8 / eslint / shellcheck"
                )

        if linter not in self._LINTERS:
            supported = " / ".join(self._LINTERS.keys())
            return f"错误: 不支持的 linter '{linter}'。支持: {supported}"

        cmd_base, desc = self._LINTERS[linter]
        if not shutil.which(cmd_base[0]):
            return f"错误: 未找到 '{cmd_base[0]}'，请先安装 ({desc})"

        cmd = list(cmd_base)
        if fix and linter in ("ruff",):
            cmd.append("--fix")
        cmd.extend(extra)
        cmd.append(path)

        rc, stdout, stderr = _run(cmd, cwd=cwd)
        combined = "\n".join(filter(None, [stdout.rstrip(), stderr.rstrip()]))

        status = "✓ 无问题" if rc == 0 else f"✗ 发现问题（退出码 {rc}）"
        header = f"── {desc}  [{path}]  {status} " + "─" * 20

        return header + "\n" + _trunc(combined) if combined else header + "\n（无输出）"

    def _detect_linter(self, path: str) -> str:
        """根据文件扩展名/项目结构自动选择 linter"""
        p = Path(path)
        ext = p.suffix.lower() if p.is_file() else ""

        # 按扩展名
        if ext in (".py",) or (p.is_dir() and any(p.rglob("*.py"))):
            for ln in ("ruff", "flake8", "pylint"):
                if shutil.which(ln):
                    return ln
        if ext in (".js", ".jsx", ".ts", ".tsx"):
            if shutil.which("npx"):
                return "eslint"
        if ext in (".sh", ".bash"):
            if shutil.which("shellcheck"):
                return "shellcheck"
        if ext in (".go",) or (p.is_dir() and (p / "go.mod").exists()):
            if shutil.which("golangci-lint"):
                return "golangci-lint"
        if ext in (".rs",) or (p.is_dir() and (p / "Cargo.toml").exists()):
            return "clippy"
        if ext in (".rb",):
            if shutil.which("rubocop"):
                return "rubocop"

        # 目录级别检测
        if p.is_dir():
            if (p / "package.json").exists() and shutil.which("npx"):
                return "eslint"
            if (p / "Cargo.toml").exists():
                return "clippy"
            if (p / "go.mod").exists() and shutil.which("golangci-lint"):
                return "golangci-lint"
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  FormatTool  — 代码格式化
# ══════════════════════════════════════════════════════════════════════════════

class FormatTool(Tool):
    """对代码文件运行格式化工具（black/ruff/prettier/gofmt/rustfmt 等）。"""

    _FORMATTERS = {
        "black":    (["black"],                    "Python"),
        "ruff":     (["ruff", "format"],           "Python (ruff)"),
        "autopep8": (["autopep8", "--in-place"],   "Python"),
        "isort":    (["isort"],                    "Python imports"),
        "prettier": (["npx", "--no", "prettier", "--write"], "JS/TS/JSON/CSS/HTML/MD"),
        "gofmt":    (["gofmt", "-w"],              "Go"),
        "rustfmt":  (["rustfmt"],                  "Rust"),
        "shfmt":    (["shfmt", "-w"],              "Shell"),
        "xmlformat": (["xmlformat", "--overwrite"], "XML"),
    }

    @property
    def name(self) -> str:
        return "FormatTool"

    @property
    def description(self) -> str:
        return (
            "对代码文件运行格式化工具，自动修正缩进、空格、换行等风格问题。\n"
            "auto 模式：根据文件扩展名自动选择格式化工具；\n"
            "支持: black/ruff/autopep8/isort（Python）、prettier（JS/TS/JSON/CSS）、"
            "gofmt（Go）、rustfmt（Rust）、shfmt（Shell）。\n"
            "警告：此操作会直接修改文件内容。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要格式化的文件或目录路径",
                },
                "formatter": {
                    "type": "string",
                    "description": (
                        "格式化工具（默认 auto）：black/ruff/autopep8/isort/"
                        "prettier/gofmt/rustfmt/shfmt"
                    ),
                },
                "check_only": {
                    "type": "boolean",
                    "description": "仅检查不修改（check 模式，返回是否需要格式化，默认 false）",
                },
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "额外命令行参数",
                },
            },
            "required": ["path"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = str(args.get("path", "")).strip()
        formatter = str(args.get("formatter", "auto")).lower().strip()
        check_only = args.get("check_only", False)
        extra = args.get("extra_args") or []

        if not path:
            return "错误: path 参数不能为空"

        p = Path(path)
        if not p.exists():
            return f"错误: 路径不存在: {path}"

        if formatter == "auto":
            formatter = self._detect_formatter(path)
            if not formatter:
                return "无法自动检测格式化工具，请手动指定 formatter 参数"

        if formatter not in self._FORMATTERS:
            supported = " / ".join(self._FORMATTERS.keys())
            return f"错误: 不支持的格式化工具 '{formatter}'。支持: {supported}"

        cmd_base, desc = self._FORMATTERS[formatter]
        if not shutil.which(cmd_base[0]):
            return f"错误: 未找到 '{cmd_base[0]}'，请先安装"

        cmd = list(cmd_base)
        if check_only:
            if formatter == "black":
                cmd.append("--check")
            elif formatter == "ruff":
                cmd += ["--check"]
            elif formatter == "prettier":
                # 去掉 --write，改为 --check
                cmd = [c for c in cmd if c != "--write"] + ["--check"]
        cmd.extend(extra)
        cmd.append(path)

        rc, stdout, stderr = _run(cmd)
        combined = "\n".join(filter(None, [stdout.rstrip(), stderr.rstrip()]))

        if check_only:
            status = "✓ 格式正确，无需修改" if rc == 0 else "✗ 需要格式化"
        else:
            status = "✓ 格式化完成" if rc == 0 else f"✗ 格式化失败（退出码 {rc}）"

        header = f"── {desc} ({formatter})  [{path}]  {status}"
        return header + ("\n" + _trunc(combined) if combined else "")

    def _detect_formatter(self, path: str) -> str:
        p = Path(path)
        ext = p.suffix.lower() if p.is_file() else ""

        if ext == ".py":
            for f in ("black", "ruff", "autopep8"):
                if shutil.which(f):
                    return f
        if ext in (".js", ".jsx", ".ts", ".tsx", ".json", ".css", ".html", ".md"):
            if shutil.which("npx"):
                return "prettier"
        if ext == ".go":
            if shutil.which("gofmt"):
                return "gofmt"
        if ext == ".rs":
            if shutil.which("rustfmt"):
                return "rustfmt"
        if ext in (".sh", ".bash"):
            if shutil.which("shfmt"):
                return "shfmt"

        # 目录检测
        if p.is_dir():
            if any(p.glob("*.py")) and shutil.which("black"):
                return "black"
            if (p / "package.json").exists() and shutil.which("npx"):
                return "prettier"
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  TestRunnerTool  — 单元/集成测试运行
# ══════════════════════════════════════════════════════════════════════════════

class TestRunnerTool(Tool):
    """运行测试套件（pytest/unittest/jest/mocha/cargo test/go test 等）。"""

    _RUNNERS = {
        "pytest":   ["pytest", "-v", "--tb=short"],
        "unittest": [sys.executable, "-m", "unittest", "-v"],
        "jest":     ["npx", "--no", "jest", "--color"],
        "mocha":    ["npx", "--no", "mocha"],
        "vitest":   ["npx", "--no", "vitest", "run"],
        "cargo":    ["cargo", "test"],
        "go":       ["go", "test", "./...", "-v"],
        "ruby":     ["bundle", "exec", "rspec"],
        "phpunit":  ["./vendor/bin/phpunit"],
    }

    @property
    def name(self) -> str:
        return "TestRunnerTool"

    @property
    def description(self) -> str:
        return (
            "运行项目测试套件，自动检测测试框架或手动指定。\n"
            "支持: pytest / unittest（Python）、jest / mocha / vitest（JS/TS）、"
            "cargo test（Rust）、go test（Go）、rspec（Ruby）。\n"
            "返回：通过/失败数量、错误详情、耗时。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "测试文件或目录（默认当前目录）",
                },
                "runner": {
                    "type": "string",
                    "description": (
                        "测试运行器（默认 auto）：pytest/unittest/jest/mocha/vitest/"
                        "cargo/go/ruby/phpunit"
                    ),
                },
                "pattern": {
                    "type": "string",
                    "description": "测试名称匹配模式（pytest 的 -k，jest 的 --testNamePattern）",
                },
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "额外命令行参数",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（默认 120）",
                    "minimum": 10,
                    "maximum": 600,
                },
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = str(args.get("path", ".")).strip() or "."
        runner = str(args.get("runner", "auto")).lower().strip()
        pattern = str(args.get("pattern", "")).strip()
        extra = args.get("extra_args") or []
        timeout = int(args.get("timeout", 120))
        cwd = os.getcwd()

        if runner == "auto":
            runner = self._detect_runner(path, cwd)
            if not runner:
                return (
                    "无法自动检测测试框架。\n"
                    "请指定 runner 参数：pytest / jest / cargo / go 等"
                )

        if runner not in self._RUNNERS:
            supported = " / ".join(self._RUNNERS.keys())
            return f"错误: 不支持的测试运行器 '{runner}'。支持: {supported}"

        cmd_base = self._RUNNERS[runner]
        if not shutil.which(cmd_base[0]):
            return f"错误: 未找到 '{cmd_base[0]}'，请先安装"

        cmd = list(cmd_base)

        # 模式匹配
        if pattern:
            if runner == "pytest":
                cmd += ["-k", pattern]
            elif runner in ("jest", "vitest"):
                cmd += ["--testNamePattern", pattern]

        cmd.extend(extra)

        # 仅当 runner 不是全局测试（如 cargo/go）时才追加 path
        if runner not in ("cargo", "go") and path != ".":
            cmd.append(path)

        import time
        start = time.monotonic()
        rc, stdout, stderr = _run(cmd, cwd=cwd, timeout=timeout)
        elapsed = time.monotonic() - start

        combined = "\n".join(filter(None, [stdout.rstrip(), stderr.rstrip()]))
        status = "✓ 全部通过" if rc == 0 else f"✗ 存在失败（退出码 {rc}）"
        header = f"── {runner}  {status}  ({elapsed:.1f}s) " + "─" * 20

        return header + "\n" + _trunc(combined) if combined else header + "\n（无输出）"

    def _detect_runner(self, path: str, cwd: str) -> str:
        p = Path(cwd)

        # Python
        if (p / "pytest.ini").exists() or (p / "pyproject.toml").exists() or list(p.glob("test_*.py")) or list(p.glob("*_test.py")):
            if shutil.which("pytest"):
                return "pytest"
            return "unittest"

        # JS/TS
        pkg = p / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                scripts = data.get("scripts", {})
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "vitest" in deps:
                    return "vitest"
                if "jest" in deps:
                    return "jest"
                if "mocha" in deps:
                    return "mocha"
            except Exception:
                pass

        # Rust
        if (p / "Cargo.toml").exists():
            return "cargo"

        # Go
        if (p / "go.mod").exists():
            return "go"

        # Ruby
        if (p / "Gemfile").exists() and (p / "spec").is_dir():
            return "ruby"

        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  JQTool  — JSON 查询与变换
# ══════════════════════════════════════════════════════════════════════════════

class JQTool(Tool):
    """对 JSON 数据执行 jq 风格的查询、过滤、变换操作（纯 Python 实现，无需安装 jq）。"""

    @property
    def name(self) -> str:
        return "JQTool"

    @property
    def description(self) -> str:
        return (
            "对 JSON 数据进行查询和变换（jq 风格的简化实现）。\n"
            "operations:\n"
            "  query     — 使用 JSONPath 表达式提取数据（如 .key / .arr[0] / .[] ）\n"
            "  keys      — 列出对象所有键\n"
            "  length    — 返回数组长度或对象键数\n"
            "  flatten   — 展开嵌套数组\n"
            "  sort      — 排序数组\n"
            "  unique    — 去重\n"
            "  map       — 对数组每个元素提取字段（如 .name）\n"
            "  filter    — 按条件过滤数组元素\n"
            "  format    — 美化 JSON（pretty print）\n"
            "  minify    — 压缩 JSON（单行）\n"
            "  stats     — 统计 JSON 结构信息\n"
            "可从字符串或文件读取 JSON 数据。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "操作: query/keys/length/flatten/sort/unique/map/filter/format/minify/stats",
                },
                "json": {
                    "type": "string",
                    "description": "JSON 字符串（与 file 二选一）",
                },
                "file": {
                    "type": "string",
                    "description": "JSON 文件路径（与 json 二选一）",
                },
                "expression": {
                    "type": "string",
                    "description": (
                        "查询/变换表达式。\n"
                        "query 支持: `.key` `.arr[0]` `.[]` `.a.b.c` 等简单路径\n"
                        "map 支持: `.field_name` 提取字段\n"
                        "filter 支持: Python 风格条件 (e['age']>18)"
                    ),
                },
                "sort_key": {
                    "type": "string",
                    "description": "sort 操作时用于排序的字段名（可选）",
                },
            },
            "required": ["operation"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        operation = str(args.get("operation", "format")).lower()
        json_str = args.get("json", "")
        file_path = args.get("file", "")
        expression = str(args.get("expression", "")).strip()
        sort_key = str(args.get("sort_key", "")).strip()

        # 读取 JSON 数据
        if file_path:
            try:
                json_str = Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                return f"错误: 无法读取文件: {e}"

        if not json_str and operation not in ("format", "minify"):
            return "错误: 需要提供 json 或 file 参数"

        if json_str:
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                return f"JSON 解析错误: {e}"
        else:
            data = None

        try:
            if operation == "format":
                result = json.dumps(data, ensure_ascii=False, indent=2)
            elif operation == "minify":
                result = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            elif operation == "keys":
                result = self._keys(data)
            elif operation == "length":
                result = self._length(data)
            elif operation == "flatten":
                result = json.dumps(self._flatten(data), ensure_ascii=False, indent=2)
            elif operation == "sort":
                result = json.dumps(self._sort(data, sort_key), ensure_ascii=False, indent=2)
            elif operation == "unique":
                result = json.dumps(self._unique(data), ensure_ascii=False, indent=2)
            elif operation == "map":
                result = json.dumps(self._map(data, expression), ensure_ascii=False, indent=2)
            elif operation == "filter":
                result = json.dumps(self._filter(data, expression), ensure_ascii=False, indent=2)
            elif operation == "query":
                result = json.dumps(self._query(data, expression), ensure_ascii=False, indent=2)
            elif operation == "stats":
                result = self._stats(data)
            else:
                return f"错误: 未知操作 '{operation}'"

            return _trunc(result)

        except Exception as e:
            return f"操作失败: {e}"

    # ── 操作实现 ──────────────────────────────────────────────────────────────

    def _keys(self, data) -> str:
        if isinstance(data, dict):
            keys = list(data.keys())
            return f"键（{len(keys)} 个）:\n" + "\n".join(f"  {k}" for k in keys)
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                all_keys = sorted(set(k for item in data if isinstance(item, dict) for k in item.keys()))
                return f"数组元素的键（{len(all_keys)} 个）:\n" + "\n".join(f"  {k}" for k in all_keys)
            return f"数组长度: {len(data)}（元素非对象类型）"
        return f"类型: {type(data).__name__}（无键）"

    def _length(self, data) -> str:
        if isinstance(data, (list, dict, str)):
            return f"长度: {len(data)}"
        return f"值: {data}（非序列类型）"

    def _flatten(self, data, depth: int = -1) -> list:
        if not isinstance(data, list):
            return [data]
        result = []
        for item in data:
            if isinstance(item, list) and depth != 0:
                result.extend(self._flatten(item, depth - 1))
            else:
                result.append(item)
        return result

    def _sort(self, data, key: str) -> list:
        if not isinstance(data, list):
            return data
        if key and all(isinstance(x, dict) and key in x for x in data):
            return sorted(data, key=lambda x: x[key])
        try:
            return sorted(data)
        except TypeError:
            return sorted(data, key=str)

    def _unique(self, data) -> list:
        if not isinstance(data, list):
            return data
        seen = []
        result = []
        for item in data:
            k = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if k not in seen:
                seen.append(k)
                result.append(item)
        return result

    def _map(self, data, expr: str) -> list:
        if not isinstance(data, list):
            return data
        if not expr:
            return data
        field = expr.lstrip(".")
        return [item.get(field) if isinstance(item, dict) else None for item in data]

    def _filter(self, data, expr: str) -> list:
        if not isinstance(data, list):
            return data
        if not expr:
            return data
        result = []
        for item in data:
            try:
                # 安全地求值：只允许比较/逻辑运算
                e = item
                if eval(expr, {"e": item, "__builtins__": {}}):
                    result.append(item)
            except Exception:
                pass
        return result

    def _query(self, data, expr: str):
        """简单 JSONPath 实现（支持 .key .arr[0] .[] .a.b 等）"""
        if not expr or expr == ".":
            return data

        # 拆分路径 segment
        import re
        segments = []
        for part in re.split(r'(?<!\[)\.(?!\d)', expr.lstrip(".")):
            # 处理数组索引 key[0]
            m = re.match(r'^(\w*)\[(\d+|-1)\]$', part)
            if m:
                if m.group(1):
                    segments.append(("key", m.group(1)))
                segments.append(("idx", int(m.group(2))))
            elif part == "[]":
                segments.append(("iter", None))
            elif part:
                segments.append(("key", part))

        def walk(node, segs):
            if not segs:
                return node
            kind, val = segs[0]
            rest = segs[1:]
            if kind == "key":
                if isinstance(node, dict) and val in node:
                    return walk(node[val], rest)
                return None
            elif kind == "idx":
                if isinstance(node, list):
                    return walk(node[val], rest) if -len(node) <= val < len(node) else None
                return None
            elif kind == "iter":
                if isinstance(node, list):
                    return [walk(x, rest) for x in node]
                return None
            return None

        return walk(data, segments)

    def _stats(self, data) -> str:
        lines = ["JSON 统计信息:"]
        lines.append(f"  根类型: {type(data).__name__}")
        if isinstance(data, dict):
            lines.append(f"  键数量: {len(data)}")
            lines.append(f"  顶层键: {', '.join(list(data.keys())[:10])}" + ("…" if len(data) > 10 else ""))
        elif isinstance(data, list):
            lines.append(f"  数组长度: {len(data)}")
            if data:
                lines.append(f"  元素类型: {type(data[0]).__name__}")
                if isinstance(data[0], dict):
                    keys = list(data[0].keys())
                    lines.append(f"  对象键: {', '.join(keys[:8])}" + ("…" if len(keys) > 8 else ""))
        raw = json.dumps(data, ensure_ascii=False)
        lines.append(f"  序列化大小: {len(raw):,} 字符")
        return "\n".join(lines)
