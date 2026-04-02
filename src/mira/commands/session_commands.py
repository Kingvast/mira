#!/usr/bin/env python3
"""
会话管理命令 - /session /resume /clear
"""

from mira.commands.base import Command


class SessionCommand(Command):
    """列出和管理历史会话"""

    @property
    def name(self) -> str:
        return "session"

    @property
    def description(self) -> str:
        return "会话管理。用法: /session [list|save|del <id>]"

    def execute(self, command: str, engine) -> None:
        from mira.utils.sessions import list_sessions, delete_session, save_session

        parts = command.strip().split()
        sub = parts[1] if len(parts) > 1 else "list"

        if sub == "list":
            sessions = list_sessions()
            if not sessions:
                print("暂无历史会话")
                return
            print(f"历史会话 (共 {len(sessions)} 条):\n")
            for s in sessions:
                updated = s.get("updated_at", "")[:16].replace("T", " ")
                count = s.get("message_count", 0)
                print(f"  [{s['session_id']}] {updated}  {s['provider']}/{s['model']}  {count}条消息")
                print(f"         {s['title']}")
            print("\n用法: /resume <会话ID> 恢复会话")

        elif sub == "save":
            provider = getattr(engine, "provider", "")
            model = getattr(engine, "model", "")
            messages = engine.app_state.export_messages()
            sid = engine.app_state.session_id
            path = save_session(sid, messages, {"provider": provider, "model": model})
            print(f"✓ 会话已保存 [{sid}] → {path}")

        elif sub == "del" and len(parts) > 2:
            sid = parts[2]
            ok = delete_session(sid)
            print(f"{'✓ 已删除' if ok else '✗ 未找到'} 会话 [{sid}]")

        else:
            print("用法: /session [list|save|del <id>]")


class ResumeCommand(Command):
    """恢复历史会话"""

    @property
    def name(self) -> str:
        return "resume"

    @property
    def description(self) -> str:
        return "恢复历史会话。用法: /resume <会话ID>"

    def execute(self, command: str, engine) -> None:
        from mira.utils.sessions import load_session, list_sessions

        parts = command.strip().split()
        if len(parts) < 2:
            # 无参数时列出最近 5 条
            sessions = list_sessions(5)
            if not sessions:
                print("暂无历史会话")
                return
            print("最近会话:")
            for s in sessions:
                updated = s.get("updated_at", "")[:16].replace("T", " ")
                print(f"  [{s['session_id']}] {updated}  {s['title']}")
            print("\n用法: /resume <会话ID>")
            return

        session_id = parts[1]
        data = load_session(session_id)
        if not data:
            print(f"✗ 未找到会话 [{session_id}]")
            return

        engine.app_state.clear_messages()
        for msg in data.get("messages", []):
            engine.app_state.add_message(msg)

        count = len(engine.app_state.messages)
        title = data.get("title", "")
        print(f"✓ 已恢复会话 [{session_id}]: {title}（{count} 条消息）")


class ClearCommand(Command):
    """清空当前对话历史"""

    @property
    def name(self) -> str:
        return "clear"

    @property
    def description(self) -> str:
        return "清空当前对话历史（不影响已保存的会话）"

    def execute(self, command: str, engine) -> None:
        count = len(engine.app_state.messages)
        engine.app_state.clear_messages()
        print(f"✓ 已清空对话历史（共 {count} 条消息）")
