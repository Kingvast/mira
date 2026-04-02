#!/usr/bin/env python3
"""
文件与目录操作工具
"""

import os
import glob
import re
import shutil
import difflib
from pathlib import Path
from typing import List, Dict, Any, Optional

from mira.tools.base import Tool


class FileReadTool(Tool):
    """读取文件内容，支持多种格式和行范围"""

    @property
    def name(self) -> str:
        return "FileReadTool"

    @property
    def description(self) -> str:
        return "读取文件内容（文本、PDF、Jupyter Notebook）。支持指定行范围 start_line/end_line，PDF 支持 pages 参数如 '1-5'"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径"},
                "start_line": {"type": "integer", "description": "起始行（从 1 开始）"},
                "end_line": {"type": "integer", "description": "结束行"},
                "pages": {"type": "string", "description": "PDF 页面范围，如 '1-5'"},
            },
            "required": ["path"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = args.get("path", "")
        start_line = args.get("start_line", 1)
        end_line = args.get("end_line")
        pages = args.get("pages")

        try:
            if os.path.isdir(path):
                return LSTool().execute({"path": path})

            ext = Path(path).suffix.lower()

            if ext == ".pdf":
                return self._read_pdf(path, pages)
            elif ext == ".ipynb":
                return self._read_notebook(path)
            else:
                return self._read_text(path, start_line, end_line)
        except FileNotFoundError:
            return f"错误：文件不存在 - {path}"
        except Exception as e:
            return f"错误：{e}"

    def _read_text(self, path: str, start_line: int, end_line: Optional[int]) -> str:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        s = max(0, (start_line or 1) - 1)
        e = end_line if end_line else total
        selected = lines[s:e]
        # 带行号输出
        result = []
        for i, line in enumerate(selected, start=s + 1):
            result.append(f"{i}\t{line}")
        return "".join(result) or "(空文件)"

    def _read_pdf(self, path: str, pages: Optional[str]) -> str:
        try:
            import PyPDF2
        except ImportError:
            return "错误：读取 PDF 需要安装 PyPDF2，运行: pip install PyPDF2"
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total = len(reader.pages)
            if pages:
                parts = pages.split("-")
                s = max(0, int(parts[0]) - 1)
                e = int(parts[1]) if len(parts) > 1 else s + 1
            else:
                s, e = 0, total
            out = [f"PDF 文件: {path}  (共 {total} 页，显示 {s+1}-{e} 页)\n"]
            for i in range(s, min(e, total)):
                out.append(f"--- 第 {i+1} 页 ---\n{reader.pages[i].extract_text()}\n")
            return "\n".join(out)

    def _read_notebook(self, path: str) -> str:
        import json
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        cells = nb.get("cells", [])
        out = [f"Jupyter Notebook: {path}  ({len(cells)} 个单元格)\n"]
        for i, cell in enumerate(cells, 1):
            ct = cell.get("cell_type", "unknown")
            src = "".join(cell.get("source", []))
            out.append(f"[{i}] {ct.upper()}\n{src}\n")
            outputs = cell.get("outputs", [])
            for o in outputs:
                if o.get("output_type") in ("stream", "execute_result", "display_data"):
                    text = "".join(o.get("text", o.get("data", {}).get("text/plain", [])))
                    if text:
                        out.append(f"输出: {text}\n")
        return "\n".join(out)


class FileEditTool(Tool):
    """精确字符串替换编辑文件"""

    @property
    def name(self) -> str:
        return "FileEditTool"

    @property
    def description(self) -> str:
        return "精确字符串替换编辑文件内容。old_string 必须在文件中唯一存在。支持 replace_all=true 替换所有匹配项"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "要替换的字符串"},
                "new_string": {"type": "string", "description": "替换后的新字符串"},
                "replace_all": {"type": "boolean", "description": "是否替换所有匹配项（默认 false）"},
            },
            "required": ["path", "old_string", "new_string"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = args["path"]
        old_string = args["old_string"]
        new_string = args["new_string"]
        replace_all = args.get("replace_all", False)

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_string not in content:
                return f"错误：在文件 {path} 中未找到目标字符串"

            count = content.count(old_string)
            if count > 1 and not replace_all:
                return (f"错误：目标字符串在文件中出现了 {count} 次，请提供更多上下文确保唯一性，"
                        f"或设置 replace_all=true 替换全部")

            new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            replaced = count if replace_all else 1
            return f"已成功替换 {replaced} 处"
        except FileNotFoundError:
            return f"错误：文件不存在 - {path}"
        except Exception as e:
            return f"错误：{e}"


class FileWriteTool(Tool):
    """创建或覆盖写入文件"""

    @property
    def name(self) -> str:
        return "FileWriteTool"

    @property
    def description(self) -> str:
        return "创建新文件或覆盖写入文件内容。会自动创建所需的父目录"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = args["path"]
        content = args["content"]
        try:
            parent = Path(path).parent
            if parent:
                parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            return f"已写入文件 {path}（{lines} 行，{len(content)} 字节）"
        except Exception as e:
            return f"错误：{e}"


class LSTool(Tool):
    """列出目录内容"""

    @property
    def name(self) -> str:
        return "LSTool"

    @property
    def description(self) -> str:
        return "列出目录内容，显示文件大小、修改时间和类型。支持 ignore 参数过滤"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认为当前目录"},
                "ignore": {"type": "array", "items": {"type": "string"}, "description": "忽略的文件名或模式列表"},
                "all": {"type": "boolean", "description": "是否显示隐藏文件（默认 false）"},
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = args.get("path", ".")
        ignore = set(args.get("ignore") or [])
        show_all = args.get("all", False)

        try:
            if not os.path.exists(path):
                return f"错误：路径不存在 - {path}"
            if not os.path.isdir(path):
                return f"错误：不是目录 - {path}"

            items = []
            for name in sorted(os.listdir(path)):
                if not show_all and name.startswith("."):
                    continue
                if name in ignore:
                    continue
                full = os.path.join(path, name)
                is_dir = os.path.isdir(full)
                try:
                    size = os.path.getsize(full) if not is_dir else 0
                    mtime = os.path.getmtime(full)
                    import datetime
                    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
                except Exception:
                    size, mtime_str = 0, "???"
                display_name = name + "/" if is_dir else name
                size_str = "-" if is_dir else _fmt_size(size)
                items.append(f"{'📁' if is_dir else '📄'}  {display_name:<40} {size_str:>8}  {mtime_str}")

            header = f"目录: {os.path.abspath(path)}  ({len(items)} 项)\n"
            return header + "\n".join(items) if items else header + "(空目录)"
        except PermissionError:
            return f"错误：没有权限访问 - {path}"
        except Exception as e:
            return f"错误：{e}"


class MkdirTool(Tool):
    """创建目录"""

    @property
    def name(self) -> str:
        return "MkdirTool"

    @property
    def description(self) -> str:
        return "创建目录（含所有必要的父目录）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要创建的目录路径"},
            },
            "required": ["path"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = args["path"]
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return f"已创建目录: {os.path.abspath(path)}"
        except Exception as e:
            return f"错误：{e}"


class DeleteTool(Tool):
    """删除文件或目录"""

    @property
    def name(self) -> str:
        return "DeleteTool"

    @property
    def description(self) -> str:
        return "删除文件或目录（目录会递归删除）。请谨慎使用！"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的文件或目录路径"},
            },
            "required": ["path"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = args["path"]
        try:
            if not os.path.exists(path):
                return f"错误：路径不存在 - {path}"
            abs_path = os.path.abspath(path)
            cwd = os.path.abspath(os.getcwd())
            # 安全检查：不允许删除工作目录本身或其父目录
            if cwd.startswith(abs_path) or abs_path == cwd:
                return "错误：不允许删除当前工作目录或其父目录"
            if os.path.isdir(path):
                shutil.rmtree(path)
                return f"已删除目录: {path}"
            else:
                os.remove(path)
                return f"已删除文件: {path}"
        except Exception as e:
            return f"错误：{e}"


class MoveTool(Tool):
    """移动或重命名文件/目录"""

    @property
    def name(self) -> str:
        return "MoveTool"

    @property
    def description(self) -> str:
        return "移动或重命名文件/目录。src/source=源路径，dst/destination=目标路径"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源路径（也接受 source）"},
                "dst": {"type": "string", "description": "目标路径（也接受 destination / target）"},
            },
            "required": ["src", "dst"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        # 兼容 AI 可能使用的多种参数名
        src = (args.get("src") or args.get("source") or args.get("from") or "").strip()
        dst = (args.get("dst") or args.get("destination") or args.get("target") or args.get("to") or "").strip()
        try:
            if not src:
                return "错误：缺少源路径参数（src）"
            if not dst:
                return "错误：缺少目标路径参数（dst）"
            if not os.path.exists(src):
                return f"错误：源路径不存在 - {src}"
            abs_src = os.path.abspath(src)
            abs_dst = os.path.abspath(dst)
            if abs_src == abs_dst:
                return "错误：源路径和目标路径相同"
            # 防止把目录移动到自身的子目录
            if os.path.isdir(abs_src) and abs_dst.startswith(abs_src + os.sep):
                return "错误：不能将目录移动到自身的子目录"
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
            return f"已移动: {src} → {dst}"
        except PermissionError as e:
            return f"错误：权限不足 - {e}"
        except Exception as e:
            return f"错误：{e}"


class CopyTool(Tool):
    """复制文件或目录"""

    @property
    def name(self) -> str:
        return "CopyTool"

    @property
    def description(self) -> str:
        return "复制文件或目录（目录会递归复制）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "源路径"},
                "dst": {"type": "string", "description": "目标路径"},
            },
            "required": ["src", "dst"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        src = args["src"]
        dst = args["dst"]
        try:
            if not os.path.exists(src):
                return f"错误：源路径不存在 - {src}"
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return f"已复制: {src} → {dst}"
        except Exception as e:
            return f"错误：{e}"


class GlobTool(Tool):
    """按文件名模式匹配文件"""

    @property
    def name(self) -> str:
        return "GlobTool"

    @property
    def description(self) -> str:
        return "按 glob 模式匹配文件，如 **/*.py、src/**/*.ts"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "glob 模式"},
                "path": {"type": "string", "description": "搜索根目录，默认当前目录"},
            },
            "required": ["pattern"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        pattern = args["pattern"]
        path = args.get("path", ".")
        try:
            full_pattern = os.path.join(path, pattern)
            files = sorted(glob.glob(full_pattern, recursive=True))
            if not files:
                return f"未找到匹配 {pattern!r} 的文件"
            return "\n".join(files) + f"\n\n共 {len(files)} 个文件"
        except Exception as e:
            return f"错误：{e}"


class GrepTool(Tool):
    """在文件内容中搜索正则表达式"""

    @property
    def name(self) -> str:
        return "GrepTool"

    @property
    def description(self) -> str:
        return "在文件中搜索正则表达式，返回匹配行（含行号和文件路径）"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "正则表达式"},
                "path": {"type": "string", "description": "搜索目录，默认当前目录"},
                "glob": {"type": "string", "description": "文件名过滤，如 *.py"},
                "case_insensitive": {"type": "boolean", "description": "是否忽略大小写"},
                "context": {"type": "integer", "description": "上下文行数"},
            },
            "required": ["pattern"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        pattern = args["pattern"]
        path = args.get("path", ".")
        glob_pattern = args.get("glob", "*")
        case_insensitive = args.get("case_insensitive", False)
        context_lines = args.get("context", 0)

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            compiled = re.compile(pattern, flags)
        except re.error as e:
            return f"错误：无效的正则表达式 - {e}"

        matches = []
        try:
            for root, dirs, files in os.walk(path):
                # 跳过隐藏目录和常见忽略目录
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git", "dist", "build")]
                for filename in files:
                    if not glob.fnmatch.fnmatch(filename, glob_pattern):
                        continue
                    fpath = os.path.join(root, filename)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()
                        for i, line in enumerate(lines, 1):
                            if compiled.search(line):
                                entry = [f"{fpath}:{i}: {line.rstrip()}"]
                                if context_lines:
                                    before = lines[max(0, i - 1 - context_lines): i - 1]
                                    after = lines[i: min(len(lines), i + context_lines)]
                                    entry = (
                                        [f"{fpath}:{j+1}- {l.rstrip()}" for j, l in enumerate(before, i - 1 - len(before))]
                                        + [f"{fpath}:{i}: {line.rstrip()}"]
                                        + [f"{fpath}:{j+1}- {l.rstrip()}" for j, l in enumerate(after, i)]
                                    )
                                matches.extend(entry)
                    except Exception:
                        continue
        except Exception as e:
            return f"错误：{e}"

        if not matches:
            return f"未找到匹配 {pattern!r} 的内容"
        result = "\n".join(matches[:500])
        if len(matches) > 500:
            result += f"\n... （共 {len(matches)} 处匹配，仅显示前 500 条）"
        return result


class DiffTool(Tool):
    """显示两个文件的差异"""

    @property
    def name(self) -> str:
        return "DiffTool"

    @property
    def description(self) -> str:
        return "比较两个文件的差异，输出 unified diff 格式"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path_a": {"type": "string", "description": "文件 A 路径"},
                "path_b": {"type": "string", "description": "文件 B 路径"},
                "context": {"type": "integer", "description": "上下文行数，默认 3"},
            },
            "required": ["path_a", "path_b"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path_a = args["path_a"]
        path_b = args["path_b"]
        context = args.get("context", 3)
        try:
            with open(path_a, "r", encoding="utf-8") as f:
                lines_a = f.readlines()
            with open(path_b, "r", encoding="utf-8") as f:
                lines_b = f.readlines()
            diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=path_a, tofile=path_b, n=context))
            if not diff:
                return "文件内容完全相同"
            return "".join(diff)
        except FileNotFoundError as e:
            return f"错误：{e}"
        except Exception as e:
            return f"错误：{e}"


class FileAppendTool(Tool):
    """向文件末尾追加内容"""

    @property
    def name(self) -> str:
        return "FileAppendTool"

    @property
    def description(self) -> str:
        return "向已有文件末尾追加内容（不覆盖原文件）。文件不存在则自动创建"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要追加的内容"},
                "newline": {"type": "boolean", "description": "追加前是否换行（默认 true）"},
            },
            "required": ["path", "content"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = args["path"]
        content = args["content"]
        newline = args.get("newline", True)
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            prefix = "\n" if newline and p.exists() and p.stat().st_size > 0 else ""
            with open(path, "a", encoding="utf-8") as f:
                f.write(prefix + content)
            return f"已追加 {len(content)} 字符到 {path}"
        except Exception as e:
            return f"错误：{e}"


class NotesWriteTool(Tool):
    """读写项目笔记 NOTES.md"""

    @property
    def name(self) -> str:
        return "NotesWriteTool"

    @property
    def description(self) -> str:
        return (
            "读取或更新项目笔记文件 NOTES.md（AI 持久化记忆）。\n"
            "action:\n"
            "  read   — 读取当前笔记内容\n"
            "  write  — 完全覆盖写入笔记\n"
            "  append — 在末尾追加一条记录（带时间戳）"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "append"],
                    "description": "操作类型",
                },
                "content": {"type": "string", "description": "写入或追加的内容（write/append 时必填）"},
                "category": {"type": "string", "description": "追加时的分类标题（默认: 笔记）"},
            },
            "required": ["action"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        from mira.utils.memory import load_notes, save_notes, append_note, get_notes_path

        action = args.get("action", "read")
        content = args.get("content", "")
        category = args.get("category", "笔记")

        if action == "read":
            notes = load_notes()
            path = get_notes_path()
            if not notes:
                return "NOTES.md 为空或不存在。可用 /init 初始化，或用 action=write 写入内容"
            return f"[{path}]\n{'─'*40}\n{notes}"

        elif action == "write":
            if not content:
                return "错误：write 操作需要 content 参数"
            save_notes(content)
            return f"✓ NOTES.md 已更新（{len(content)} 字符）"

        elif action == "append":
            if not content:
                return "错误：append 操作需要 content 参数"
            append_note(content, category)
            return f"✓ 已追加到 NOTES.md [{category}]"

        return f"错误：未知操作 {action}"


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _fmt_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
