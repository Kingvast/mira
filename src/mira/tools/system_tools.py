#!/usr/bin/env python3
"""
系统工具 — HTTP 请求 / 压缩包 / 环境变量 / 进程管理
"""

import json
import os
import subprocess
import sys
import zipfile
import tarfile
from pathlib import Path
from typing import Any, Dict

from mira.tools.base import Tool


# ══════════════════════════════════════════════════════════════════════════════
#  HttpRequestTool
# ══════════════════════════════════════════════════════════════════════════════

class HttpRequestTool(Tool):
    """向任意 URL 发送 HTTP 请求，适合测试 REST API 接口。"""

    @property
    def name(self) -> str:
        return "HttpRequestTool"

    @property
    def description(self) -> str:
        return (
            "发送 HTTP 请求（GET/POST/PUT/DELETE/PATCH 等）并返回状态码、响应头和响应体。"
            "适合测试 API 接口、调试 Webhook、验证服务端响应。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "请求 URL",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP 方法，默认 GET。可选：GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS",
                },
                "headers": {
                    "type": "object",
                    "description": "请求头（JSON 对象），如 {\"Authorization\": \"Bearer token\"}",
                },
                "body": {
                    "type": "string",
                    "description": "请求体字符串。若为合法 JSON 则自动以 application/json 发送",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 30",
                    "minimum": 1,
                    "maximum": 120,
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "是否跟随重定向，默认 true",
                },
            },
            "required": ["url"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        import httpx

        url = args.get("url", "").strip()
        if not url:
            return "错误: url 不能为空"

        method  = str(args.get("method", "GET")).upper()
        headers = args.get("headers") or {}
        body    = args.get("body")
        timeout = int(args.get("timeout", 30))
        follow  = args.get("follow_redirects", True)

        kwargs: Dict[str, Any] = {
            "headers": headers,
            "timeout": timeout,
            "follow_redirects": follow,
        }

        if body:
            try:
                kwargs["json"] = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                kwargs["content"] = body.encode("utf-8")
                if "content-type" not in {k.lower() for k in headers}:
                    kwargs["headers"] = {**headers, "Content-Type": "text/plain; charset=utf-8"}

        try:
            with httpx.Client() as client:
                resp = client.request(method, url, **kwargs)

            elapsed = resp.elapsed.total_seconds() if resp.elapsed else 0
            lines = [
                f"HTTP {resp.status_code} {resp.reason_phrase}  ({elapsed:.3f}s)",
                "── 响应头 " + "─" * 40,
            ]
            for k, v in resp.headers.items():
                lines.append(f"  {k}: {v}")

            lines.append("── 响应体 " + "─" * 40)

            content_type = resp.headers.get("content-type", "")
            try:
                if "json" in content_type:
                    body_text = json.dumps(resp.json(), ensure_ascii=False, indent=2)
                else:
                    body_text = resp.text
            except Exception:
                body_text = resp.text

            _MAX = 8000
            if len(body_text) > _MAX:
                body_text = body_text[:_MAX] + f"\n… (已截断，共 {len(resp.content):,} 字节)"

            lines.append(body_text)
            return "\n".join(lines)

        except Exception as e:
            return f"请求失败: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  ArchiveTool
# ══════════════════════════════════════════════════════════════════════════════

class ArchiveTool(Tool):
    """压缩包操作：列出内容、解压、创建 zip / tar.gz 等格式。"""

    @property
    def name(self) -> str:
        return "ArchiveTool"

    @property
    def description(self) -> str:
        return (
            "压缩包操作。"
            "list：列出压缩包内容；"
            "extract：解压到目标目录；"
            "create：将文件/目录打包为 .zip / .tar.gz / .tgz / .tar.bz2 / .tar.xz。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：list / extract / create",
                },
                "path": {
                    "type": "string",
                    "description": "压缩包路径",
                },
                "dest": {
                    "type": "string",
                    "description": "解压目标目录（extract 时使用，默认当前目录）",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要打包的文件/目录列表（create 时使用）",
                },
            },
            "required": ["action", "path"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).lower()
        path   = args.get("path", "")
        dest   = args.get("dest", ".")
        files  = args.get("files") or []

        if not path:
            return "错误: path 不能为空"

        p = Path(path)

        if action == "list":
            return self._list(p)
        elif action == "extract":
            return self._extract(p, Path(dest))
        elif action == "create":
            return self._create(p, files)
        else:
            return f"错误: 未知操作 '{action}'，可选: list / extract / create"

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _list(self, p: Path) -> str:
        if not p.exists():
            return f"错误: 文件不存在: {p}"
        try:
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as zf:
                    infos = zf.infolist()
                    lines = [f"ZIP  {p}  ({len(infos)} 个条目)"]
                    for info in infos:
                        lines.append(f"  {info.filename:<60} {info.file_size:>10,} B")
                    return "\n".join(lines)
            elif tarfile.is_tarfile(str(p)):
                with tarfile.open(p) as tf:
                    members = tf.getmembers()
                    lines = [f"TAR  {p}  ({len(members)} 个条目)"]
                    for m in members:
                        lines.append(f"  {m.name:<60} {m.size:>10,} B")
                    return "\n".join(lines)
            else:
                return f"错误: 不支持的格式（仅支持 zip / tar.*）: {p}"
        except Exception as e:
            return f"错误: {e}"

    def _extract(self, p: Path, dest: Path) -> str:
        if not p.exists():
            return f"错误: 文件不存在: {p}"
        dest.mkdir(parents=True, exist_ok=True)
        try:
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as zf:
                    zf.extractall(dest)
                    count = len(zf.namelist())
            elif tarfile.is_tarfile(str(p)):
                with tarfile.open(p) as tf:
                    tf.extractall(dest)
                    count = len(tf.getmembers())
            else:
                return f"错误: 不支持的格式: {p}"
            return f"✓ 已解压 {count} 个条目到: {dest.resolve()}"
        except Exception as e:
            return f"错误: {e}"

    def _create(self, p: Path, files: list) -> str:
        if not files:
            return "错误: create 操作需要指定 files 参数"
        name = str(p).lower()
        try:
            if name.endswith(".zip"):
                with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in files:
                        fp = Path(f)
                        if fp.is_dir():
                            for sub in sorted(fp.rglob("*")):
                                if sub.is_file():
                                    zf.write(sub, sub.relative_to(fp.parent))
                        elif fp.exists():
                            zf.write(fp, fp.name)
                    count = len(zf.namelist())
            elif any(name.endswith(ext) for ext in (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")):
                mode = (
                    "w:gz"  if any(name.endswith(e) for e in (".tar.gz", ".tgz")) else
                    "w:bz2" if name.endswith(".tar.bz2") else
                    "w:xz"  if name.endswith(".tar.xz")  else "w"
                )
                with tarfile.open(p, mode) as tf:
                    for f in files:
                        tf.add(f, arcname=Path(f).name)
                    count = len(tf.getmembers())
            else:
                return "错误: 不支持的目标格式，请用 .zip / .tar.gz / .tgz / .tar.bz2 / .tar.xz"
            return f"✓ 已创建: {p.resolve()}  ({count} 个条目)"
        except Exception as e:
            return f"错误: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  EnvTool
# ══════════════════════════════════════════════════════════════════════════════

class EnvTool(Tool):
    """读写当前进程的环境变量。"""

    @property
    def name(self) -> str:
        return "EnvTool"

    @property
    def description(self) -> str:
        return (
            "环境变量管理。"
            "get：读取指定变量；"
            "set：设置变量（仅当前进程）；"
            "unset：删除变量；"
            "list：列出所有变量（可按关键词过滤）。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作：get / set / unset / list",
                },
                "name": {
                    "type": "string",
                    "description": "变量名称（get/set/unset 必填）",
                },
                "value": {
                    "type": "string",
                    "description": "要设置的值（set 时使用）",
                },
                "filter": {
                    "type": "string",
                    "description": "list 时按关键词过滤变量名（不区分大小写）",
                },
            },
            "required": ["action"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        action  = str(args.get("action", "")).lower()
        name    = args.get("name", "")
        value   = str(args.get("value", ""))
        keyword = str(args.get("filter", "")).upper()

        if action == "get":
            if not name:
                return "错误: get 需要 name 参数"
            val = os.environ.get(name)
            return f"{name}={val}" if val is not None else f"未设置: {name}"

        elif action == "set":
            if not name:
                return "错误: set 需要 name 参数"
            os.environ[name] = value
            return f"✓ {name}={value}"

        elif action == "unset":
            if not name:
                return "错误: unset 需要 name 参数"
            if name in os.environ:
                del os.environ[name]
                return f"✓ 已删除: {name}"
            return f"不存在: {name}"

        elif action == "list":
            items = sorted(os.environ.items())
            if keyword:
                items = [(k, v) for k, v in items if keyword in k.upper()]
            if not items:
                return "无匹配的环境变量" + (f"（过滤: {keyword}）" if keyword else "")
            lines = [f"环境变量（{len(items)} 个）:"]
            for k, v in items:
                v_disp = v if len(v) <= 80 else v[:80] + "…"
                lines.append(f"  {k}={v_disp}")
            return "\n".join(lines)

        else:
            return f"错误: 未知操作 '{action}'，可选: get / set / unset / list"


# ══════════════════════════════════════════════════════════════════════════════
#  ProcessTool
# ══════════════════════════════════════════════════════════════════════════════

class ProcessTool(Tool):
    """查看进程列表、按端口查找占用进程、结束进程。"""

    @property
    def name(self) -> str:
        return "ProcessTool"

    @property
    def description(self) -> str:
        return (
            "进程管理。"
            "list：列出进程（可按名称或端口过滤）；"
            "kill：结束进程（按 PID 或名称）。"
            "适合查找占用端口的进程、结束卡死的服务。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作：list / kill",
                },
                "name": {
                    "type": "string",
                    "description": "按进程名过滤（list）或要结束的进程名（kill）",
                },
                "pid": {
                    "type": "integer",
                    "description": "进程 PID（kill 时使用）",
                },
                "port": {
                    "type": "integer",
                    "description": "查找占用此端口的进程（list 时使用）",
                },
            },
            "required": ["action"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).lower()
        name   = args.get("name", "")
        pid    = args.get("pid")
        port   = args.get("port")

        if action == "list":
            return self._list(name=name, port=port)
        elif action == "kill":
            return self._kill(name=name, pid=pid)
        else:
            return f"错误: 未知操作 '{action}'，可选: list / kill"

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _list(self, name: str = "", port: int = None) -> str:
        try:
            if sys.platform == "win32":
                return self._list_windows(name=name, port=port)
            else:
                return self._list_unix(name=name, port=port)
        except Exception as e:
            return f"错误: {e}"

    def _list_windows(self, name: str, port) -> str:
        if port:
            r = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
            )
            lines = [
                l for l in r.stdout.splitlines()
                if f":{port} " in l or f":{port}\t" in l
            ]
            return "\n".join(lines) if lines else f"没有进程占用端口 {port}"

        r = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        rows = ["进程名                     PID   内存"]
        for line in r.stdout.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) < 5:
                continue
            proc_name, proc_pid, _, _, mem = parts[0], parts[1], parts[2], parts[3], parts[4]
            if name and name.lower() not in proc_name.lower():
                continue
            rows.append(f"  {proc_name:<30} {proc_pid:<8} {mem}")
        return "\n".join(rows[:60]) if len(rows) > 1 else f"未找到进程: {name}"

    def _list_unix(self, name: str, port) -> str:
        if port:
            cmds = [
                ["lsof", "-i", f":{port}", "-n", "-P"],
                ["ss", "-tlnp", f"sport = :{port}"],
            ]
            for cmd in cmds:
                try:
                    r = subprocess.run(
                        cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=10,
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        return r.stdout.strip()
                except FileNotFoundError:
                    continue
            return f"没有进程占用端口 {port}（lsof/ss 均未找到）"

        r = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        lines = r.stdout.splitlines()
        if name:
            lines = [lines[0]] + [l for l in lines[1:] if name.lower() in l.lower()]
        return "\n".join(lines[:60]) if lines else f"未找到进程: {name}"

    def _kill(self, name: str, pid) -> str:
        if not pid and not name:
            return "错误: kill 需要 pid 或 name 参数"
        try:
            if sys.platform == "win32":
                if pid:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        check=True, capture_output=True,
                    )
                    return f"✓ 已结束进程 PID {pid}"
                else:
                    subprocess.run(
                        ["taskkill", "/F", "/IM", name],
                        check=True, capture_output=True,
                    )
                    return f"✓ 已结束进程 {name}"
            else:
                if pid:
                    subprocess.run(["kill", "-TERM", str(pid)], check=True)
                    return f"✓ 已发送 SIGTERM 给 PID {pid}"
                else:
                    subprocess.run(["pkill", "-f", name], check=True)
                    return f"✓ 已结束进程 {name}"
        except subprocess.CalledProcessError as e:
            return f"错误: 无法结束进程 ({e.returncode})"
        except Exception as e:
            return f"错误: {e}"


# ══════════════════════════════════════════════════════════════════════════════
#  DateTimeTool
# ══════════════════════════════════════════════════════════════════════════════

class DateTimeTool(Tool):
    """获取当前日期时间、格式化时间戳，支持时区。"""

    @property
    def name(self) -> str:
        return "DateTimeTool"

    @property
    def description(self) -> str:
        return (
            "日期时间工具。"
            "now：获取当前时间（可指定时区/格式）；"
            "timestamp：获取当前 Unix 时间戳；"
            "format：将 Unix 时间戳格式化为可读时间。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作: now（默认）/ timestamp / format",
                },
                "timezone": {
                    "type": "string",
                    "description": "时区名称，如 Asia/Shanghai、UTC、America/New_York，默认本地时区",
                },
                "format": {
                    "type": "string",
                    "description": "strftime 格式字符串，如 %Y-%m-%d %H:%M:%S，默认 ISO 8601",
                },
                "timestamp": {
                    "type": "number",
                    "description": "Unix 时间戳（format 操作时使用）",
                },
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        from datetime import datetime, timezone, timedelta
        import time as _time

        action   = str(args.get("action", "now")).lower()
        tz_name  = args.get("timezone", "")
        fmt      = args.get("format", "")
        ts       = args.get("timestamp")

        # 解析时区
        tz = None
        if tz_name:
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(tz_name)
            except Exception:
                up = tz_name.upper()
                if up.startswith("UTC"):
                    rest = up[3:]
                    if rest:
                        sign = -1 if rest[0] == "-" else 1
                        try:
                            tz = timezone(timedelta(hours=sign * int(rest.lstrip("+-"))))
                        except Exception:
                            return f"错误: 无法识别时区 '{tz_name}'"
                    else:
                        tz = timezone.utc
                else:
                    return f"错误: 无法识别时区 '{tz_name}'"

        if action == "timestamp":
            return f"当前 Unix 时间戳: {int(_time.time())}"

        if action == "format" and ts is not None:
            dt = datetime.fromtimestamp(float(ts), tz=tz or timezone.utc)
        else:
            dt = datetime.now(tz=tz)

        result = dt.strftime(fmt) if fmt else dt.isoformat()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return "\n".join([
            f"当前时间: {result}",
            f"时区:     {tz_name or '本地'}",
            f"时间戳:   {int(dt.timestamp())}",
            f"星期:     {weekdays[dt.weekday()]}",
        ])


# ══════════════════════════════════════════════════════════════════════════════
#  HashTool
# ══════════════════════════════════════════════════════════════════════════════

class HashTool(Tool):
    """计算文件或字符串的哈希值（MD5/SHA1/SHA256/SHA512）。"""

    @property
    def name(self) -> str:
        return "HashTool"

    @property
    def description(self) -> str:
        return (
            "计算文件或字符串的哈希摘要（MD5/SHA1/SHA256/SHA512）。"
            "适合校验文件完整性、生成唯一标识、比较两个文件是否相同。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "algorithm": {
                    "type": "string",
                    "description": "算法: md5 / sha1 / sha256（默认）/ sha512",
                },
                "file": {
                    "type": "string",
                    "description": "要哈希的文件路径（与 text 二选一）",
                },
                "text": {
                    "type": "string",
                    "description": "要哈希的文本字符串（与 file 二选一）",
                },
            },
        }

    def execute(self, args: Dict[str, Any]) -> str:
        import hashlib

        algo      = str(args.get("algorithm", "sha256")).lower()
        file_path = args.get("file", "")
        text      = args.get("text")

        if algo not in ("md5", "sha1", "sha256", "sha512"):
            return f"错误: 不支持的算法 '{algo}'，可选: md5 / sha1 / sha256 / sha512"

        if not file_path and text is None:
            return "错误: 需要提供 file 或 text 参数"

        h = hashlib.new(algo)

        if file_path:
            p = Path(file_path)
            if not p.exists():
                return f"错误: 文件不存在: {file_path}"
            try:
                with open(p, "rb") as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
                return f"{algo.upper()}: {h.hexdigest()}\n文件: {p.resolve()}\n大小: {p.stat().st_size:,} 字节"
            except Exception as e:
                return f"错误: {e}"
        else:
            h.update(str(text).encode("utf-8"))
            preview = str(text)[:80] + ("…" if len(str(text)) > 80 else "")
            return f"{algo.upper()}: {h.hexdigest()}\n内容: {preview}"


# ══════════════════════════════════════════════════════════════════════════════
#  Base64Tool
# ══════════════════════════════════════════════════════════════════════════════

class Base64Tool(Tool):
    """Base64 编码与解码。"""

    @property
    def name(self) -> str:
        return "Base64Tool"

    @property
    def description(self) -> str:
        return (
            "Base64 编码/解码。"
            "encode：将文本或文件内容编码为 Base64 字符串；"
            "decode：将 Base64 字符串解码为文本，或保存为二进制文件。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作: encode / decode",
                },
                "text": {
                    "type": "string",
                    "description": "要编码的文本（encode），或要解码的 Base64 字符串（decode）",
                },
                "file": {
                    "type": "string",
                    "description": "要编码的文件路径（encode 时使用）",
                },
                "output_file": {
                    "type": "string",
                    "description": "解码结果保存到的文件路径（decode 时可选）",
                },
            },
            "required": ["action"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        import base64

        action      = str(args.get("action", "")).lower()
        text        = args.get("text", "")
        file_path   = args.get("file", "")
        output_file = args.get("output_file", "")

        if action == "encode":
            if file_path:
                p = Path(file_path)
                if not p.exists():
                    return f"错误: 文件不存在: {file_path}"
                try:
                    raw = p.read_bytes()
                    encoded = base64.b64encode(raw).decode("ascii")
                    preview = encoded[:2000] + ("…" if len(encoded) > 2000 else "")
                    return f"Base64 编码 ({p.name}, {len(raw):,} 字节):\n{preview}"
                except Exception as e:
                    return f"错误: {e}"
            elif text:
                encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
                return f"Base64: {encoded}"
            else:
                return "错误: encode 需要 text 或 file 参数"

        elif action == "decode":
            if not text:
                return "错误: decode 需要 text 参数（Base64 字符串）"
            try:
                data = base64.b64decode(text.strip())
                if output_file:
                    Path(output_file).write_bytes(data)
                    return f"✓ 已解码并保存到: {output_file}  ({len(data):,} 字节)"
                try:
                    decoded = data.decode("utf-8")
                    preview = decoded[:2000] + ("…" if len(decoded) > 2000 else "")
                    return f"解码结果（文本）:\n{preview}"
                except UnicodeDecodeError:
                    return (
                        f"解码结果为二进制数据（{len(data):,} 字节），无法作为 UTF-8 文本显示。\n"
                        "请使用 output_file 参数将结果保存到文件。"
                    )
            except Exception as e:
                return f"错误: {e}"

        else:
            return f"错误: 未知操作 '{action}'，可选: encode / decode"
