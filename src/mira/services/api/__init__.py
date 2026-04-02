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


# ─── 各提供商 base_url ────────────────────────────────────────────────────────

_PROVIDER_BASE_URLS = {
    "openai":    "https://api.openai.com/v1",
    "deepseek":  "https://api.deepseek.com/v1",
    "zhipu":     "https://open.bigmodel.cn/api/paas/v4",
    "longcat":   "https://api.longcat.chat/openai/v1",
    "doubao":    "https://ark.cn-beijing.volces.com/api/v3",
    "moonshot":  "https://api.moonshot.cn/v1",
    "minimax":   "https://api.minimax.chat/v1",
}


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
    base_url = (
        config.get("base_url")                      # 用户自定义优先
        or _PROVIDER_BASE_URLS.get(provider)        # 内置默认
        or "https://api.openai.com/v1"              # 最终兜底
    )
    merged = {**config, "base_url": base_url}
    return OpenAICompatibleClient(merged)
