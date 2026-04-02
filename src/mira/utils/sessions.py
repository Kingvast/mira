#!/usr/bin/env python3
"""
会话持久化 - 保存和恢复对话历史
"""

import os
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

_SESSIONS_DIR = Path.home() / ".mira" / "sessions"


def _ensure_dir() -> Path:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSIONS_DIR


def save_session(session_id: str, messages: List[Dict], metadata: Dict = None) -> str:
    """保存会话"""
    d = _ensure_dir()
    meta = metadata or {}
    data = {
        "session_id": session_id,
        "created_at": meta.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat(),
        "provider": meta.get("provider", ""),
        "model": meta.get("model", ""),
        "cwd": meta.get("cwd", os.getcwd()),
        "title": meta.get("title") or _make_title(messages),
        "messages": messages,
    }
    path = d / f"{session_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_session(session_id: str) -> Optional[Dict]:
    """加载会话"""
    path = _SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_sessions(limit: int = 50) -> List[Dict]:
    """列出所有会话（按更新时间降序）"""
    if not _SESSIONS_DIR.exists():
        return []
    sessions = []
    for f in _SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data.get("session_id", f.stem),
                "title": data.get("title", "无标题"),
                "provider": data.get("provider", ""),
                "model": data.get("model", ""),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions[:limit]


def delete_session(session_id: str) -> bool:
    """删除会话"""
    path = _SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def new_session_id() -> str:
    return str(uuid.uuid4())[:8]


async def generate_title_with_ai(messages: List[Dict], api_client) -> Optional[str]:
    """用 AI 根据对话内容生成简洁的会话标题（5~15 字）"""
    if not messages or not api_client:
        return None
    # 提取前几条用户/助手消息作为上下文
    context_parts = []
    for msg in messages[:6]:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))[:200]
        if role in ("user", "assistant") and content.strip():
            label = "用户" if role == "user" else "助手"
            context_parts.append(f"{label}: {content.strip()}")
    if not context_parts:
        return None

    context = "\n".join(context_parts)
    prompt = (
        f"请根据以下对话内容生成一个简洁的标题（5~15个字，不加引号，不加标点符号结尾）：\n\n"
        f"{context}\n\n只输出标题，不要任何解释。"
    )

    try:
        parts = []
        stream = api_client.stream_message(
            [{"role": "user", "content": prompt}], [], "你是一个标题生成助手，只输出简洁标题。"
        )
        from mira.query import _parse_stream_event
        tc_buf: Dict = {}
        async for event in stream:
            text, _ = _parse_stream_event(event, tc_buf)
            if text:
                parts.append(text)
        title = "".join(parts).strip().strip('"\'。').strip()
        if 3 <= len(title) <= 30:
            return title
    except Exception:
        pass
    return None


def _make_title(messages: List[Dict]) -> str:
    import re
    for msg in messages:
        if msg.get("role") != "user":
            continue
        raw = msg.get("content", "")
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        # Skip very short messages
        if len(text) < 5:
            continue
        # Skip messages that look like tool results or system messages
        if text.startswith("[对话") or text.startswith("[tool") or text.startswith("[摘要"):
            continue
        # Take first meaningful line
        first_line = text.split("\n")[0].strip()
        if not first_line or len(first_line) < 5:
            first_line = text[:80].split("\n")[0].strip()
        # Strip markdown formatting (headers, bold, code backticks)
        first_line = re.sub(r"^#{1,6}\s+", "", first_line)
        first_line = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", first_line)
        first_line = re.sub(r"`[^`]+`", "", first_line).strip()
        # Strip @mentions
        first_line = re.sub(r"@\w+", "", first_line).strip()
        if len(first_line) < 5:
            continue
        # Limit to 60 chars
        if len(first_line) > 60:
            first_line = first_line[:57] + "…"
        return first_line
    return f"会话 {datetime.now().strftime('%m-%d %H:%M')}"
