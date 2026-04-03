#!/usr/bin/env python3
"""
API 服务模块 - 工厂函数 + 客户端注册
"""

from mira.services.api.base import BaseAPIClient
from mira.services.api.openai_compatible import OpenAICompatibleClient

# Anthropic 客户端（原生 SDK）
from mira.services.api.anthropic_client import AnthropicClient

# Google Gemini（可选依赖）
_GoogleClient = None
try:
    from mira.services.api.google_client import GoogleClient as _GoogleClient
except ImportError:
    pass


# ─── 工厂函数 ─────────────────────────────────────────────────────────────────

def create_api_client(provider: str, config: dict) -> BaseAPIClient:
    """
    根据 provider 创建对应的 API 客户端。
    config 至少包含: api_key, model, temperature
    """
    # Anthropic 原生
    if provider == "anthropic":
        return AnthropicClient(config)

    # Google Gemini
    if provider == "google":
        if _GoogleClient is None:
            raise ImportError("Google Gemini 需要安装: pip install google-generativeai")
        return _GoogleClient(config)

    # 所有 OpenAI 兼容提供商
    # base_url 优先级：用户传入 > PROVIDER_DEFAULTS > 兜底
    from mira.utils.config import PROVIDER_DEFAULTS
    pdef = PROVIDER_DEFAULTS.get(provider, {})
    base_url = (
        config.get("base_url")
        or pdef.get("base_url")
        or "https://api.openai.com/v1"
    )
    merged = {**config, "base_url": base_url}
    # 部分提供商使用非标准 chat endpoint（如 MiniMax、ERNIE、Spark）
    if "chat_url" not in merged and pdef.get("chat_url"):
        merged["chat_url"] = pdef["chat_url"]
    return OpenAICompatibleClient(merged)
