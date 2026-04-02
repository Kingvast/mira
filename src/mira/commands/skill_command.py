#!/usr/bin/env python3
"""
/skill 命令 — 执行预定义技能模板
"""

from mira.commands.base import Command


class SkillCommand(Command):
    """调用预定义技能"""

    @property
    def name(self) -> str:
        return "skill"

    @property
    def description(self) -> str:
        return "执行预定义技能。用法: /skill [list|<name>|save <name>|del <name>]"

    def execute(self, command: str, engine) -> None:
        from mira.services.skills import (
            list_skills, get_skill, save_user_skill, delete_user_skill,
        )
        try:
            from mira.query import _cyan, _bold, _dim, _gray, _yellow, _green, _red
        except ImportError:
            def _cyan(s): return s
            def _bold(s): return s
            def _dim(s): return s
            def _gray(s): return s
            def _yellow(s): return s
            def _green(s): return s
            def _red(s): return s

        parts = command.strip().split(maxsplit=2)
        # parts[0] = "skill", parts[1] = subcommand, parts[2] = rest
        sub = parts[1] if len(parts) > 1 else "list"

        if sub == "list":
            skills = list_skills()
            if not skills:
                print("暂无可用技能")
                return
            sep = _gray("─" * 48)
            print(f"\n{sep}")
            print(f"  {_bold('可用技能')}  {_dim(f'共 {len(skills)} 个')}")
            print(sep)
            for s in skills:
                is_user = s.get("source") == "user"
                tag = _yellow(" [自定义]") if is_user else _dim(" [内置]")
                pad = max(14 - len(s["name"]), 1)
                print(f"  {_cyan('/skill ' + s['name'])}{' ' * pad}{_dim(s['description'])}{tag}")
            print(sep)
            print(f"  用法: {_yellow('/skill <name>')}  执行技能")
            print(f"  用法: {_yellow('/skill save <name> <描述> ### <提示词>')}  保存自定义技能")
            print(sep + "\n")
            return

        if sub == "save":
            # /skill save <name> <description> ### <prompt>
            rest = parts[2] if len(parts) > 2 else ""
            if "###" in rest:
                meta, prompt = rest.split("###", 1)
                meta_parts = meta.strip().split(maxsplit=1)
                name = meta_parts[0] if meta_parts else ""
                description = meta_parts[1] if len(meta_parts) > 1 else name
                prompt = prompt.strip()
            else:
                name_parts = rest.strip().split(maxsplit=1)
                name = name_parts[0] if name_parts else ""
                description = name_parts[1] if len(name_parts) > 1 else name
                prompt = f"请执行 {name} 技能。"

            if not name:
                print(_red("用法: /skill save <name> <描述> ### <提示词>"))
                return

            try:
                path = save_user_skill(name, description, prompt)
                print(f"{_green('✓')} 技能 [{_cyan(name)}] 已保存 → {_dim(path)}")
            except ValueError as e:
                print(_red(f"✗ {e}"))
            return

        if sub == "del":
            name = parts[2].strip() if len(parts) > 2 else ""
            if not name:
                print(_red("用法: /skill del <name>"))
                return
            ok = delete_user_skill(name)
            if ok:
                print(f"{_green('✓')} 已删除技能 [{_cyan(name)}]")
            else:
                print(_red(f"✗ 未找到自定义技能 [{name}]（内置技能不可删除）"))
            return

        # 执行技能：/skill <name>
        name = sub
        skill = get_skill(name)
        if not skill:
            print(_red(f"✗ 未找到技能 [{name}]，用 /skill list 查看可用技能"))
            return

        import asyncio
        from mira.query import _cli_callback

        print(f"\n{_gray('▶')} 执行技能 {_cyan(_bold(name))}: {_dim(skill['description'])}\n")

        async def run():
            await engine.process_message(skill["prompt"], callback=_cli_callback)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(run())
            else:
                loop.run_until_complete(run())
        except RuntimeError:
            asyncio.run(run())
