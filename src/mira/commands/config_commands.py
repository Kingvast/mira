#!/usr/bin/env python3
"""
配置管理命令 - /config /permissions
"""

import json
from mira.commands.base import Command


class ConfigCommand(Command):
    """查看和修改配置"""

    @property
    def name(self) -> str:
        return "config"

    @property
    def description(self) -> str:
        return "配置管理。用法: /config [show|set <键> <值>|key <提供商> <APIKey>|provider <子命令>|path]"

    def execute(self, command: str, engine) -> None:
        from mira.utils.config import (
            load_config, save_config, get_config_for_display,
            get_providers, add_custom_provider, remove_custom_provider,
            PROVIDER_DEFAULTS, mask_api_key,
        )

        parts = command.strip().split(None, 3)
        sub = parts[1] if len(parts) > 1 else "show"

        if sub == "show":
            display = get_config_for_display(engine.config)
            print("当前配置:\n")
            print(f"  默认提供商  : {display.get('default_provider', '—')}")
            print(f"  当前提供商  : {engine.provider}")
            print(f"  当前模型    : {engine.model}")
            print(f"  温度        : {display.get('temperature', 0.7)}")
            print(f"  最大 Token  : {display.get('max_tokens', 4096)}")
            print(f"  跳过权限确认: {display.get('dangerously_skip_permissions', False)}")
            print("\n  内置提供商 API 密钥:")
            for pid, pdef in PROVIDER_DEFAULTS.items():
                key = display.get(f"{pid}_api_key", "")
                status = key if key else "未配置"
                print(f"    {pid:<12} {status}")
            custom = display.get("custom_providers", {})
            if custom:
                print("\n  自定义提供商:")
                for pid, p in custom.items():
                    key_status = p.get("api_key", "") or "未配置"
                    models = ", ".join(p.get("models", []))
                    print(f"    {pid:<12} {p.get('name',pid)} | {p.get('base_url','')} | key:{key_status} | models:{models}")
            print(f"\n配置文件: ~/.mira/config.json")

        elif sub == "set" and len(parts) >= 4:
            key, value = parts[2], parts[3]
            for conv in (json.loads, int, float):
                try:
                    value = conv(value)
                    break
                except Exception:
                    pass
            engine.config[key] = value
            save_config(engine.config)
            print(f"✓ 已设置 {key} = {value!r}")

        elif sub == "key" and len(parts) >= 4:
            provider = parts[2]
            api_key = parts[3]
            cfg = load_config()
            custom_ids = list(cfg.get("custom_providers", {}).keys())
            if provider not in PROVIDER_DEFAULTS and provider not in custom_ids:
                print(f"✗ 未知提供商: {provider}")
                print(f"内置: {', '.join(PROVIDER_DEFAULTS.keys())}")
                if custom_ids:
                    print(f"自定义: {', '.join(custom_ids)}")
                return
            if provider in PROVIDER_DEFAULTS:
                engine.config[f"{provider}_api_key"] = api_key
            else:
                engine.config.setdefault("custom_providers", {})[provider]["api_key"] = api_key
            save_config(engine.config)
            print(f"✓ 已保存 {provider} API 密钥 ({mask_api_key(api_key)})")

        elif sub == "provider":
            # /config provider <add|list|remove> ...
            pparts = command.strip().split(None, 6)
            psub = pparts[2] if len(pparts) > 2 else "list"

            if psub == "list":
                cfg = load_config()
                custom = cfg.get("custom_providers", {})
                if not custom:
                    print("暂无自定义提供商。使用 /config provider add 添加。")
                else:
                    print(f"自定义提供商 ({len(custom)} 个):\n")
                    for pid, p in custom.items():
                        models_str = ", ".join(p.get("models", []))
                        key_str = mask_api_key(p.get("api_key", "")) or "未配置"
                        print(f"  [{pid}] {p.get('name', pid)}")
                        print(f"    base_url : {p.get('base_url', '')}")
                        print(f"    api_key  : {key_str}")
                        print(f"    models   : {models_str or '—'}")

            elif psub == "add":
                # /config provider add <id> <name> <base_url> <api_key> [model1,model2]
                if len(pparts) < 7:
                    print("用法: /config provider add <id> <name> <base_url> <api_key> [model1,model2,...]")
                    print("示例: /config provider add myapi MyAPI https://api.example.com/v1 sk-xxx my-model-v1")
                    return
                pid, name, base_url, api_key = pparts[2], pparts[3], pparts[4], pparts[5]
                # 注意: pparts[0]="config", pparts[1]="provider", pparts[2]="add"
                # 重新解析避免 split 层数问题
                raw = command.strip().split(None)
                # /config provider add <id> <name> <base_url> <api_key> [models...]
                if len(raw) < 7:
                    print("用法: /config provider add <id> <名称> <base_url> <api_key> [模型1 模型2 ...]")
                    return
                pid, name, base_url, api_key = raw[3], raw[4], raw[5], raw[6]
                models = raw[7:]  # 可选，后面的都是模型名
                if pid in PROVIDER_DEFAULTS:
                    print(f"✗ '{pid}' 是内置提供商 ID，请换一个名字")
                    return
                cfg = load_config()
                add_custom_provider(pid, name, base_url, api_key, models, cfg)
                save_config(cfg)
                engine.config = cfg
                print(f"✓ 已添加自定义提供商 [{pid}] {name}")
                if models:
                    print(f"  模型: {', '.join(models)}")

            elif psub == "remove":
                if len(pparts) < 4:
                    print("用法: /config provider remove <id>")
                    return
                raw = command.strip().split(None)
                pid = raw[3] if len(raw) > 3 else ""
                cfg = load_config()
                if remove_custom_provider(pid, cfg):
                    save_config(cfg)
                    engine.config = cfg
                    print(f"✓ 已删除自定义提供商: {pid}")
                else:
                    print(f"✗ 未找到自定义提供商: {pid}")

            else:
                print("用法:")
                print("  /config provider list                                    — 列出所有自定义提供商")
                print("  /config provider add <id> <名称> <base_url> <api_key> [模型...] — 添加")
                print("  /config provider remove <id>                             — 删除")

        elif sub == "path":
            from pathlib import Path
            print(f"配置文件路径: {Path.home() / '.mira' / 'config.json'}")

        else:
            print("用法:")
            print("  /config show                              — 显示当前配置")
            print("  /config set <键> <值>                     — 修改配置项")
            print("  /config key <提供商> <APIKey>             — 保存 API 密钥")
            print("  /config provider list/add/remove          — 管理自定义提供商")
            print("  /config path                              — 显示配置文件路径")


class PermissionsCommand(Command):
    """查看权限设置"""

    @property
    def name(self) -> str:
        return "permissions"

    @property
    def description(self) -> str:
        return "查看当前权限设置和工具列表"

    def execute(self, command: str, engine) -> None:
        skip = engine.skip_permissions
        print(f"权限模式: {'⚡ 自动批准（dangerously_skip_permissions=true）' if skip else '🔒 手动确认'}")
        print(f"\n已注册工具 ({len(engine.tools)} 个):\n")
        for tool in engine.tools:
            desc = tool.description.split("\n")[0][:60]
            print(f"  • {tool.name:<25} {desc}")
