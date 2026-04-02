#!/usr/bin/env python3
"""
Git 操作工具
"""

import subprocess
import os
from typing import Dict, Any

from mira.tools.base import Tool


def _run_git(args: list, cwd: str = None) -> tuple:
    """运行 git 命令，返回 (stdout, stderr, returncode)"""
    cwd = cwd or os.getcwd()
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", "未找到 git 命令，请确认已安装 Git", 1
    except subprocess.TimeoutExpired:
        return "", "命令超时", 1
    except Exception as e:
        return "", str(e), 1


class GitStatusTool(Tool):
    """查看 Git 仓库状态"""

    @property
    def name(self) -> str:
        return "GitStatusTool"

    @property
    def description(self) -> str:
        return "查看 Git 仓库当前状态（已修改/已暂存/未跟踪的文件），以及当前分支信息"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"},
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        cwd = args.get("path", os.getcwd())
        stdout, stderr, code = _run_git(["status", "--short", "--branch"], cwd=cwd)
        if code != 0:
            return f"错误：{stderr or '不是 Git 仓库'}"
        return stdout or "工作区干净"


class GitDiffTool(Tool):
    """查看 Git 差异"""

    @property
    def name(self) -> str:
        return "GitDiffTool"

    @property
    def description(self) -> str:
        return "查看工作区或暂存区的代码差异。可指定文件路径和 commit/分支对比"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"},
                "file": {"type": "string", "description": "指定文件路径（可选）"},
                "staged": {"type": "boolean", "description": "是否查看已暂存的差异（默认 false）"},
                "commit": {"type": "string", "description": "与指定 commit 或分支对比"},
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        cwd = args.get("path", os.getcwd())
        git_args = ["diff"]
        if args.get("staged"):
            git_args.append("--staged")
        if args.get("commit"):
            git_args.append(args["commit"])
        if args.get("file"):
            git_args += ["--", args["file"]]

        stdout, stderr, code = _run_git(git_args, cwd=cwd)
        if code != 0:
            return f"错误：{stderr}"
        return stdout or "没有差异"


class GitLogTool(Tool):
    """查看 Git 提交历史"""

    @property
    def name(self) -> str:
        return "GitLogTool"

    @property
    def description(self) -> str:
        return "查看 Git 提交历史记录"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"},
                "n": {"type": "integer", "description": "显示最近 N 条记录，默认 10"},
                "file": {"type": "string", "description": "只显示影响该文件的提交"},
                "oneline": {"type": "boolean", "description": "单行格式显示（默认 true）"},
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        cwd = args.get("path", os.getcwd())
        n = args.get("n", 10)
        oneline = args.get("oneline", True)

        git_args = ["log", f"-{n}"]
        if oneline:
            git_args += ["--oneline", "--decorate"]
        else:
            git_args += ["--pretty=format:%h %an %ar%n  %s%n"]
        if args.get("file"):
            git_args += ["--", args["file"]]

        stdout, stderr, code = _run_git(git_args, cwd=cwd)
        if code != 0:
            return f"错误：{stderr or '不是 Git 仓库或没有提交记录'}"
        return stdout or "没有提交记录"


class GitCommitTool(Tool):
    """提交 Git 变更"""

    @property
    def name(self) -> str:
        return "GitCommitTool"

    @property
    def description(self) -> str:
        return "将变更提交到 Git 仓库。可选择先暂存指定文件（add_files）或所有变更（add_all）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "提交信息"},
                "path": {"type": "string", "description": "仓库路径，默认当前目录"},
                "add_all": {"type": "boolean", "description": "是否先执行 git add -A（默认 false）"},
                "add_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要暂存的文件列表",
                },
            },
            "required": ["message"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        cwd = args.get("path", os.getcwd())
        message = args["message"]

        # 暂存文件
        if args.get("add_all"):
            stdout, stderr, code = _run_git(["add", "-A"], cwd=cwd)
            if code != 0:
                return f"错误：git add -A 失败 - {stderr}"
        elif args.get("add_files"):
            for f in args["add_files"]:
                stdout, stderr, code = _run_git(["add", f], cwd=cwd)
                if code != 0:
                    return f"错误：git add {f} 失败 - {stderr}"

        # 提交
        stdout, stderr, code = _run_git(["commit", "-m", message], cwd=cwd)
        if code != 0:
            return f"错误：{stderr}"
        return stdout.strip()


class GitBranchTool(Tool):
    """管理 Git 分支"""

    @property
    def name(self) -> str:
        return "GitBranchTool"

    @property
    def description(self) -> str:
        return "查看、创建或切换 Git 分支"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"},
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "checkout", "delete"],
                    "description": "操作类型（默认 list）",
                },
                "name": {"type": "string", "description": "分支名称（create/checkout/delete 时需要）"},
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        cwd = args.get("path", os.getcwd())
        action = args.get("action", "list")
        name = args.get("name", "")

        if action == "list":
            stdout, stderr, code = _run_git(["branch", "-a", "--color=never"], cwd=cwd)
        elif action == "create":
            if not name:
                return "错误：create 操作需要 name 参数"
            stdout, stderr, code = _run_git(["checkout", "-b", name], cwd=cwd)
        elif action == "checkout":
            if not name:
                return "错误：checkout 操作需要 name 参数"
            stdout, stderr, code = _run_git(["checkout", name], cwd=cwd)
        elif action == "delete":
            if not name:
                return "错误：delete 操作需要 name 参数"
            stdout, stderr, code = _run_git(["branch", "-d", name], cwd=cwd)
        else:
            return f"错误：未知操作 {action}"

        if code != 0:
            return f"错误：{stderr}"
        return stdout.strip() or f"操作 {action} 成功"


class GitAddTool(Tool):
    """暂存文件（git add）"""

    @property
    def name(self) -> str:
        return "GitAddTool"

    @property
    def description(self) -> str:
        return "将文件添加到 Git 暂存区（git add）。files 为空时暂存所有变更（git add -A）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要暂存的文件列表；为空则暂存所有变更",
                },
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        cwd = args.get("path", os.getcwd())
        files = args.get("files") or []

        if files:
            for f in files:
                stdout, stderr, code = _run_git(["add", f], cwd=cwd)
                if code != 0:
                    return f"错误：git add {f} 失败 - {stderr}"
            return f"已暂存 {len(files)} 个文件"
        else:
            stdout, stderr, code = _run_git(["add", "-A"], cwd=cwd)
            if code != 0:
                return f"错误：{stderr}"
            return "已暂存所有变更（git add -A）"


class GitPushTool(Tool):
    """推送到远程仓库（git push）"""

    @property
    def name(self) -> str:
        return "GitPushTool"

    @property
    def description(self) -> str:
        return "推送当前分支到远程仓库。可指定 remote（默认 origin）和 branch（默认当前分支）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "仓库路径，默认当前目录"},
                "remote": {"type": "string", "description": "远程名称，默认 origin"},
                "branch": {"type": "string", "description": "分支名称，默认当前分支"},
                "set_upstream": {"type": "boolean", "description": "是否设置上游 (-u)，默认 false"},
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        cwd = args.get("path", os.getcwd())
        remote = args.get("remote", "origin")
        branch = args.get("branch", "")
        set_upstream = args.get("set_upstream", False)

        git_args = ["push"]
        if set_upstream:
            git_args.append("-u")
        git_args.append(remote)
        if branch:
            git_args.append(branch)

        stdout, stderr, code = _run_git(git_args, cwd=cwd)
        if code != 0:
            return f"错误：{stderr or stdout}"
        return (stdout + stderr).strip() or f"已推送到 {remote}"
