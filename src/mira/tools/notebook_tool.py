#!/usr/bin/env python3
"""
Jupyter Notebook 工具 — 读取、编辑、执行 .ipynb 文件
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from mira.tools.base import Tool

_MAX_OUTPUT = 6000  # 单个 cell 输出最大字符数


# ══════════════════════════════════════════════════════════════════════════════
#  NotebookReadTool
# ══════════════════════════════════════════════════════════════════════════════

class NotebookReadTool(Tool):
    """读取 Jupyter Notebook (.ipynb) 文件，返回结构化内容。"""

    @property
    def name(self) -> str:
        return "NotebookRead"

    @property
    def description(self) -> str:
        return (
            "读取 Jupyter Notebook (.ipynb) 文件，以易读格式返回所有 cell 的内容、"
            "类型（code/markdown）和执行结果（outputs）。\n"
            "适合：理解 notebook 结构、分析代码逻辑、查看数据分析结果。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Notebook 文件路径（.ipynb）",
                },
                "cell_range": {
                    "type": "string",
                    "description": "要读取的 cell 范围，如 '1-5' 或 '3'（默认读取全部）",
                },
                "include_outputs": {
                    "type": "boolean",
                    "description": "是否包含 cell 的执行输出（默认 true）",
                },
            },
            "required": ["path"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = str(args.get("path", "")).strip()
        cell_range = str(args.get("cell_range", "")).strip()
        include_outputs = args.get("include_outputs", True)

        if not path:
            return "错误: path 不能为空"

        p = Path(path)
        if not p.exists():
            return f"错误: 文件不存在: {path}"
        if p.suffix.lower() != ".ipynb":
            return f"错误: 不是 .ipynb 文件: {path}"

        try:
            nb = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return f"错误: JSON 解析失败: {e}"
        except Exception as e:
            return f"错误: 无法读取文件: {e}"

        cells = nb.get("cells", [])
        total = len(cells)

        # 解析范围
        start, end = 0, total
        if cell_range:
            try:
                if "-" in cell_range:
                    s, e_ = cell_range.split("-", 1)
                    start = max(0, int(s.strip()) - 1)
                    end = min(total, int(e_.strip()))
                else:
                    idx = int(cell_range.strip()) - 1
                    start, end = max(0, idx), min(total, idx + 1)
            except ValueError:
                return f"错误: 无效的 cell_range '{cell_range}'"

        selected = cells[start:end]

        kernel = nb.get("metadata", {}).get("kernelspec", {}).get("display_name", "未知")
        lang = nb.get("metadata", {}).get("language_info", {}).get("name", "未知")

        lines = [
            f"Notebook: {p.name}",
            f"内核: {kernel}  |  语言: {lang}  |  共 {total} 个 cell",
            f"显示: {start+1}–{min(end, total)} / {total}",
            "═" * 60,
        ]

        for i, cell in enumerate(selected, start=start + 1):
            cell_type = cell.get("cell_type", "unknown")
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)

            type_label = {"code": "代码", "markdown": "Markdown", "raw": "原始"}.get(
                cell_type, cell_type
            )
            exec_count = cell.get("execution_count")
            count_str = f"[{exec_count}]" if exec_count is not None else "[ ]"

            lines.append(f"\n── Cell {i} ({type_label}) {count_str} " + "─" * 30)
            if source.strip():
                lines.append(source.rstrip())
            else:
                lines.append("（空）")

            if include_outputs and cell_type == "code":
                outputs = cell.get("outputs", [])
                if outputs:
                    lines.append("  ↳ 输出:")
                    for out in outputs:
                        out_type = out.get("output_type", "")
                        out_text = _extract_output_text(out)
                        if out_text:
                            if len(out_text) > _MAX_OUTPUT:
                                out_text = out_text[:_MAX_OUTPUT] + f"\n… (截断，共 {len(out_text):,} 字符)"
                            for line in out_text.rstrip().splitlines():
                                lines.append(f"    {line}")
                        elif out_type == "display_data":
                            lines.append("    [图形/富文本输出，无文本表示]")

        return "\n".join(lines)


def _extract_output_text(output: dict) -> str:
    """从 output dict 中提取文本内容"""
    out_type = output.get("output_type", "")

    if out_type in ("stream",):
        text = output.get("text", "")
        if isinstance(text, list):
            text = "".join(text)
        return text

    if out_type in ("execute_result", "display_data"):
        data = output.get("data", {})
        # 优先文本
        if "text/plain" in data:
            t = data["text/plain"]
            if isinstance(t, list):
                t = "".join(t)
            return t
        # HTML 退回文本
        if "text/html" in data:
            return "[HTML 输出]"

    if out_type == "error":
        ename = output.get("ename", "")
        evalue = output.get("evalue", "")
        traceback = output.get("traceback", [])
        # 去除 ANSI 颜色码
        import re
        clean_tb = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in traceback[-5:]]
        return f"{ename}: {evalue}\n" + "\n".join(clean_tb)

    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  NotebookEditTool
# ══════════════════════════════════════════════════════════════════════════════

class NotebookEditTool(Tool):
    """编辑 Jupyter Notebook：插入、替换、删除 cell，清除输出，修改 cell 源码。"""

    @property
    def name(self) -> str:
        return "NotebookEdit"

    @property
    def description(self) -> str:
        return (
            "编辑 Jupyter Notebook (.ipynb) 文件。\n"
            "操作：\n"
            "  replace_source  — 替换指定 cell 的源码（cell_index 从 1 开始）\n"
            "  insert_cell     — 在指定位置插入新 cell（before/after cell_index）\n"
            "  delete_cell     — 删除指定 cell\n"
            "  clear_outputs   — 清除所有 cell 的执行输出\n"
            "  clear_cell_output — 清除指定 cell 的输出\n"
            "  set_metadata    — 更新 notebook 顶层 metadata\n"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Notebook 文件路径（.ipynb）",
                },
                "action": {
                    "type": "string",
                    "description": (
                        "操作类型: replace_source / insert_cell / delete_cell / "
                        "clear_outputs / clear_cell_output / set_metadata"
                    ),
                },
                "cell_index": {
                    "type": "integer",
                    "description": "Cell 序号（从 1 开始）",
                },
                "source": {
                    "type": "string",
                    "description": "新 cell 的源码或替换内容",
                },
                "cell_type": {
                    "type": "string",
                    "description": "插入 cell 的类型：code（默认）/ markdown / raw",
                },
                "insert_position": {
                    "type": "string",
                    "description": "插入位置：before / after（默认 after）",
                },
                "metadata": {
                    "type": "object",
                    "description": "要设置的 metadata 字段（set_metadata 时使用）",
                },
            },
            "required": ["path", "action"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        path = str(args.get("path", "")).strip()
        action = str(args.get("action", "")).strip().lower()

        if not path:
            return "错误: path 不能为空"
        if not action:
            return "错误: action 不能为空"

        p = Path(path)
        if not p.exists():
            return f"错误: 文件不存在: {path}"
        if p.suffix.lower() != ".ipynb":
            return f"错误: 不是 .ipynb 文件: {path}"

        try:
            nb = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return f"错误: 无法读取文件: {e}"

        cells = nb.setdefault("cells", [])

        if action == "replace_source":
            return self._replace_source(nb, cells, args, p)
        elif action == "insert_cell":
            return self._insert_cell(nb, cells, args, p)
        elif action == "delete_cell":
            return self._delete_cell(nb, cells, args, p)
        elif action == "clear_outputs":
            return self._clear_all_outputs(nb, cells, p)
        elif action == "clear_cell_output":
            return self._clear_cell_output(nb, cells, args, p)
        elif action == "set_metadata":
            return self._set_metadata(nb, args, p)
        else:
            return (
                f"错误: 未知操作 '{action}'。"
                "可选: replace_source / insert_cell / delete_cell / "
                "clear_outputs / clear_cell_output / set_metadata"
            )

    # ── 操作实现 ──────────────────────────────────────────────────────────────

    def _replace_source(self, nb, cells, args, p: Path) -> str:
        idx = args.get("cell_index")
        source = args.get("source")
        if idx is None:
            return "错误: replace_source 需要 cell_index"
        if source is None:
            return "错误: replace_source 需要 source"
        i = int(idx) - 1
        if i < 0 or i >= len(cells):
            return f"错误: cell_index {idx} 超出范围（共 {len(cells)} 个 cell）"
        cells[i]["source"] = source
        # 清除执行计数和输出（已修改）
        cells[i]["execution_count"] = None
        cells[i]["outputs"] = []
        self._save(nb, p)
        return f"✓ Cell {idx} 源码已更新，执行计数和输出已清除"

    def _insert_cell(self, nb, cells, args, p: Path) -> str:
        source = args.get("source", "")
        cell_type = str(args.get("cell_type", "code")).lower()
        idx = args.get("cell_index", len(cells))
        position = str(args.get("insert_position", "after")).lower()

        if cell_type not in ("code", "markdown", "raw"):
            return f"错误: cell_type 必须是 code / markdown / raw"

        new_cell: Dict[str, Any] = {
            "cell_type": cell_type,
            "metadata": {},
            "source": source,
        }
        if cell_type == "code":
            new_cell["execution_count"] = None
            new_cell["outputs"] = []

        i = int(idx) - 1
        if position == "before":
            insert_at = max(0, i)
        else:
            insert_at = min(len(cells), i + 1)

        cells.insert(insert_at, new_cell)
        self._save(nb, p)
        return f"✓ 已在位置 {insert_at + 1} 插入 {cell_type} cell（共 {len(cells)} 个）"

    def _delete_cell(self, nb, cells, args, p: Path) -> str:
        idx = args.get("cell_index")
        if idx is None:
            return "错误: delete_cell 需要 cell_index"
        i = int(idx) - 1
        if i < 0 or i >= len(cells):
            return f"错误: cell_index {idx} 超出范围（共 {len(cells)} 个 cell）"
        removed = cells.pop(i)
        self._save(nb, p)
        src_preview = str(removed.get("source", ""))[:60].replace("\n", " ")
        return f"✓ 已删除 Cell {idx}：{src_preview}…"

    def _clear_all_outputs(self, nb, cells, p: Path) -> str:
        count = 0
        for cell in cells:
            if cell.get("cell_type") == "code":
                cell["outputs"] = []
                cell["execution_count"] = None
                count += 1
        self._save(nb, p)
        return f"✓ 已清除 {count} 个代码 cell 的输出和执行计数"

    def _clear_cell_output(self, nb, cells, args, p: Path) -> str:
        idx = args.get("cell_index")
        if idx is None:
            return "错误: clear_cell_output 需要 cell_index"
        i = int(idx) - 1
        if i < 0 or i >= len(cells):
            return f"错误: cell_index {idx} 超出范围"
        cells[i]["outputs"] = []
        cells[i]["execution_count"] = None
        self._save(nb, p)
        return f"✓ 已清除 Cell {idx} 的输出"

    def _set_metadata(self, nb, args, p: Path) -> str:
        metadata = args.get("metadata")
        if not metadata or not isinstance(metadata, dict):
            return "错误: set_metadata 需要 metadata 参数（JSON 对象）"
        nb.setdefault("metadata", {}).update(metadata)
        self._save(nb, p)
        keys = ", ".join(metadata.keys())
        return f"✓ 已更新 notebook metadata: {keys}"

    @staticmethod
    def _save(nb: dict, p: Path) -> None:
        p.write_text(
            json.dumps(nb, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
