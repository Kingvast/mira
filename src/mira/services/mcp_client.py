#!/usr/bin/env python3
"""
MCP 客户端 — Model Context Protocol (stdio-based) 基础实现

配置文件：~/.mira/mcp.json
格式：
{
  "servers": [
    {
      "name": "filesystem",
      "description": "文件系统工具",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  ]
}

协议：JSON-RPC 2.0 over stdio（行分隔 JSON）
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 避免循环 import：Tool 基类位于 tools.base
from mira.tools.base import Tool

# MCP 配置文件路径
MCP_CONFIG_PATH = Path.home() / ".mira" / "mcp.json"

# 协议常量
PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "mira", "version": "2.2.0"}

# 单次请求超时（秒）
REQUEST_TIMEOUT = 30.0
# 服务器启动 + initialize 超时（秒）
START_TIMEOUT = 15.0


# ──────────────────────────────────────────────
# MCPServer
# ──────────────────────────────────────────────

class MCPServer:
    """
    与单个 MCP 服务器通信的客户端。

    通过 asyncio.subprocess 启动子进程，使用 stdin/stdout 进行
    行分隔 JSON-RPC 2.0 通信。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        config 字段：
          name        服务器名称（必填）
          command     可执行命令（必填），如 "npx"
          args        命令参数列表（可选），如 ["-y", "@modelcontextprotocol/server-filesystem"]
          description 描述（可选）
        """
        self.name: str = config["name"]
        self.command: str = config["command"]
        self.args: List[str] = config.get("args", [])
        self.description: str = config.get("description", "")

        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._started: bool = False

    # ── 生命周期 ──────────────────────────────

    async def start(self) -> None:
        """
        启动子进程并发送 initialize 握手请求。
        成功后将 _started 置为 True。
        """
        cmd = [self.command] + self.args
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError) as exc:
            raise RuntimeError(
                f"[MCP:{self.name}] 无法启动进程 '{self.command}'：{exc}"
            ) from exc

        # 发送 initialize 请求
        init_params = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        }
        try:
            response = await asyncio.wait_for(
                self._send_request("initialize", init_params),
                timeout=START_TIMEOUT,
            )
        except asyncio.TimeoutError:
            await self.stop()
            raise RuntimeError(
                f"[MCP:{self.name}] initialize 超时（>{START_TIMEOUT}s）"
            )

        # initialize 成功后发送 initialized 通知（无需等待响应）
        await self._send_notification("notifications/initialized")
        self._started = True

    async def stop(self) -> None:
        """终止子进程，忽略所有错误。"""
        if self._process is None:
            return
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except Exception:
            # 进程已退出或超时，强制 kill
            try:
                self._process.kill()
            except Exception:
                pass
        finally:
            self._process = None
            self._started = False

    # ── 工具接口 ──────────────────────────────

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        发送 tools/list 请求，返回工具描述列表。

        每个元素包含：name, description, inputSchema。
        """
        self._ensure_started()
        response = await asyncio.wait_for(
            self._send_request("tools/list"),
            timeout=REQUEST_TIMEOUT,
        )
        # MCP 规范：结果位于 result.tools
        return response.get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        发送 tools/call 请求，返回工具执行结果。

        结果格式由 MCP 服务器决定，通常为 {"content": [...]}。
        """
        self._ensure_started()
        params = {"name": name, "arguments": arguments}
        response = await asyncio.wait_for(
            self._send_request("tools/call", params),
            timeout=REQUEST_TIMEOUT,
        )
        return response

    # ── JSON-RPC 底层 ──────────────────────────

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送 JSON-RPC 请求并等待对应 id 的响应。
        返回 response["result"]，若服务器返回 error 则抛出 RuntimeError。
        """
        assert self._process is not None
        assert self._process.stdin is not None
        assert self._process.stdout is not None

        req_id = self._next_id()
        request: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "id": req_id,
        }
        if params is not None:
            request["params"] = params

        # 写入请求（行分隔 JSON）
        line = json.dumps(request, ensure_ascii=False) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

        # 读取响应行（跳过与当前 id 不匹配的行，例如服务器主动推送的通知）
        while True:
            raw = await self._process.stdout.readline()
            if not raw:
                raise RuntimeError(
                    f"[MCP:{self.name}] 服务器关闭了 stdout（method={method}）"
                )
            try:
                response = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                # 忽略非 JSON 行（如日志输出）
                continue

            # 跳过 id 不匹配的消息（通知没有 id 字段）
            if response.get("id") != req_id:
                continue

            # 检查 JSON-RPC 错误
            if "error" in response:
                err = response["error"]
                raise RuntimeError(
                    f"[MCP:{self.name}] 服务器返回错误 "
                    f"(code={err.get('code')})：{err.get('message')}"
                )

            return response.get("result", {})

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        发送 JSON-RPC 通知（无 id，不等待响应）。
        """
        if self._process is None or self._process.stdin is None:
            return
        notification: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            notification["params"] = params
        line = json.dumps(notification, ensure_ascii=False) + "\n"
        try:
            self._process.stdin.write(line.encode("utf-8"))
            await self._process.stdin.drain()
        except Exception:
            pass  # 通知失败不影响主流程

    def _ensure_started(self) -> None:
        if not self._started:
            raise RuntimeError(
                f"[MCP:{self.name}] 服务器尚未启动，请先调用 await server.start()"
            )


# ──────────────────────────────────────────────
# MCPTool（包装单个 MCP 工具为 Tool 子类）
# ──────────────────────────────────────────────

class MCPTool(Tool):
    """
    将 MCP 服务器暴露的单个工具包装为 Tool 接口。

    name、description、input_schema 直接来自 MCP 服务器的 tools/list 响应。
    execute() 通过关联的 MCPServer 调用 tools/call。
    """

    def __init__(self, server: MCPServer, tool_def: Dict[str, Any]) -> None:
        """
        server:   关联的 MCPServer 实例
        tool_def: MCP tools/list 中的单个工具描述
                  {"name": "...", "description": "...", "inputSchema": {...}}
        """
        self._server = server
        self._name: str = tool_def["name"]
        self._description: str = tool_def.get("description", "（无描述）")
        self._input_schema: Dict[str, Any] = tool_def.get("inputSchema", {})

    # ── Tool 抽象属性 ──────────────────────────

    @property
    def name(self) -> str:
        # MCP 工具名加前缀避免与内置工具冲突
        return f"mcp_{self._server.name}_{self._name}"

    @property
    def description(self) -> str:
        return f"[MCP:{self._server.name}] {self._description}"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return self._input_schema

    # ── 执行 ──────────────────────────────────

    def execute(self, args: Dict[str, Any]) -> Any:
        """
        同步执行入口：在新的事件循环中运行异步调用。

        注意：若调用方已在异步上下文中，建议直接调用 execute_async()。
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有事件循环中（如 Jupyter、某些框架），创建 Task
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self.execute_async(args), loop
                )
                return future.result(timeout=REQUEST_TIMEOUT + 5)
            else:
                return loop.run_until_complete(self.execute_async(args))
        except RuntimeError:
            # 没有事件循环，创建新的
            return asyncio.run(self.execute_async(args))

    async def execute_async(self, args: Dict[str, Any]) -> Any:
        """异步执行，直接调用 MCP 服务器的 tools/call。"""
        result = await self._server.call_tool(self._name, args)
        # 提取可读内容：MCP 结果通常为 {"content": [{"type":"text","text":"..."}]}
        content = result.get("content", [])
        if content and isinstance(content, list):
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return "\n".join(texts) if texts else result
        return result


# ──────────────────────────────────────────────
# load_mcp_tools
# ──────────────────────────────────────────────

async def _load_mcp_tools_async() -> List[MCPTool]:
    """
    内部异步实现：读取 mcp.json，启动所有 MCP 服务器，汇总所有 MCPTool。
    """
    if not MCP_CONFIG_PATH.exists():
        return []

    try:
        config_text = MCP_CONFIG_PATH.read_text(encoding="utf-8")
        config = json.loads(config_text)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[MCP] 读取配置文件 {MCP_CONFIG_PATH} 失败：{exc}")
        return []

    servers_cfg = config.get("servers", [])
    if not servers_cfg:
        return []

    all_tools: List[MCPTool] = []

    async def start_server_and_collect(server_cfg: Dict[str, Any]) -> None:
        """启动单个服务器并收集其工具，失败时打印警告。"""
        server_name = server_cfg.get("name", "<未命名>")
        server = MCPServer(server_cfg)
        try:
            await asyncio.wait_for(server.start(), timeout=START_TIMEOUT)
            tool_defs = await asyncio.wait_for(
                server.list_tools(), timeout=REQUEST_TIMEOUT
            )
            for tool_def in tool_defs:
                all_tools.append(MCPTool(server, tool_def))
            print(
                f"[MCP] 服务器 '{server_name}' 已连接，"
                f"加载了 {len(tool_defs)} 个工具"
            )
        except asyncio.TimeoutError:
            print(f"[MCP] ⚠️  服务器 '{server_name}' 连接超时，已跳过")
            await server.stop()
        except Exception as exc:
            print(f"[MCP] ⚠️  服务器 '{server_name}' 启动失败，已跳过：{exc}")
            await server.stop()

    # 并发启动所有服务器
    await asyncio.gather(
        *[start_server_and_collect(cfg) for cfg in servers_cfg],
        return_exceptions=True,  # 单个 gather 任务异常不影响其他任务
    )

    return all_tools


def load_mcp_tools() -> List[MCPTool]:
    """
    读取 ~/.mira/mcp.json，启动所有配置的 MCP 服务器，返回所有 MCPTool 实例列表。

    超时或启动失败的服务器会被跳过并打印警告。
    配置文件不存在时返回空列表。
    """
    try:
        return asyncio.run(_load_mcp_tools_async())
    except RuntimeError:
        # 已在运行中的事件循环（极少见），尝试 get_event_loop
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_load_mcp_tools_async())


# ──────────────────────────────────────────────
# 简单自测（python -m ... 直接运行时）
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("=== MCP 客户端自测 ===")
    print(f"配置文件路径：{MCP_CONFIG_PATH}")

    if not MCP_CONFIG_PATH.exists():
        print("配置文件不存在，创建示例配置以供演示...")
        MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        example = {
            "servers": [
                {
                    "name": "demo",
                    "description": "演示（实际不会成功，仅验证流程）",
                    "command": "echo",
                    "args": ["hello"],
                }
            ]
        }
        MCP_CONFIG_PATH.write_text(json.dumps(example, ensure_ascii=False, indent=2))

    print("\n正在加载 MCP 工具（超时则跳过）...")
    tools = load_mcp_tools()
    print(f"\n共加载 {len(tools)} 个 MCP 工具：")
    for t in tools:
        print(f"  {t.name}: {t.description}")
