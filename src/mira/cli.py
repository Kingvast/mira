#!/usr/bin/env python3
"""
CLI 参数解析模块
"""

import argparse
import os
import sys
from pathlib import Path

# 添加 src 目录到 Python 路径（用于导入 config）
src_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(src_dir))

from mira.utils.config import load_config, get_default_model


def parse_args():
    """解析命令行参数"""
    # 先加载配置获取默认值
    config = load_config()
    default_provider = config.get("default_provider", "openai")
    default_model = config.get("default_model", get_default_model(default_provider, config))
    default_temperature = config.get("temperature", 0.7)
    
    parser = argparse.ArgumentParser(
        prog="mira",
        description="Mira — AI 智能编程助手，支持 9 大 AI 提供商"
    )
    
    # 版本信息
    parser.add_argument(
        "--version",
        action="store_true",
        help="显示版本信息"
    )
    
    # 模型相关
    parser.add_argument(
        "--provider",
        type=str,
        default=default_provider,
        choices=["openai", "anthropic", "google", "zhipu", "deepseek", "longcat", "doubao", "moonshot", "minimax"],
        help="AI 服务提供商 (openai/anthropic/google/zhipu/deepseek/longcat/doubao/moonshot/minimax)"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default=default_model,
        help="使用的模型"
    )
    
    parser.add_argument(
        "--temperature",
        type=float,
        default=default_temperature,
        help="生成温度 (0.0-1.0)"
    )
    
    # 执行模式
    parser.add_argument(
        "-p", "--print",
        action="store_true",
        help="非交互模式，打印结果后退出"
    )
    
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="输出格式"
    )
    
    # 权限
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="自动批准所有工具调用"
    )
    
    # 上下文
    parser.add_argument(
        "--add-dir",
        type=str,
        action="append",
        help="添加额外的目录到上下文"
    )
    
    parser.add_argument(
        "--system-prompt",
        type=str,
        help="自定义系统提示"
    )
    
    # 集成
    parser.add_argument(
        "--mcp-config",
        type=str,
        help="MCP 服务器配置文件"
    )
    
    parser.add_argument(
        "--settings",
        type=str,
        help="设置文件路径"
    )
    
    # 调试
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启调试模式"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出"
    )
    
    # ── Web UI 模式 ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Web UI（浏览器界面）"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Web UI 监听地址（默认 127.0.0.1）"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Web UI 端口（默认 8080）"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动 Web UI 时不自动打开浏览器"
    )

    # ── 位置参数 ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "prompt",
        nargs="*",
        help="直接输入的提示（非交互模式）"
    )

    return parser.parse_args()
