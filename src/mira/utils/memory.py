#!/usr/bin/env python3
"""
记忆系统 - 多层级 NOTES.md 加载

加载优先级（从高到低）：
1. <cwd>/NOTES.md
2. 父目录向上递归（直到文件系统根）
3. 用户全局 ~/.mira/memory/*.md 和 ~/.mira/NOTES.md
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

_NOTES_FILENAME  = "NOTES.md"
_CLAUDE_FILENAME = "CLAUDE.md"      # Claude Code 标准记忆文件（兼容）
_GLOBAL_DIR      = Path.home() / ".mira"
_GLOBAL_MEMORY   = _GLOBAL_DIR / "memory"


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def load_memory_sources() -> List[Dict]:
    """
    按优先级加载所有记忆来源。
    返回 [{path, content, level}] 列表。
    """
    sources: List[Dict] = []
    seen: set = set()

    # 1. 当前目录向上递归查找 NOTES.md / CLAUDE.md / .claude/memory/*.md
    current = Path.cwd().resolve()
    level = 0
    while True:
        # NOTES.md（本项目标准）
        for fname in (_NOTES_FILENAME, _CLAUDE_FILENAME):
            p = current / fname
            if p.exists() and p.is_file() and str(p) not in seen:
                content = _read_file(p)
                if content.strip():
                    sources.append({"path": p, "content": content, "level": level})
                    seen.add(str(p))
        # .claude/memory/*.md（Claude Code 兼容格式）
        claude_mem = current / ".claude" / "memory"
        if claude_mem.is_dir():
            for md in sorted(claude_mem.glob("*.md")):
                if str(md) not in seen:
                    content = _read_file(md)
                    if content.strip():
                        sources.append({"path": md, "content": content, "level": level + 0.5})
                        seen.add(str(md))
        level += 1
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 2. 用户全局内存目录 ~/.mira/memory/*.md
    if _GLOBAL_MEMORY.is_dir():
        for md in sorted(_GLOBAL_MEMORY.glob("*.md")):
            if str(md) not in seen:
                content = _read_file(md)
                if content.strip():
                    sources.append({"path": md, "content": content, "level": 100})
                    seen.add(str(md))

    # 3. 配置的全局记忆路径（config.json notes_path 或默认 ~/.mira/NOTES.md）
    try:
        global_notes = _get_configured_global_path()
    except Exception:
        global_notes = _GLOBAL_DIR / _NOTES_FILENAME
    if global_notes.exists() and str(global_notes) not in seen:
        content = _read_file(global_notes)
        if content.strip():
            sources.append({"path": global_notes, "content": content, "level": 101})

    return sources


def load_memory() -> str:
    """合并所有记忆来源为单一字符串（供系统提示使用）"""
    sources = load_memory_sources()
    if not sources:
        return ""
    if len(sources) == 1:
        return sources[0]["content"]
    parts = []
    for src in sources:
        try:
            rel = str(src["path"].relative_to(Path.home()))
        except ValueError:
            rel = str(src["path"])
        parts.append(f"<!-- {rel} -->\n{src['content']}")
    return "\n\n---\n\n".join(parts)


def _get_configured_global_path() -> Path:
    """读取 config.json 中的 notes_path 配置，未配置则返回默认路径"""
    try:
        from mira.utils.config import load_config
        cfg = load_config()
        custom = cfg.get("notes_path", "").strip()
        if custom:
            p = Path(custom).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return _GLOBAL_DIR / _NOTES_FILENAME


def save_memory(content: str, path: Optional[Path] = None):
    """保存记忆内容"""
    if path is None:
        local = Path.cwd() / _NOTES_FILENAME
        if local.exists():
            path = local
        else:
            path = _get_configured_global_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def get_memory_path() -> Optional[Path]:
    """获取当前最优先的记忆文件路径"""
    sources = load_memory_sources()
    return sources[0]["path"] if sources else None


def append_note(entry: str, category: str = "笔记"):
    """追加一条笔记到当前最优先的记忆文件"""
    current = load_memory()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"\n## [{timestamp}] {category}\n{entry}\n"
    save_memory(current + new_entry)


def init_notes(project_name: str = "", description: str = "") -> str:
    """在当前目录创建 NOTES.md"""
    content = f"""# 项目笔记

> 此文件由 Mira 维护，记录项目上下文、规范和重要信息。
> AI 助手每次对话都会读取此文件，请在此记录重要约定。

## 项目信息
- 项目名称: {project_name or Path.cwd().name}
- 描述: {description or ""}
- 创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
- 工作目录: {os.getcwd()}

## 技术栈


## 代码规范


## 重要约定


## 历史记录
"""
    target = Path.cwd() / _NOTES_FILENAME
    target.write_text(content, encoding="utf-8")
    return str(target)


# ── 向后兼容别名 ─────────────────────────────────────────────────────────────
load_notes     = load_memory
save_notes     = save_memory
append_memory  = append_note
get_notes_path = get_memory_path
