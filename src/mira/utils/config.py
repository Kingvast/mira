#!/usr/bin/env python3
"""
配置管理 - 支持 9 大 AI 提供商的 API Key / Model 配置
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict

# 全局配置目录
_CONFIG_DIR = Path.home() / ".mira"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# ─── 所有支持的提供商 ─────────────────────────────────────────────────────────

PROVIDER_DEFAULTS: Dict[str, Dict] = {
    "openai": {
        "name": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "name": "Anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
                   "claude-3-opus-20240229", "claude-3-sonnet-20240229"],
        "default_model": "claude-opus-4-6",
    },
    "google": {
        "name": "Google Gemini",
        "api_key_env": "GOOGLE_API_KEY",
        "base_url": "",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"],
        "default_model": "gemini-1.5-pro",
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "api_key_env": "ZHIPU_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4", "glm-4-flash", "glm-3-turbo"],
        "default_model": "glm-4-plus",
    },
    "moonshot": {
        "name": "月之暗面 Kimi",
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"],
        "default_model": "moonshot-v1-32k",
    },
    "doubao": {
        "name": "豆包 (字节)",
        "api_key_env": "DOUBAO_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k", "doubao-pro-4k", "doubao-lite-4k"],
        "default_model": "doubao-pro-32k",
    },
    "minimax": {
        "name": "MiniMax",
        "api_key_env": "MINIMAX_API_KEY",
        "base_url": "https://api.minimax.chat/v1",
        "models": ["abab6.5s-chat", "abab6.5-chat"],
        "default_model": "abab6.5s-chat",
    },
    "longcat": {
        "name": "LongCat",
        "api_key_env": "LONGCAT_API_KEY",
        "base_url": "https://api.longcat.chat/openai/v1",
        "models": ["LongCat-Flash-Omni-2603", "LongCat-Flash-Thinking-2601",
                   "LongCat-Flash-Chat", "LongCat-Flash-Lite"],
        "default_model": "LongCat-Flash-Chat",
    },
}


def load_config() -> dict:
    """加载配置（优先级：环境变量 > ~/.mira/config.json > 当前目录 config.json）"""
    config: dict = {
        "default_provider": "deepseek",
        "temperature": 0.7,
        "max_tokens": 4096,
        "dangerously_skip_permissions": False,
        "extended_thinking": False,
        "prompt_caching": True,
        "provider_models": {p: d["models"] for p, d in PROVIDER_DEFAULTS.items()},
        "custom_providers": {},
    }

    # 配置文件搜索顺序
    search = [_CONFIG_FILE, Path.cwd() / "config.json"]
    for cfg_path in search:
        if cfg_path.exists():
            try:
                file_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                config.update(file_cfg)
                break
            except Exception as e:
                print(f"警告：读取配置文件 {cfg_path} 失败: {e}")

    # 环境变量最高优先级（覆盖文件配置）
    for provider, pdef in PROVIDER_DEFAULTS.items():
        val = os.environ.get(pdef["api_key_env"])
        if val:
            config[f"{provider}_api_key"] = val

    return config


def save_config(config: dict, path: Optional[Path] = None):
    """保存配置到文件"""
    if path is None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = _CONFIG_FILE
    # 不写入空值
    clean = {k: v for k, v in config.items() if v is not None and v != ""}
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def get_api_key(provider: str, config: dict) -> Optional[str]:
    """获取指定提供商的 API 密钥"""
    key = config.get(f"{provider}_api_key")
    if not key:
        env = PROVIDER_DEFAULTS.get(provider, {}).get("api_key_env", "")
        key = os.environ.get(env) if env else None
    if not key:
        # 自定义提供商的 api_key 存在 custom_providers 里
        key = config.get("custom_providers", {}).get(provider, {}).get("api_key")
    return key or None


def get_provider_base_url(provider: str, config: dict) -> Optional[str]:
    """获取提供商的 base_url（优先用户配置，其次内置默认，最后自定义）"""
    # 用户在 provider_base_urls 里的覆盖
    url = config.get("provider_base_urls", {}).get(provider)
    if url:
        return url
    # 内置提供商默认
    url = PROVIDER_DEFAULTS.get(provider, {}).get("base_url")
    if url:
        return url
    # 自定义提供商
    return config.get("custom_providers", {}).get(provider, {}).get("base_url")


def get_default_model(provider: str, config: dict) -> str:
    """获取提供商的默认模型"""
    models = get_models(provider, config)
    return models[0] if models else ""


def get_models(provider: str, config: dict) -> List[str]:
    """获取提供商的完整模型列表"""
    # provider_models 覆盖
    models = config.get("provider_models", {}).get(provider)
    if models:
        return models
    # 内置默认
    builtin = PROVIDER_DEFAULTS.get(provider, {}).get("models")
    if builtin:
        return builtin
    # 自定义提供商
    return config.get("custom_providers", {}).get(provider, {}).get("models", [])


def get_providers(config: dict = None) -> List[Dict]:
    """获取所有提供商基础信息（内置 + 自定义）"""
    result = [
        {"id": pid, "name": p["name"], "default_model": p["default_model"], "custom": False}
        for pid, p in PROVIDER_DEFAULTS.items()
    ]
    if config:
        for pid, p in config.get("custom_providers", {}).items():
            models = p.get("models", [])
            result.append({
                "id": pid,
                "name": p.get("name", pid),
                "default_model": models[0] if models else "",
                "custom": True,
                "base_url": p.get("base_url", ""),
            })
    return result


def add_custom_provider(provider_id: str, name: str, base_url: str,
                        api_key: str, models: List[str], config: dict) -> dict:
    """添加或更新自定义提供商，返回更新后的 config"""
    config.setdefault("custom_providers", {})[provider_id] = {
        "name": name,
        "base_url": base_url,
        "api_key": api_key,
        "models": models,
    }
    return config


def remove_custom_provider(provider_id: str, config: dict) -> bool:
    """删除自定义提供商，返回是否成功"""
    providers = config.get("custom_providers", {})
    if provider_id in providers:
        del providers[provider_id]
        return True
    return False


def mask_api_key(key: Optional[str]) -> str:
    """脱敏显示 API 密钥"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def get_config_for_display(config: dict) -> dict:
    """返回用于界面展示的脱敏配置"""
    d = dict(config)
    for provider in PROVIDER_DEFAULTS:
        key_name = f"{provider}_api_key"
        if d.get(key_name):
            d[key_name] = mask_api_key(d[key_name])
    # 脱敏自定义提供商 api_key
    custom = d.get("custom_providers", {})
    if custom:
        d["custom_providers"] = {
            pid: {**p, "api_key": mask_api_key(p.get("api_key", ""))}
            for pid, p in custom.items()
        }
    return d
