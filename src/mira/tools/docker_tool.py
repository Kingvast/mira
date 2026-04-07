#!/usr/bin/env python3
"""
Docker 工具 — 容器/镜像/网络/卷的管理操作
"""

import json
import subprocess
import sys
from typing import Any, Dict

from mira.tools.base import Tool

_MAX_OUT = 6000


def _docker(*args, timeout: int = 30) -> tuple[int, str, str]:
    """运行 docker 命令，返回 (returncode, stdout, stderr)"""
    try:
        r = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "未找到 docker 命令，请先安装 Docker"
    except subprocess.TimeoutExpired:
        return -1, "", f"docker 命令超时（>{timeout}s）"
    except Exception as e:
        return -1, "", str(e)


def _truncate(s: str, limit: int = _MAX_OUT) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n… (已截断，共 {len(s):,} 字符)"


# ══════════════════════════════════════════════════════════════════════════════
#  DockerTool
# ══════════════════════════════════════════════════════════════════════════════

class DockerTool(Tool):
    """Docker 容器、镜像、网络、卷的管理操作。"""

    @property
    def name(self) -> str:
        return "DockerTool"

    @property
    def description(self) -> str:
        return (
            "Docker 管理工具。支持以下操作：\n"
            "容器: list_containers / start / stop / restart / remove / logs / inspect / exec / stats\n"
            "镜像: list_images / pull / remove_image / inspect_image / build\n"
            "系统: info / version / ps / prune\n"
            "Compose: compose_up / compose_down / compose_ps / compose_logs\n"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": (
                        "操作类型：list_containers / start / stop / restart / remove / "
                        "logs / inspect / exec / stats / list_images / pull / "
                        "remove_image / inspect_image / build / info / version / "
                        "prune / compose_up / compose_down / compose_ps / compose_logs"
                    ),
                },
                "container": {
                    "type": "string",
                    "description": "容器名称或 ID",
                },
                "image": {
                    "type": "string",
                    "description": "镜像名称（含可选 tag，如 nginx:latest）",
                },
                "command": {
                    "type": "string",
                    "description": "exec 时要在容器内执行的命令",
                },
                "tail": {
                    "type": "integer",
                    "description": "logs 显示最后 N 行（默认 50）",
                },
                "all": {
                    "type": "boolean",
                    "description": "list_containers 时是否包括已停止的容器（默认 false）",
                },
                "dockerfile": {
                    "type": "string",
                    "description": "build 时的 Dockerfile 路径或上下文目录（默认 .）",
                },
                "tag": {
                    "type": "string",
                    "description": "build 时的镜像标签",
                },
                "compose_file": {
                    "type": "string",
                    "description": "docker-compose.yml 文件路径（默认 docker-compose.yml）",
                },
                "service": {
                    "type": "string",
                    "description": "compose 服务名称（可选）",
                },
                "detach": {
                    "type": "boolean",
                    "description": "compose_up 时是否后台运行（默认 true）",
                },
            },
            "required": ["action"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).lower().strip()

        dispatch = {
            "list_containers": self._list_containers,
            "start":           self._start,
            "stop":            self._stop,
            "restart":         self._restart,
            "remove":          self._remove,
            "logs":            self._logs,
            "inspect":         self._inspect,
            "exec":            self._exec,
            "stats":           self._stats,
            "list_images":     self._list_images,
            "pull":            self._pull,
            "remove_image":    self._remove_image,
            "inspect_image":   self._inspect_image,
            "build":           self._build,
            "info":            self._info,
            "version":         self._version,
            "prune":           self._prune,
            "compose_up":      self._compose_up,
            "compose_down":    self._compose_down,
            "compose_ps":      self._compose_ps,
            "compose_logs":    self._compose_logs,
        }

        handler = dispatch.get(action)
        if not handler:
            supported = " / ".join(sorted(dispatch.keys()))
            return f"错误: 未知操作 '{action}'。支持:\n{supported}"

        return handler(args)

    # ── 容器操作 ──────────────────────────────────────────────────────────────

    def _list_containers(self, args: dict) -> str:
        show_all = args.get("all", False)
        flags = ["ps", "--format", "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"]
        if show_all:
            flags.append("-a")
        rc, out, err = _docker(*flags)
        if rc != 0:
            return f"错误: {err or out}"
        return out or "无运行中的容器" + ("\n提示: 使用 all=true 查看已停止的容器" if not show_all else "")

    def _start(self, args: dict) -> str:
        c = args.get("container", "")
        if not c:
            return "错误: 需要 container 参数"
        rc, out, err = _docker("start", c)
        return f"✓ 已启动: {out}" if rc == 0 else f"错误: {err or out}"

    def _stop(self, args: dict) -> str:
        c = args.get("container", "")
        if not c:
            return "错误: 需要 container 参数"
        rc, out, err = _docker("stop", c)
        return f"✓ 已停止: {out}" if rc == 0 else f"错误: {err or out}"

    def _restart(self, args: dict) -> str:
        c = args.get("container", "")
        if not c:
            return "错误: 需要 container 参数"
        rc, out, err = _docker("restart", c)
        return f"✓ 已重启: {out}" if rc == 0 else f"错误: {err or out}"

    def _remove(self, args: dict) -> str:
        c = args.get("container", "")
        if not c:
            return "错误: 需要 container 参数"
        rc, out, err = _docker("rm", c)
        if rc != 0:
            rc, out, err = _docker("rm", "-f", c)
        return f"✓ 已删除容器: {out}" if rc == 0 else f"错误: {err or out}"

    def _logs(self, args: dict) -> str:
        c = args.get("container", "")
        if not c:
            return "错误: 需要 container 参数"
        tail = str(args.get("tail", 50))
        rc, out, err = _docker("logs", "--tail", tail, c, timeout=20)
        combined = "\n".join(filter(None, [out, err]))
        if rc != 0 and not combined:
            return f"错误: {err or out}"
        return _truncate(combined) or "（无日志输出）"

    def _inspect(self, args: dict) -> str:
        c = args.get("container", "")
        if not c:
            return "错误: 需要 container 参数"
        rc, out, err = _docker("inspect", c)
        if rc != 0:
            return f"错误: {err or out}"
        try:
            data = json.loads(out)
            if data:
                info = data[0]
                lines = [
                    f"容器: {info.get('Name', '').lstrip('/')}",
                    f"ID:   {info.get('Id', '')[:12]}",
                    f"镜像: {info.get('Config', {}).get('Image', '')}",
                    f"状态: {info.get('State', {}).get('Status', '')}",
                    f"IP:   {info.get('NetworkSettings', {}).get('IPAddress', '无')}",
                    "── 完整信息 " + "─" * 30,
                    _truncate(json.dumps(info, ensure_ascii=False, indent=2)),
                ]
                return "\n".join(lines)
        except Exception:
            pass
        return _truncate(out)

    def _exec(self, args: dict) -> str:
        c = args.get("container", "")
        cmd = args.get("command", "")
        if not c:
            return "错误: 需要 container 参数"
        if not cmd:
            return "错误: 需要 command 参数"
        import shlex
        cmd_parts = shlex.split(cmd) if sys.platform != "win32" else cmd.split()
        rc, out, err = _docker("exec", c, *cmd_parts, timeout=60)
        combined = "\n".join(filter(None, [out, err]))
        prefix = "✓ " if rc == 0 else f"退出码 {rc}\n"
        return prefix + _truncate(combined)

    def _stats(self, args: dict) -> str:
        c = args.get("container", "")
        flags = ["stats", "--no-stream", "--format",
                 "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"]
        if c:
            flags.append(c)
        rc, out, err = _docker(*flags, timeout=15)
        return out if rc == 0 else f"错误: {err or out}"

    # ── 镜像操作 ──────────────────────────────────────────────────────────────

    def _list_images(self, args: dict) -> str:
        rc, out, err = _docker(
            "images", "--format",
            "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}"
        )
        return out if rc == 0 else f"错误: {err or out}"

    def _pull(self, args: dict) -> str:
        img = args.get("image", "")
        if not img:
            return "错误: 需要 image 参数"
        rc, out, err = _docker("pull", img, timeout=120)
        return out or err if rc == 0 else f"错误: {err or out}"

    def _remove_image(self, args: dict) -> str:
        img = args.get("image", "")
        if not img:
            return "错误: 需要 image 参数"
        rc, out, err = _docker("rmi", img)
        return f"✓ 已删除镜像: {out}" if rc == 0 else f"错误: {err or out}"

    def _inspect_image(self, args: dict) -> str:
        img = args.get("image", "")
        if not img:
            return "错误: 需要 image 参数"
        rc, out, err = _docker("inspect", img)
        if rc != 0:
            return f"错误: {err or out}"
        try:
            data = json.loads(out)
            if data:
                info = data[0]
                cfg = info.get("Config", {})
                lines = [
                    f"镜像: {img}",
                    f"ID:   {info.get('Id', '')[:12]}",
                    f"创建: {info.get('Created', '')[:19]}",
                    f"大小: {info.get('Size', 0) // 1024 // 1024} MB",
                    f"入口: {cfg.get('Entrypoint', 'none')}",
                    f"命令: {cfg.get('Cmd', 'none')}",
                    f"环境变量: {len(cfg.get('Env', []))} 个",
                    "── 完整信息 " + "─" * 30,
                    _truncate(json.dumps(info, ensure_ascii=False, indent=2), 4000),
                ]
                return "\n".join(lines)
        except Exception:
            pass
        return _truncate(out)

    def _build(self, args: dict) -> str:
        context = args.get("dockerfile", ".")
        tag = args.get("tag", "")
        cmd_args = ["build", context]
        if tag:
            cmd_args += ["-t", tag]
        rc, out, err = _docker(*cmd_args, timeout=300)
        combined = "\n".join(filter(None, [out, err]))
        return _truncate(combined) if rc == 0 else f"构建失败:\n{_truncate(combined)}"

    # ── 系统操作 ──────────────────────────────────────────────────────────────

    def _info(self, args: dict) -> str:
        rc, out, err = _docker("info", "--format", "json")
        if rc != 0:
            return f"错误: {err or out}"
        try:
            info = json.loads(out)
            lines = [
                f"Docker 服务器信息:",
                f"  版本:       {info.get('ServerVersion', '未知')}",
                f"  容器总数:   {info.get('Containers', 0)}（运行: {info.get('ContainersRunning', 0)}，停止: {info.get('ContainersStopped', 0)}）",
                f"  镜像数:     {info.get('Images', 0)}",
                f"  存储驱动:   {info.get('Driver', '未知')}",
                f"  操作系统:   {info.get('OperatingSystem', '未知')}",
                f"  内存:       {info.get('MemTotal', 0) // 1024 // 1024 // 1024} GB",
                f"  CPU:        {info.get('NCPU', 0)} 核",
            ]
            return "\n".join(lines)
        except Exception:
            return _truncate(out)

    def _version(self, args: dict) -> str:
        rc, out, err = _docker("version")
        return out if rc == 0 else f"错误: {err or out}"

    def _prune(self, args: dict) -> str:
        rc, out, err = _docker("system", "prune", "-f")
        return out if rc == 0 else f"错误: {err or out}"

    # ── Docker Compose 操作 ──────────────────────────────────────────────────

    def _compose_cmd(self, compose_file: str, *sub_args, timeout: int = 60):
        """运行 docker compose 命令"""
        base = ["docker", "compose"]
        if compose_file and compose_file != "docker-compose.yml":
            base += ["-f", compose_file]
        try:
            r = subprocess.run(
                base + list(sub_args),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout,
            )
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except FileNotFoundError:
            return -1, "", "未找到 docker compose 命令"
        except subprocess.TimeoutExpired:
            return -1, "", f"命令超时（>{timeout}s）"
        except Exception as e:
            return -1, "", str(e)

    def _compose_up(self, args: dict) -> str:
        cf = args.get("compose_file", "docker-compose.yml")
        svc = args.get("service", "")
        detach = args.get("detach", True)
        sub = ["up", "--build"]
        if detach:
            sub.append("-d")
        if svc:
            sub.append(svc)
        rc, out, err = self._compose_cmd(cf, *sub, timeout=300)
        combined = "\n".join(filter(None, [out, err]))
        return _truncate(combined) if combined else ("✓ 服务已启动" if rc == 0 else f"错误 (rc={rc})")

    def _compose_down(self, args: dict) -> str:
        cf = args.get("compose_file", "docker-compose.yml")
        rc, out, err = self._compose_cmd(cf, "down")
        return out or "✓ 服务已停止" if rc == 0 else f"错误: {err or out}"

    def _compose_ps(self, args: dict) -> str:
        cf = args.get("compose_file", "docker-compose.yml")
        rc, out, err = self._compose_cmd(cf, "ps")
        return out if rc == 0 else f"错误: {err or out}"

    def _compose_logs(self, args: dict) -> str:
        cf = args.get("compose_file", "docker-compose.yml")
        svc = args.get("service", "")
        tail = str(args.get("tail", 50))
        sub = ["logs", "--tail", tail]
        if svc:
            sub.append(svc)
        rc, out, err = self._compose_cmd(cf, *sub, timeout=20)
        combined = "\n".join(filter(None, [out, err]))
        return _truncate(combined) or "（无日志）"
