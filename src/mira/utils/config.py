#!/usr/bin/env python3
"""
配置管理 - 支持 15 大 AI 提供商的 API Key / Model 配置
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
        "models": [
            "gpt-5.4", "gpt-5.4-mini",
            "gpt-4o", "gpt-4o-mini",
            "gpt-4-turbo", "gpt-3.5-turbo",
            "text-embedding-3-large", "text-embedding-3-small",
        ],
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "name": "Anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com",
        "models": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
        ],
        "default_model": "claude-sonnet-4-6",
    },
    "google": {
        "name": "Google Gemini",
        "api_key_env": "GOOGLE_API_KEY",
        "base_url": "",
        "models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ],
        "default_model": "gemini-2.5-flash",
    },
    "xai": {
        "name": "xAI Grok",
        "api_key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "models": [
            "grok-4",
            "grok-3",
            "grok-3-mini",
        ],
        "default_model": "grok-3",
    },
    "mistral": {
        "name": "Mistral AI",
        "api_key_env": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "models": [
            "mistral-large-latest",
            "mistral-large-2411",
            "open-mistral-nemo",
            "codestral-latest",
        ],
        "default_model": "mistral-large-latest",
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "name": "Alibaba Qwen",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": [
            "qwen-max",
            "qwen-plus",
            "qwen-turbo",
            "qwen-long",
            "qwen-vl-max",
        ],
        "default_model": "qwen-max",
    },
    "zhipu": {
        "name": "Zhipu GLM",
        "api_key_env": "ZHIPU_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [
            "glm-5",
            "glm-5-turbo",
            "glm-4",
            "glm-4.7-flash",
            "glm-4.6v",
        ],
        "default_model": "glm-5",
    },
    "moonshot": {
        "name": "Moonshot Kimi",
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1",
        "models": [
            "kimi-k2.5",
            "moonshot-v1-128k",
            "moonshot-v1-32k",
            "moonshot-v1-8k",
        ],
        "default_model": "kimi-k2.5",
    },
    "doubao": {
        "name": "Doubao (ByteDance)",
        "api_key_env": "DOUBAO_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [
            "doubao-seed-2-0-pro-260215",
            "doubao-seed-2-0-lite-260215",
            "doubao-seed-1-6-251015",
            "doubao-pro-32k",
            "doubao-lite-32k",
        ],
        "default_model": "doubao-seed-2-0-pro-260215",
    },
    "minimax": {
        "name": "MiniMax",
        "api_key_env": "MINIMAX_API_KEY",
        "base_url": "https://api.minimax.chat/v1",
        "chat_url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
        "models": [
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
        ],
        "default_model": "MiniMax-M2.7",
    },
    "lingyi": {
        "name": "Yi (01.AI)",
        "api_key_env": "LINGYI_API_KEY",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "models": [
            "yi-large",
            "yi-large-turbo",
            "yi-vision",
        ],
        "default_model": "yi-large",
    },
    "baichuan": {
        "name": "Baichuan AI",
        "api_key_env": "BAICHUAN_API_KEY",
        "base_url": "https://api.baichuan-ai.com/v1",
        "models": [
            "Baichuan4",
            "Baichuan4-Turbo",
            "Baichuan4-Air",
            "Baichuan3-Turbo",
            "Baichuan3-Turbo-128k",
        ],
        "default_model": "Baichuan4",
    },
    "ernie": {
        "name": "Baidu ERNIE",
        "api_key_env": "ERNIE_API_KEY",
        "base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop",
        "chat_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
        "models": [
            "ERNIE-4.0-Turbo-8K",
            "ERNIE-3.5-8K",
            "ERNIE-3.5-128K",
            "ERNIE-Speed-8K",
            "ERNIE-Speed-128K",
        ],
        "default_model": "ERNIE-4.0-Turbo-8K",
    },
    "spark": {
        "name": "Spark (iFlytek)",
        "api_key_env": "SPARK_API_KEY",
        "base_url": "https://spark-api-open.xf-yun.com/v1",
        "models": [
            "4.0Ultra",
            "generalv3.5",
            "general",
        ],
        "default_model": "4.0Ultra",
    },
    "longcat": {
        "name": "LongCat",
        "api_key_env": "LONGCAT_API_KEY",
        "base_url": "https://api.longcat.chat/openai/v1",
        "models": [
            "LongCat-Flash-Omni-2603",
            "LongCat-Flash-Chat-2602-Exp",
            "LongCat-Flash-Thinking-2601",
            "LongCat-Flash-Thinking",
            "LongCat-Flash-Chat",
            "LongCat-Flash-Lite",
        ],
        "default_model": "LongCat-Flash-Omni-2603",
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

    # 内置厂商的模型列表始终以 PROVIDER_DEFAULTS 为准，防止配置文件中的旧数据覆盖
    for pid, pdef in PROVIDER_DEFAULTS.items():
        config.setdefault("provider_models", {})[pid] = pdef["models"]

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
    # 不写入空值；provider_models 始终从 PROVIDER_DEFAULTS 派生，不持久化避免过期
    clean = {k: v for k, v in config.items() if v is not None and v != "" and k != "provider_models"}
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
    """获取提供商的默认/已选模型（优先用户选择，不影响完整模型列表）"""
    selected = config.get("provider_selected_models", {}).get(provider)
    if selected:
        return selected
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
