#!/usr/bin/env python3
"""
Mira 主入口
"""

import sys
import os
from pathlib import Path

# 确保 src 在 Python 路径中
src_dir = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from mira.cli import parse_args
from mira.utils.config import load_config, save_config, get_api_key, get_default_model

# ── 提供商元数据（用于首次启动向导）──────────────────────────────────────────

_PROVIDER_META = [
    ("anthropic", "Anthropic Claude",   "ANTHROPIC_API_KEY",    "sk-ant-..."),
    ("openai",    "OpenAI GPT",          "OPENAI_API_KEY",       "sk-..."),
    ("deepseek",  "DeepSeek",            "DEEPSEEK_API_KEY",     "sk-..."),
    ("google",    "Google Gemini",       "GOOGLE_API_KEY",       "AIza..."),
    ("xai",       "xAI Grok",           "XAI_API_KEY",          "xai-..."),
    ("mistral",   "Mistral AI",         "MISTRAL_API_KEY",      "..."),
    ("qwen",      "Alibaba Qwen",       "DASHSCOPE_API_KEY",    "sk-..."),
    ("zhipu",     "Zhipu GLM",          "ZHIPU_API_KEY",        "..."),
    ("moonshot",  "Moonshot Kimi",      "MOONSHOT_API_KEY",     "sk-..."),
    ("doubao",    "Doubao (ByteDance)", "DOUBAO_API_KEY",       "..."),
    ("minimax",   "MiniMax",            "MINIMAX_API_KEY",      "..."),
    ("lingyi",    "Yi (01.AI)",         "LINGYI_API_KEY",       "..."),
    ("baichuan",  "Baichuan AI",        "BAICHUAN_API_KEY",     "..."),
    ("ernie",     "Baidu ERNIE",        "ERNIE_API_KEY",        "..."),
    ("spark",     "Spark (iFlytek)",    "SPARK_API_KEY",        "..."),
    ("longcat",   "LongCat",            "LONGCAT_API_KEY",      "ak_..."),
]


def _first_run_setup(provider: str, config: dict) -> str:
    """首次启动交互式向导：引导用户配置 API 密钥"""
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║         Mira — 首次使用配置向导              ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print(f"  未找到 [{provider}] 的 API 密钥。")
    print()

    # 列出所有提供商让用户选择
    print("  支持的 AI 提供商：")
    providers = [p[0] for p in _PROVIDER_META]
    for i, (pid, name, env, _) in enumerate(_PROVIDER_META, 1):
        cur = " ◀ 当前默认" if pid == provider else ""
        print(f"    {i:2}. {name:<20}  ({pid}){cur}")
    print()

    # 选择提供商
    try:
        choice = input(f"  请选择提供商编号（直接回车使用 {provider}）: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已取消")
        return ""

    selected_provider = provider
    if choice:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(_PROVIDER_META):
                selected_provider = _PROVIDER_META[idx][0]
            else:
                print(f"  无效编号，使用默认 {provider}")
        except ValueError:
            print(f"  无效输入，使用默认 {provider}")

    # 找到对应元数据
    meta = next((m for m in _PROVIDER_META if m[0] == selected_provider), None)
    if not meta:
        meta = (selected_provider, selected_provider, f"{selected_provider.upper()}_API_KEY", "...")

    _, name, env_var, hint = meta
    print()
    print(f"  配置 {name} API 密钥")
    print(f"  （也可以设置环境变量 {env_var}）")
    print()

    try:
        key = input(f"  请输入 API Key [{hint}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  已取消")
        return ""

    if not key:
        print()
        print(f"  未输入密钥。稍后可通过以下方式配置：")
        print(f"    环境变量: set {env_var}=your-key")
        print(f"    配置命令: mira /config key {selected_provider} your-key")
        print(f"    Web UI:  mira --web")
        return ""

    # 保存到配置文件
    config[f"{selected_provider}_api_key"] = key
    if selected_provider != config.get("default_provider"):
        config["default_provider"] = selected_provider
    save_config(config)

    print()
    print(f"  ✓ 已保存 {name} API 密钥到配置文件")
    if selected_provider != provider:
        print(f"  ✓ 默认提供商已切换为 {selected_provider}")
    print()

    return key


def main():
    """主函数"""
    args = parse_args()
    config = load_config()

    # ── 版本信息 ──────────────────────────────────────────────────────────────
    if getattr(args, "version", False):
        from mira import __version__, __app_name__
        print(f"{__app_name__} v{__version__}")
        return

    # ── Web UI 模式 ───────────────────────────────────────────────────────────
    if getattr(args, "web", False):
        try:
            from mira.web.server import start_server
        except ImportError as e:
            print(f"错误：Web UI 需要额外依赖\n  {e}")
            print("\n请安装：pip install fastapi uvicorn[standard] websockets aiofiles")
            sys.exit(1)

        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8080)
        no_browser = getattr(args, "no_browser", False)
        start_server(host=host, port=port, open_browser=not no_browser)
        return

    # ── CLI 模式 ──────────────────────────────────────────────────────────────
    provider = getattr(args, "provider", None) or config.get("default_provider", "deepseek")
    model = getattr(args, "model", None)
    skip_perms = getattr(args, "dangerously_skip_permissions", False)

    # 检查 API 密钥
    api_key = get_api_key(provider, config)
    if not api_key:
        api_key = _first_run_setup(provider, config)
        if not api_key:
            sys.exit(1)
        # 向导可能切换了 provider，重新加载配置
        config = load_config()
        provider = config.get("default_provider", provider)

    try:
        from mira.query import QueryEngine
        engine = QueryEngine(
            config=config,
            provider=provider,
            model=model or get_default_model(provider, config),
            skip_permissions=skip_perms,
        )
        engine.run(args)
    except ValueError as e:
        print(f"错误：{e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n再见！")


if __name__ == "__main__":
    # PyInstaller Windows 多进程支持（必须在 main() 之前调用）
    import multiprocessing
    multiprocessing.freeze_support()
    main()
