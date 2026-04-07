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


# ══════════════════════════════════════════════════════════════════════════════
#  SQLiteTool
# ══════════════════════════════════════════════════════════════════════════════

class SQLiteTool(Tool):
    """对本地 SQLite 数据库执行 SQL 查询，查看结构、读写数据。"""

    @property
    def name(self) -> str:
        return "SQLiteTool"

    @property
    def description(self) -> str:
        return (
            "操作本地 SQLite 数据库文件（.db / .sqlite / .sqlite3）。\n"
            "query：执行任意 SQL 语句（SELECT/INSERT/UPDATE/DELETE/CREATE/DROP）；\n"
            "schema：查看所有表结构；\n"
            "tables：列出所有表名；\n"
            "describe：查看指定表的列定义；\n"
            "export_csv：将查询结果导出为 CSV 文件。\n"
            "注意：写操作（INSERT/UPDATE/DELETE/CREATE/DROP）会修改数据库文件，请谨慎使用。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "SQLite 数据库文件路径（支持 .db/.sqlite/.sqlite3，也可用 :memory: 创建内存库）",
                },
                "action": {
                    "type": "string",
                    "description": "操作类型：query（默认）/ schema / tables / describe / export_csv",
                },
                "sql": {
                    "type": "string",
                    "description": "SQL 语句（action=query 或 export_csv 时使用）",
                },
                "table": {
                    "type": "string",
                    "description": "表名（action=describe 时使用）",
                },
                "params": {
                    "type": "array",
                    "items": {},
                    "description": "SQL 参数化查询的参数列表（可选，防止 SQL 注入）",
                },
                "limit": {
                    "type": "integer",
                    "description": "查询结果最大行数（默认 100）",
                    "minimum": 1,
                    "maximum": 10000,
                },
                "output_file": {
                    "type": "string",
                    "description": "export_csv 时的输出文件路径",
                },
            },
            "required": ["database"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        import sqlite3

        database = str(args.get("database", "")).strip()
        action = str(args.get("action", "query")).lower()
        sql = str(args.get("sql", "")).strip()
        table = str(args.get("table", "")).strip()
        params = args.get("params") or []
        limit = int(args.get("limit", 100))
        output_file = str(args.get("output_file", "")).strip()

        if not database:
            return "错误: database 参数不能为空"

        if database != ":memory:":
            db_path = Path(database)
            if not db_path.exists():
                # 如果是写操作，允许创建新文件
                if action == "query" and sql and any(
                    sql.upper().lstrip().startswith(kw)
                    for kw in ("CREATE", "INSERT", "ATTACH")
                ):
                    pass  # 允许创建
                elif action == "query":
                    return f"错误: 数据库文件不存在: {database}"

        try:
            conn = sqlite3.connect(database)
            conn.row_factory = sqlite3.Row

            if action == "tables":
                return self._list_tables(conn)
            elif action == "schema":
                return self._show_schema(conn)
            elif action == "describe":
                return self._describe_table(conn, table)
            elif action == "export_csv":
                return self._export_csv(conn, sql, params, output_file, limit)
            else:
                return self._run_query(conn, sql, params, limit)

        except sqlite3.Error as e:
            return f"SQLite 错误: {e}"
        except Exception as e:
            return f"错误: {e}"
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _run_query(self, conn, sql: str, params: list, limit: int) -> str:
        import sqlite3
        if not sql:
            return "错误: query 操作需要 sql 参数"

        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)

            # 写操作
            if cursor.description is None:
                conn.commit()
                return f"✓ 执行成功，影响行数: {cursor.rowcount}"

            # 读操作
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchmany(limit)

            if not rows:
                return f"查询返回 0 行\n列: {', '.join(columns)}"

            lines = [self._format_table(columns, rows)]
            total = len(rows)
            if total >= limit:
                lines.append(f"\n（显示前 {limit} 行，如需更多请增大 limit 参数）")
            else:
                lines.append(f"\n共 {total} 行")
            return "\n".join(lines)

        except sqlite3.Error as e:
            return f"SQL 执行错误: {e}"

    def _list_tables(self, conn) -> str:
        cursor = conn.cursor()
        cursor.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name")
        rows = cursor.fetchall()
        if not rows:
            return "数据库中没有表"
        lines = [f"表/视图（共 {len(rows)} 个）:"]
        for row in rows:
            lines.append(f"  {'[视图]' if row[1]=='view' else '[表]  '} {row[0]}")
        return "\n".join(lines)

    def _show_schema(self, conn) -> str:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name"
        )
        rows = cursor.fetchall()
        if not rows:
            return "数据库中没有表"
        lines = [f"数据库结构（{len(rows)} 张表）:"]
        for name, ddl in rows:
            lines.append(f"\n── {name} " + "─" * 40)
            lines.append(ddl or "（无 DDL）")
            # 行数统计
            try:
                count_cur = conn.cursor()
                count_cur.execute(f"SELECT COUNT(*) FROM [{name}]")
                count = count_cur.fetchone()[0]
                lines.append(f"  → 共 {count:,} 行")
            except Exception:
                pass
        return "\n".join(lines)

    def _describe_table(self, conn, table: str) -> str:
        if not table:
            return "错误: describe 操作需要 table 参数"
        cursor = conn.cursor()
        try:
            cursor.execute(f"PRAGMA table_info([{table}])")
            cols = cursor.fetchall()
            if not cols:
                return f"表不存在或无列信息: {table}"
            lines = [f"表: {table}  （{len(cols)} 列）", "─" * 60]
            lines.append(f"  {'序号':<5} {'列名':<25} {'类型':<15} {'非空':<6} {'默认值':<15} {'主键'}")
            lines.append("  " + "─" * 58)
            for col in cols:
                cid, name, dtype, notnull, dflt, pk = col
                lines.append(
                    f"  {cid:<5} {name:<25} {dtype:<15} {'YES' if notnull else 'NO':<6} "
                    f"{str(dflt) if dflt is not None else '':<15} {'PK' if pk else ''}"
                )
            # 索引信息
            cursor.execute(f"PRAGMA index_list([{table}])")
            indexes = cursor.fetchall()
            if indexes:
                lines.append(f"\n索引（{len(indexes)} 个）:")
                for idx in indexes:
                    lines.append(f"  • {idx[1]} {'(unique)' if idx[2] else ''}")
            return "\n".join(lines)
        except Exception as e:
            return f"错误: {e}"

    def _export_csv(self, conn, sql: str, params: list, output_file: str, limit: int) -> str:
        import csv
        import io
        if not sql:
            return "错误: export_csv 需要 sql 参数"
        if not output_file:
            return "错误: export_csv 需要 output_file 参数"

        cursor = conn.cursor()
        cursor.execute(sql, params)
        if cursor.description is None:
            return "错误: 该 SQL 不返回数据（非 SELECT 语句）"

        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchmany(limit)

        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        return f"✓ 已导出 {len(rows)} 行到: {Path(output_file).resolve()}"

    @staticmethod
    def _format_table(columns: list, rows: list) -> str:
        """将查询结果格式化为 ASCII 表格"""
        # 计算列宽
        widths = [len(str(c)) for c in columns]
        str_rows = []
        for row in rows:
            s_row = [str(v) if v is not None else "NULL" for v in row]
            str_rows.append(s_row)
            for i, val in enumerate(s_row):
                widths[i] = min(max(widths[i], len(val)), 40)

        sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        header = "|" + "|".join(f" {str(c):<{w}} " for c, w in zip(columns, widths)) + "|"
        lines = [sep, header, sep]
        for s_row in str_rows:
            line = "|" + "|".join(
                f" {v[:w]:<{w}} " if len(v) <= w else f" {v[:w-1]}… "
                for v, w in zip(s_row, widths)
            ) + "|"
            lines.append(line)
        lines.append(sep)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  RegexTool
# ══════════════════════════════════════════════════════════════════════════════

class RegexTool(Tool):
    """正则表达式测试、提取、替换工具。"""

    @property
    def name(self) -> str:
        return "RegexTool"

    @property
    def description(self) -> str:
        return (
            "正则表达式工具。\n"
            "test：测试正则是否匹配文本，返回所有匹配项；\n"
            "extract：从文本中提取所有匹配的捕获组；\n"
            "replace：用正则替换文本中的匹配内容；\n"
            "split：按正则分割文本；\n"
            "validate：校验整个字符串是否完整匹配正则（如验证邮箱/URL格式）。\n"
            "适合调试正则表达式、文本解析、数据清洗。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作: test / extract / replace / split / validate",
                },
                "pattern": {
                    "type": "string",
                    "description": "正则表达式模式",
                },
                "text": {
                    "type": "string",
                    "description": "要处理的文本",
                },
                "replacement": {
                    "type": "string",
                    "description": "替换字符串（replace 时使用，支持 \\1 \\2 等反向引用）",
                },
                "flags": {
                    "type": "string",
                    "description": "正则标志（可组合）: i（忽略大小写）/ m（多行）/ s（点号匹配换行）/ x（详细模式）",
                },
                "count": {
                    "type": "integer",
                    "description": "replace 时最多替换次数（默认 0=全部替换）",
                },
            },
            "required": ["action", "pattern", "text"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        import re

        action = str(args.get("action", "test")).lower()
        pattern = str(args.get("pattern", ""))
        text = str(args.get("text", ""))
        replacement = str(args.get("replacement", ""))
        flags_str = str(args.get("flags", "")).lower()
        count = int(args.get("count", 0))

        if not pattern:
            return "错误: pattern 参数不能为空"

        # 解析标志
        re_flags = 0
        if "i" in flags_str:
            re_flags |= re.IGNORECASE
        if "m" in flags_str:
            re_flags |= re.MULTILINE
        if "s" in flags_str:
            re_flags |= re.DOTALL
        if "x" in flags_str:
            re_flags |= re.VERBOSE

        try:
            compiled = re.compile(pattern, re_flags)
        except re.error as e:
            return f"正则语法错误: {e}"

        if action == "test":
            return self._test(compiled, text)
        elif action == "extract":
            return self._extract(compiled, text)
        elif action == "replace":
            return self._replace(compiled, text, replacement, count)
        elif action == "split":
            return self._split(compiled, text)
        elif action == "validate":
            return self._validate(compiled, text)
        else:
            return f"错误: 未知操作 '{action}'，可选: test / extract / replace / split / validate"

    def _test(self, pat, text: str) -> str:
        import re
        matches = list(pat.finditer(text))
        if not matches:
            return f"✗ 未找到匹配（模式: {pat.pattern}）"

        lines = [f"✓ 找到 {len(matches)} 个匹配:"]
        for i, m in enumerate(matches[:20], 1):
            start, end = m.start(), m.end()
            groups = m.groups()
            lines.append(f"\n  [{i}] 位置 {start}-{end}: {repr(m.group())}")
            if groups:
                for j, g in enumerate(groups, 1):
                    lines.append(f"       组 {j}: {repr(g)}")
            if m.groupdict():
                for name, val in m.groupdict().items():
                    lines.append(f"       {name}: {repr(val)}")
        if len(matches) > 20:
            lines.append(f"\n  … (仅显示前 20 个，共 {len(matches)} 个)")
        return "\n".join(lines)

    def _extract(self, pat, text: str) -> str:
        matches = pat.findall(text)
        if not matches:
            return "✗ 未找到匹配"
        lines = [f"提取结果（{len(matches)} 条）:"]
        for i, m in enumerate(matches[:50], 1):
            lines.append(f"  {i:3}. {repr(m)}")
        if len(matches) > 50:
            lines.append(f"  … (仅显示前 50 条，共 {len(matches)} 条)")
        return "\n".join(lines)

    def _replace(self, pat, text: str, replacement: str, count: int) -> str:
        result, num = pat.subn(replacement, text, count=count)
        if num == 0:
            return f"✗ 未找到匹配，文本未更改"
        lines = [
            f"✓ 替换了 {num} 处",
            "── 替换后结果 " + "─" * 30,
            result[:4000] + ("…" if len(result) > 4000 else ""),
        ]
        return "\n".join(lines)

    def _split(self, pat, text: str) -> str:
        parts = pat.split(text)
        lines = [f"分割结果（{len(parts)} 段）:"]
        for i, p in enumerate(parts[:30], 1):
            lines.append(f"  [{i}] {repr(p)}")
        if len(parts) > 30:
            lines.append(f"  … (共 {len(parts)} 段)")
        return "\n".join(lines)

    def _validate(self, pat, text: str) -> str:
        import re
        m = pat.fullmatch(text)
        if m:
            return f"✓ 完整匹配（整个字符串与模式匹配）"
        else:
            # 尝试部分匹配
            partial = pat.search(text)
            if partial:
                return (
                    f"✗ 不完整匹配（字符串有部分不符合模式）\n"
                    f"  匹配部分: {repr(partial.group())} (位置 {partial.start()}-{partial.end()})\n"
                    f"  字符串全长: {len(text)}"
                )
            return f"✗ 不匹配（字符串与模式完全不符）"
