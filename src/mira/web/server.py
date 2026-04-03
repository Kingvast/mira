#!/usr/bin/env python3
"""
FastAPI Web 服务器 - Mira Web UI
"""

import os
import json
import asyncio
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    raise ImportError("Web UI 需要安装依赖：pip install fastapi uvicorn[standard] websockets")

from mira.utils.config import (
    load_config, save_config, get_api_key, get_default_model,
    get_models, get_providers, get_config_for_display, get_provider_base_url,
    add_custom_provider, remove_custom_provider, PROVIDER_DEFAULTS,
)

# ─── 辅助：持久化 extra_dirs 到配置文件 ──────────────────────────────────────

def _persist_extra_dirs(dirs: list):
    """将额外目录列表写回 config.json"""
    cfg = load_config()
    cfg["extra_dirs"] = dirs
    save_config(cfg)


from mira.utils.sessions import (
    list_sessions, delete_session, load_session, save_session, new_session_id,
)
from mira.utils.memory import load_memory, save_memory, get_memory_path
from mira import __version__

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Mira", version=__version__, docs_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── 页面路由 ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = STATIC_DIR / "index.html"
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


# ─── 配置 API ─────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    config = load_config()
    return get_config_for_display(config)


class ConfigUpdateRequest(BaseModel):
    key: str
    value: Any


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    config = load_config()
    config[req.key] = req.value
    save_config(config)
    return {"ok": True, "message": f"已更新配置 {req.key}"}


class ProviderConfigRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


@app.post("/api/config/provider")
async def update_provider_config(req: ProviderConfigRequest):
    config = load_config()
    if req.api_key is not None:
        config[f"{req.provider}_api_key"] = req.api_key
    if req.model is not None:
        config.setdefault("provider_selected_models", {})[req.provider] = req.model
    if req.base_url is not None:
        config.setdefault("provider_base_urls", {})[req.provider] = req.base_url
    save_config(config)
    return {"ok": True}


# ─── 提供商 & 模型 API ────────────────────────────────────────────────────────

@app.get("/api/providers")
async def api_get_providers():
    config = load_config()
    result = []
    for p in get_providers(config):
        pid = p["id"]
        key = get_api_key(pid, config)
        result.append({
            **p,
            "has_key": bool(key),
            "models": get_models(pid, config),
        })
    return result


class CustomProviderRequest(BaseModel):
    id: str
    name: str
    base_url: str
    api_key: str
    models: List[str] = []


@app.post("/api/providers/custom")
async def api_add_custom_provider(req: CustomProviderRequest):
    if not req.id or not req.base_url:
        raise HTTPException(400, "id 和 base_url 不能为空")
    if req.id in PROVIDER_DEFAULTS:
        raise HTTPException(400, f"'{req.id}' 是内置提供商 ID，请换一个名字")
    config = load_config()
    add_custom_provider(req.id, req.name, req.base_url, req.api_key, req.models, config)
    save_config(config)
    return {"ok": True}


@app.delete("/api/providers/custom/{provider_id}")
async def api_remove_custom_provider(provider_id: str):
    config = load_config()
    ok = remove_custom_provider(provider_id, config)
    if not ok:
        raise HTTPException(404, f"自定义提供商不存在: {provider_id}")
    save_config(config)
    return {"ok": True}


@app.get("/api/models/{provider}")
async def api_get_models(provider: str):
    config = load_config()
    return get_models(provider, config)


# ─── 会话 API ─────────────────────────────────────────────────────────────────

@app.get("/api/sessions")
async def api_list_sessions():
    return list_sessions()


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    ok = delete_session(session_id)
    if not ok:
        raise HTTPException(404, "会话不存在")
    return {"ok": True}


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    data = load_session(session_id)
    if not data:
        raise HTTPException(404, "会话不存在")
    return data


# ─── 文件浏览 API ─────────────────────────────────────────────────────────────

@app.get("/api/files")
async def api_list_files(path: str = "."):
    try:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            raise HTTPException(404, f"路径不存在: {path}")
        if not os.path.isdir(abs_path):
            raise HTTPException(400, f"不是目录: {path}")

        items = []
        for name in sorted(os.listdir(abs_path)):
            full = os.path.join(abs_path, name)
            is_dir = os.path.isdir(full)
            try:
                size = os.path.getsize(full) if not is_dir else 0
                mtime = os.path.getmtime(full)
            except Exception:
                size, mtime = 0, 0
            items.append({
                "name": name,
                "path": full,
                "is_dir": is_dir,
                "size": size,
                "mtime": mtime,
            })
        return {"path": abs_path, "items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/files/read")
async def api_read_file(path: str):
    try:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            raise HTTPException(404, "文件不存在")
        if os.path.isdir(abs_path):
            raise HTTPException(400, "是目录而非文件")
        content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
        return {"path": abs_path, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


class WriteFileRequest(BaseModel):
    path: str
    content: str


@app.post("/api/files/write")
async def api_write_file(req: WriteFileRequest):
    try:
        abs_path = os.path.abspath(req.path)
        Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
        Path(abs_path).write_text(req.content, encoding="utf-8")
        return {"ok": True, "path": abs_path}
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── 额外目录 REST API（持久化，无需 WebSocket）────────────────────────────────

@app.get("/api/extra_dirs")
async def api_get_extra_dirs():
    cfg = load_config()
    dirs = [d for d in cfg.get("extra_dirs", []) if os.path.isdir(d)]
    return {"extra_dirs": dirs}


class ExtraDirsRequest(BaseModel):
    dirs: List[str]


@app.post("/api/extra_dirs")
async def api_set_extra_dirs(req: ExtraDirsRequest):
    valid = [d for d in req.dirs if os.path.isdir(d)]
    _persist_extra_dirs(valid)
    return {"ok": True, "extra_dirs": valid}


# ─── 工作目录 API ────────────────────────────────────────────────────────────

@app.get("/api/cwd")
async def api_get_cwd():
    return {"cwd": os.getcwd()}


class SetCwdRequest(BaseModel):
    path: str


@app.post("/api/cwd")
async def api_set_cwd(req: SetCwdRequest):
    path = os.path.abspath(req.path)
    if not os.path.isdir(path):
        raise HTTPException(400, f"不是有效目录: {path}")
    try:
        os.chdir(path)
        return {"ok": True, "cwd": os.getcwd()}
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── 记忆 API ─────────────────────────────────────────────────────────────────

@app.get("/api/memory")
async def api_get_memory():
    content = load_memory()
    path = get_memory_path()
    return {"content": content, "path": str(path) if path else None}


class SaveMemoryRequest(BaseModel):
    content: str
    path: Optional[str] = None


@app.post("/api/memory")
async def api_save_memory(req: SaveMemoryRequest):
    if req.path:
        from pathlib import Path as _Path
        save_memory(req.content, _Path(req.path))
    else:
        save_memory(req.content)
    return {"ok": True}


class AppendMemoryRequest(BaseModel):
    text: str
    category: str = "笔记"


@app.post("/api/memory/append")
async def api_append_memory(req: AppendMemoryRequest):
    from mira.utils.memory import append_note
    append_note(req.text, req.category)
    return {"ok": True}


@app.get("/api/memory/sources")
async def api_memory_sources():
    from mira.utils.memory import load_memory_sources
    sources = load_memory_sources()
    return [{"path": str(s["path"]), "level": s["level"],
              "size": len(s["content"]), "preview": s["content"][:120]} for s in sources]


@app.post("/api/memory/init")
async def api_memory_init():
    from mira.utils.memory import init_notes
    path = init_notes()
    return {"ok": True, "path": path}


# ─── Skills API ──────────────────────────────────────────────────────────────

@app.get("/api/skills")
async def api_list_skills():
    from mira.services.skills import list_skills
    return list_skills()


@app.get("/api/skills/{name}")
async def api_get_skill(name: str):
    from mira.services.skills import get_skill
    s = get_skill(name)
    if not s:
        raise HTTPException(404, f"技能不存在: {name}")
    return s


class SaveSkillRequest(BaseModel):
    name: str
    description: str
    prompt: str


@app.post("/api/skills")
async def api_save_skill(req: SaveSkillRequest):
    from mira.services.skills import save_user_skill
    try:
        path = save_user_skill(req.name, req.description, req.prompt)
        return {"ok": True, "path": path}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/skills/{name}")
async def api_delete_skill(name: str):
    from mira.services.skills import delete_user_skill
    ok = delete_user_skill(name)
    if not ok:
        raise HTTPException(404, "技能不存在或为内置技能")
    return {"ok": True}


# ─── 文件上传 API ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def api_upload_files(files: List[UploadFile] = File(...)):
    """上传文件，返回文件内容（文本）或 base64（图片）"""
    results = []
    IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    MAX_TEXT_SIZE = 500_000  # 500KB text limit
    MAX_IMAGE_SIZE = 5_000_000  # 5MB image limit

    for f in files:
        content_type = f.content_type or ""
        data = await f.read()
        if content_type in IMAGE_TYPES or f.filename.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp"):
            if len(data) > MAX_IMAGE_SIZE:
                results.append({"name": f.filename, "error": "图片超过 5MB 限制"})
                continue
            b64 = base64.b64encode(data).decode()
            mime = content_type if content_type in IMAGE_TYPES else "image/png"
            results.append({"name": f.filename, "type": "image", "data": b64, "media_type": mime})
        else:
            if len(data) > MAX_TEXT_SIZE:
                data = data[:MAX_TEXT_SIZE]
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                text = data.decode("latin-1", errors="replace")
            results.append({"name": f.filename, "type": "text", "content": text})
    return results


# ─── MCP API ──────────────────────────────────────────────────────────────────

@app.get("/api/mcp")
async def api_list_mcp():
    """列出 MCP 服务器配置"""
    cfg_path = Path.home() / ".mira" / "mcp.json"
    if not cfg_path.exists():
        return {"servers": []}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {"servers": []}


class MCPServerConfig(BaseModel):
    name: str
    description: str = ""
    command: str
    args: List[str] = []


@app.post("/api/mcp")
async def api_add_mcp_server(req: MCPServerConfig):
    cfg_path = Path.home() / ".mira" / "mcp.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = {"servers": []}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg.setdefault("servers", [])
    cfg["servers"] = [s for s in cfg["servers"] if s.get("name") != req.name]
    cfg["servers"].append(req.model_dump())
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.delete("/api/mcp/{name}")
async def api_delete_mcp_server(name: str):
    cfg_path = Path.home() / ".mira" / "mcp.json"
    if not cfg_path.exists():
        raise HTTPException(404, "服务器不存在")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    before = len(cfg.get("servers", []))
    cfg["servers"] = [s for s in cfg.get("servers", []) if s.get("name") != name]
    if len(cfg["servers"]) == before:
        raise HTTPException(404, "服务器不存在")
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


# ─── Git 状态 API ─────────────────────────────────────────────────────────────

@app.get("/api/git/status")
async def api_git_status():
    import subprocess as _sp
    try:
        branch = _sp.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=os.getcwd(), stderr=_sp.DEVNULL, timeout=5,
            encoding="utf-8", errors="replace"
        ).strip()
        status = _sp.check_output(
            ["git", "status", "--porcelain"],
            cwd=os.getcwd(), stderr=_sp.DEVNULL, timeout=5,
            encoding="utf-8", errors="replace"
        )
        log = _sp.check_output(
            ["git", "log", "--oneline", "-5"],
            cwd=os.getcwd(), stderr=_sp.DEVNULL, timeout=5,
            encoding="utf-8", errors="replace"
        )
        files = [l for l in status.splitlines() if l.strip()]
        return {
            "branch":        branch,
            "changed_files": len(files),
            "status_lines":  files[:20],
            "recent_log":    log.strip().splitlines()[:5],
        }
    except Exception as e:
        return {"error": str(e)}


# ─── 健康检查 ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    config = load_config()
    providers_status = {}
    for pid in PROVIDER_DEFAULTS:
        providers_status[pid] = bool(get_api_key(pid, config))
    return {
        "status": "ok",
        "cwd": os.getcwd(),
        "providers": providers_status,
    }


# ─── WebSocket 聊天 ──────────────────────────────────────────────────────────

class ChatSession:
    """管理单个 WebSocket 连接的聊天会话"""

    def __init__(self, websocket: WebSocket):
        self.ws = websocket
        self.engine = None
        self.provider = None
        self.model = None
        # 权限确认用的 asyncio 事件
        self._perm_event: asyncio.Event = asyncio.Event()
        self._perm_result: bool = False
        # AskUserQuestion 用的 asyncio 事件
        self._ask_event: asyncio.Event = asyncio.Event()
        self._ask_result: str = ""
        # 当前正在运行的 AI 生成 Task（用于中断）
        self._gen_task: Optional[asyncio.Task] = None

    async def send(self, event: Dict):
        try:
            await self.ws.send_json(event)
        except Exception:
            pass

    # ── 权限确认（通过 WebSocket 发给浏览器）────────────────────────────────

    async def _web_confirm(self, tool_name: str, args: dict, prompt: str) -> bool:
        """向浏览器发送权限确认请求，等待用户操作"""
        self._perm_event.clear()
        await self.send({
            "type": "permission_request",
            "tool": tool_name,
            "args": args,
            "prompt": prompt,
        })
        try:
            await asyncio.wait_for(self._perm_event.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            return False
        return self._perm_result

    # ── AskUserQuestion（通过 WebSocket 发给浏览器）──────────────────────────

    async def _web_ask(self, question: str, options: list) -> str:
        """向浏览器发送提问请求，等待用户在 Web 端回复"""
        self._ask_event.clear()
        await self.send({
            "type": "ask_user",
            "question": question,
            "options": options,
        })
        try:
            await asyncio.wait_for(self._ask_event.wait(), timeout=300.0)
        except asyncio.TimeoutError:
            return "(超时未回复)"
        return self._ask_result

    # ── 会话自动保存 ─────────────────────────────────────────────────────────

    async def _auto_save(self):
        """每次对话结束后自动保存会话"""
        if not self.engine:
            return
        messages = self.engine.app_state.export_messages()
        if not messages:
            return
        sid = self.engine.app_state.session_id
        try:
            save_session(sid, messages, {
                "provider": self.provider or "",
                "model": self.model or "",
                "created_at": self.engine.app_state.created_at,
            })
            await self.send({"type": "session_saved", "session_id": sid})
        except Exception:
            pass

    # ── 引擎初始化 ───────────────────────────────────────────────────────────

    async def init_engine(self, provider: str, model: str = None):
        """首次初始化引擎（创建新 QueryEngine，带空白历史）"""
        from mira.query import QueryEngine
        config = load_config()
        api_key = get_api_key(provider, config)
        if not api_key:
            await self.send({"type": "error", "message": f"未配置 {provider} 的 API 密钥，请在设置中添加"})
            return False
        try:
            self.engine = QueryEngine(
                config=config,
                provider=provider,
                model=model or get_default_model(provider, config),
                skip_permissions=config.get("dangerously_skip_permissions", False),
                confirm_fn=self._web_confirm,
                ask_fn=self._web_ask,
            )
            # 从配置文件恢复额外目录
            saved_dirs = config.get("extra_dirs", [])
            self.engine._extra_dirs = [d for d in saved_dirs if os.path.isdir(d)]
            self.provider = provider
            self.model = self.engine.model
            return True
        except Exception as e:
            await self.send({"type": "error", "message": str(e)})
            return False

    async def switch_model(self, provider: str, model: str = None):
        """切换模型：保留对话历史，只换 API 客户端（同 CLI /model 命令）"""
        from mira.services.api import create_api_client
        config = load_config()
        api_key = get_api_key(provider, config)
        if not api_key:
            await self.send({"type": "error", "message": f"未配置 {provider} 的 API 密钥，请在设置中添加"})
            return False
        target_model = model or get_default_model(provider, config)
        try:
            new_client = create_api_client(provider, {
                "api_key": api_key,
                "model": target_model,
                "temperature": config.get("temperature", 0.7),
                "base_url": get_provider_base_url(provider, config),
            })
            if self.engine:
                # 就地替换，保留历史
                self.engine.api_client = new_client
                self.engine.provider = provider
                self.engine.model = target_model
                self.engine.config = config
            self.provider = provider
            self.model = target_model
            return True
        except Exception as e:
            await self.send({"type": "error", "message": str(e)})
            return False

    # ── 消息处理 ─────────────────────────────────────────────────────────────

    async def handle_message(self, data: Dict):
        msg_type = data.get("type", "chat")

        # ── 权限响应 ──────────────────────────────────────────────────────────
        if msg_type == "permission_response":
            self._perm_result = bool(data.get("approved", False))
            self._perm_event.set()
            return

        # ── AskUserQuestion 回复 ──────────────────────────────────────────────
        if msg_type == "ask_response":
            self._ask_result = data.get("answer", "")
            self._ask_event.set()
            return

        # ── 首次初始化（连接时）─────────────────────────────────────────────
        if msg_type == "init":
            provider = data.get("provider") or "deepseek"
            model = data.get("model")
            ok = await self.init_engine(provider, model)
            if ok:
                await self.send({
                    "type": "ready",
                    "provider": self.provider,
                    "model": self.model,
                    "session_id": self.engine.app_state.session_id,
                })
            return

        # ── 切换模型（保留历史）────────────────────────────────────────────────
        if msg_type == "switch":
            provider = data.get("provider") or "deepseek"
            model = data.get("model")
            # 引擎不存在则先初始化
            if not self.engine:
                ok = await self.init_engine(provider, model)
            else:
                ok = await self.switch_model(provider, model)
            if ok:
                # 持久化选择
                cfg = load_config()
                cfg["default_provider"] = provider
                if model:
                    cfg.setdefault("provider_selected_models", {})[provider] = model
                save_config(cfg)
                await self.send({
                    "type": "ready",
                    "provider": self.provider,
                    "model": self.model,
                    "session_id": self.engine.app_state.session_id if self.engine else "",
                })
            return

        # ── 技能执行 ──────────────────────────────────────────────────────────
        if msg_type == "run_skill":
            skill_name = data.get("name", "")
            from mira.services.skills import get_skill
            skill = get_skill(skill_name)
            if not skill:
                await self.send({"type": "error", "message": f"技能不存在: {skill_name}"})
                return
            # 作为普通聊天执行
            data = {"type": "chat", "prompt": skill["prompt"],
                    "provider": data.get("provider"), "model": data.get("model")}
            msg_type = "chat"

        # ── 聊天 ──────────────────────────────────────────────────────────────
        if msg_type == "chat":
            prompt = data.get("prompt", "").strip()
            attachments = data.get("attachments", [])  # [{type, name, content/data, media_type}]

            # 处理附件：文本拼接到 prompt，图片收集为 vision 列表
            image_attachments = []
            if attachments:
                text_parts = [prompt] if prompt else []
                for att in attachments:
                    if att.get("type") == "text":
                        ext = att["name"].rsplit(".", 1)[-1] if "." in att["name"] else "text"
                        text_parts.append(f"\n文件 `{att['name']}`:\n```{ext}\n{att['content']}\n```")
                    elif att.get("type") == "image":
                        image_attachments.append({
                            "media_type": att.get("media_type", "image/png"),
                            "data": att.get("data", ""),
                            "name": att.get("name", "图片"),
                        })
                if text_parts:
                    prompt = "\n".join(text_parts)

            if not prompt and not image_attachments:
                return

            # 自动初始化 engine（首次发消息且未初始化时）
            if not self.engine:
                provider = data.get("provider") or load_config().get("default_provider", "deepseek")
                model = data.get("model")
                ok = await self.init_engine(provider, model)
                if not ok:
                    return

            await self.send({"type": "user_message", "content": prompt,
                             "attachments": attachments})

            async def callback(event: Dict):
                await self.send(event)
                if event.get("type") == "done":
                    await self._auto_save()

            async def _run_gen():
                try:
                    await self.engine.process_message(
                        prompt, callback=callback,
                        images=image_attachments if image_attachments else None,
                    )
                except asyncio.CancelledError:
                    await self.send({"type": "done", "interrupted": True})
                    await self.send({"type": "system", "text": "⏹ 已中断"})
                except Exception as e:
                    await self.send({"type": "error", "message": str(e)})
                finally:
                    self._gen_task = None

            self._gen_task = asyncio.create_task(_run_gen())
            return

        # ── 中断生成 ──────────────────────────────────────────────────────────
        if msg_type == "stop":
            if self._gen_task and not self._gen_task.done():
                self._gen_task.cancel()
            return

        # ── 清空历史 ──────────────────────────────────────────────────────────
        if msg_type == "clear":
            if self.engine:
                self.engine.clear_history()
            await self.send({"type": "cleared"})
            return

        # ── 新会话 ────────────────────────────────────────────────────────────
        if msg_type == "new_session":
            if self.engine:
                self.engine.app_state.clear_messages()
                # 分配新 session_id
                from mira.state.app_state import AppState
                import uuid
                self.engine.app_state.session_id = str(uuid.uuid4())[:8]
            await self.send({"type": "cleared",
                             "session_id": self.engine.app_state.session_id if self.engine else ""})
            return

        # ── 加载会话 ──────────────────────────────────────────────────────────
        if msg_type == "load_session":
            session_id = data.get("session_id")
            session_data = load_session(session_id)
            if session_data and self.engine:
                self.engine.app_state.clear_messages()
                self.engine.app_state.session_id = session_id
                for msg in session_data.get("messages", []):
                    self.engine.app_state.add_message(msg)
                await self.send({
                    "type": "session_loaded",
                    "session_id": session_id,
                    "messages": session_data.get("messages", []),
                    "provider": session_data.get("provider", ""),
                    "model": session_data.get("model", ""),
                    "title": session_data.get("title", ""),
                })
            return

        # ── 获取工具列表 ──────────────────────────────────────────────────────
        if msg_type == "get_tools":
            if self.engine:
                tools = [{"name": t.name, "description": t.description} for t in self.engine.tools]
                await self.send({"type": "tools_list", "tools": tools})
            return

        # ── 设置工作目录 ──────────────────────────────────────────────────────
        if msg_type == "set_cwd":
            path = data.get("path", "")
            if path and os.path.isdir(path):
                os.chdir(path)
                await self.send({"type": "cwd_changed", "cwd": os.getcwd()})
                # 通知前端刷新项目记忆（目录变化后 NOTES.md 来源可能不同）
                await self.send({"type": "memory_changed"})
            else:
                await self.send({"type": "error", "message": f"目录不存在: {path}"})
            return

        # ── 获取状态 ──────────────────────────────────────────────────────────
        if msg_type == "get_status":
            if self.engine:
                from mira.utils.context import get_context_usage
                ctx = get_context_usage(self.engine.app_state.messages, self.engine.model)
                await self.send({
                    "type":        "status",
                    "session_id":  self.engine.app_state.session_id,
                    "provider":    self.engine.provider,
                    "model":       self.engine.model,
                    "cwd":         os.getcwd(),
                    "messages":    len(self.engine.app_state.messages),
                    "ctx_used":    ctx["used"],
                    "ctx_window":  ctx["window"],
                    "ctx_ratio":   ctx["ratio"],
                    "cost_usd":    self.engine.cost_tracker.total_usd,
                    "cost_input":  self.engine.cost_tracker.total_input,
                    "cost_output": self.engine.cost_tracker.total_output,
                })
            return

        # ── 手动压缩 ──────────────────────────────────────────────────────────
        if msg_type == "compact":
            if self.engine:
                async def cb(ev):
                    await self.send(ev)
                await self.engine._do_compact(cb)
                await self.send({"type": "done"})
            return

        # ── 列出额外目录 ──────────────────────────────────────────────────
        if msg_type == "list_dirs":
            extra = list(self.engine._extra_dirs) if self.engine else []
            await self.send({"type": "dirs_list", "cwd": os.getcwd(), "extra_dirs": extra})
            return

        # ── 添加额外目录 ──────────────────────────────────────────────────
        if msg_type == "add_dir":
            path = data.get("path", "").strip()
            if not path:
                await self.send({"type": "error", "message": "路径不能为空"})
                return
            abs_path = os.path.abspath(path)
            if not os.path.isdir(abs_path):
                await self.send({"type": "error", "message": f"目录不存在: {abs_path}"})
                return
            if self.engine and abs_path not in self.engine._extra_dirs:
                self.engine._extra_dirs.append(abs_path)
            extra = list(self.engine._extra_dirs) if self.engine else []
            _persist_extra_dirs(extra)
            await self.send({"type": "dirs_list", "cwd": os.getcwd(), "extra_dirs": extra})
            return

        # ── 移除额外目录 ──────────────────────────────────────────────────
        if msg_type == "remove_dir":
            path = data.get("path", "").strip()
            if self.engine and path in self.engine._extra_dirs:
                self.engine._extra_dirs.remove(path)
            extra = list(self.engine._extra_dirs) if self.engine else []
            _persist_extra_dirs(extra)
            await self.send({"type": "dirs_list", "cwd": os.getcwd(), "extra_dirs": extra})
            return

        # ── 计划模式开关 ──────────────────────────────────────────────────
        if msg_type == "set_plan_mode":
            if self.engine:
                self.engine._plan_mode = bool(data.get("active", False))
                await self.send({"type": "plan_mode", "active": self.engine._plan_mode})
            return


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    session = ChatSession(websocket)

    # 自动用默认 provider 初始化
    config = load_config()
    default_provider = config.get("default_provider", "deepseek")
    await session.init_engine(default_provider)
    if session.engine:
        await session.send({
            "type": "ready",
            "provider": session.provider,
            "model": session.model,
            "session_id": session.engine.app_state.session_id,
        })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await session.send({"type": "error", "message": "无效的 JSON 数据"})
                continue
            await session.handle_message(data)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ─── 启动入口 ────────────────────────────────────────────────────────────────

def find_free_port(start: int = 8080, end: int = 9000) -> int:
    """在 [start, end) 范围内扫描并返回第一个空闲的 TCP 端口。"""
    import socket
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"在 {start}–{end} 范围内找不到空闲端口，请手动指定 --port")


def start_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True):
    """启动 Web 服务器。若指定端口被占用则自动向后查找空闲端口。"""
    import sys
    import uvicorn
    import socket

    # Windows 上必须使用 SelectorEventLoop，ProactorEventLoop 与 uvicorn 不兼容
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 检测端口是否可用，被占用则自动寻找空闲端口
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
        _s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            _s.bind((host, port))
        except OSError:
            old_port = port
            port = find_free_port(port + 1)
            print(f"  端口 {old_port} 已被占用，自动切换到 {port}")

    if open_browser:
        import threading
        import webbrowser
        _url = f"http://{host}:{port}"
        def _open():
            import time
            time.sleep(1.5)
            webbrowser.open(_url)
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n✦  Mira Web UI")
    print(f"   地址: http://{host}:{port}")
    print(f"   按 Ctrl+C 停止\n")

    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except Exception as exc:
        # 在打包环境（无控制台）下将错误写入日志文件方便排查
        if getattr(sys, "frozen", False):
            import traceback
            log_path = Path.home() / ".mira" / "error.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                f"Mira Web Server Error\n{'='*40}\n{traceback.format_exc()}",
                encoding="utf-8",
            )
        raise
