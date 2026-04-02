#!/usr/bin/env python3
"""
Skills 系统 — 预定义的提示模板

内置 skills 存储在本模块中，用户自定义 skills 存储在 ~/.mira/skills/ 目录下的 Markdown 文件中。
Markdown 文件格式：frontmatter（name、description）+ body 作为 prompt。
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


# 用户 skills 目录
SKILLS_DIR = Path.home() / ".mira" / "skills"

# ──────────────────────────────────────────────
# 内置 Skills
# ──────────────────────────────────────────────

BUILTIN_SKILLS: Dict[str, Dict[str, str]] = {
    "commit": {
        "name": "commit",
        "description": "生成规范的 Conventional Commits 提交消息",
        "prompt": """请分析当前 git 差异（先用 GitDiffTool 获取），然后生成一个符合 Conventional Commits 规范的提交消息。

格式：
<type>(<scope>): <description>

[可选 body：解释 why 而非 what]

类型：feat(新功能) fix(修复) docs(文档) style(格式) refactor(重构) test(测试) chore(杂项)

要求：
- 描述用中文，不超过 50 字
- 只输出提交消息本身，不要多余解释""",
    },
    "review": {
        "name": "review",
        "description": "对当前文件或 git diff 进行代码审查",
        "prompt": """请对当前修改的代码进行专业的代码审查。先用 GitDiffTool 获取变更，然后分析：

1. **代码质量**：逻辑是否正确，边界情况是否处理
2. **安全性**：是否存在安全漏洞（注入、权限等）
3. **性能**：是否有性能问题
4. **可维护性**：命名是否清晰，代码是否易读
5. **具体改进建议**：给出可操作的修改建议

用 Markdown 格式输出，重要问题用 ⚠️ 标注，建议用 💡 标注。""",
    },
    "explain": {
        "name": "explain",
        "description": "解释当前目录的代码结构和逻辑",
        "prompt": """请分析并解释当前项目/文件的代码。先用 LSTool 和 GlobTool 了解结构，再用 FileReadTool 读取关键文件。

需要解释：
1. 整体架构和职责划分
2. 核心数据流程
3. 关键算法或设计模式
4. 入口点和主要模块

用通俗易懂的中文解释，配合代码示例。""",
    },
    "refactor": {
        "name": "refactor",
        "description": "分析代码并提出重构建议",
        "prompt": """请分析当前代码并提出具体的重构建议。

重点关注：
1. **重复代码**：识别可抽取的公共逻辑
2. **复杂函数**：建议拆分过长或过复杂的函数
3. **命名问题**：变量名、函数名是否清晰
4. **设计模式**：是否有更优雅的设计方式
5. **依赖关系**：模块耦合是否过高

对每个问题给出：现状描述 → 问题所在 → 具体改法（含代码示例）""",
    },
    "test": {
        "name": "test",
        "description": "为当前代码生成测试用例",
        "prompt": """请为当前代码生成完整的测试用例。先读取要测试的代码文件，然后生成测试：

1. **单元测试**：测试每个函数的核心逻辑
2. **边界情况**：空值、异常输入、边界值
3. **集成测试**：如果有多个模块交互
4. **Mock**：对外部依赖（API、文件、数据库）进行 Mock

使用项目当前使用的测试框架（Python 用 pytest，JS 用 jest 等），直接写出可运行的测试代码。""",
    },
    "debug": {
        "name": "debug",
        "description": "系统性地分析和定位 bug",
        "prompt": """请帮我系统性地调试这个问题。

请按以下步骤进行：
1. **重现**：明确问题的触发条件
2. **定位**：通过代码分析找到可能的根因
3. **验证**：提出验证假设的方法
4. **修复**：给出具体的修复代码

如果需要，请用 BashTool 运行诊断命令，用 FileReadTool 读取相关代码。""",
    },
    "docs": {
        "name": "docs",
        "description": "为当前代码生成文档",
        "prompt": """请为当前代码生成完整的文档。读取相关文件后生成：

1. **README 或模块文档**：功能概述、安装、快速开始
2. **API 文档**：每个公开函数/类的参数、返回值、示例
3. **注释**：复杂逻辑处添加内联注释

使用对应语言的文档规范（Python 用 Google docstring，JS 用 JSDoc 等），直接输出可用的文档。""",
    },
    "summarize": {
        "name": "summarize",
        "description": "总结当前对话的关键决策和行动",
        "prompt": """请总结我们这次对话的关键内容：

1. **问题描述**：我们处理的核心问题是什么
2. **决策**：做了哪些重要的技术决策，以及原因
3. **完成的工作**：实际修改/创建了什么
4. **待处理**：还有哪些事项需要后续处理
5. **注意事项**：有什么重要的注意点或风险

用简洁的 Markdown 格式输出，方便保存到 NOTES.md。""",
    },
}


# ──────────────────────────────────────────────
# Markdown 解析 / 序列化
# ──────────────────────────────────────────────

def _parse_skill_markdown(text: str, filename: str) -> Optional[Dict[str, str]]:
    """
    解析用户 skill 的 Markdown 文件。

    格式：
        ---
        name: <name>
        description: <description>
        ---
        <prompt body>

    返回 dict 或 None（解析失败时）。
    """
    # 尝试提取 YAML frontmatter
    frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)
    match = frontmatter_re.match(text)
    if not match:
        # 没有 frontmatter，把文件名当 name，整个内容当 prompt
        name = Path(filename).stem
        return {
            "name": name,
            "description": f"用户自定义 skill: {name}",
            "prompt": text.strip(),
            "source": "user",
        }

    frontmatter_block, body = match.group(1), match.group(2)

    # 简单解析 key: value 行（不依赖 PyYAML）
    meta: Dict[str, str] = {}
    for line in frontmatter_block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()

    name = meta.get("name") or Path(filename).stem
    description = meta.get("description") or f"用户自定义 skill: {name}"
    prompt = body.strip()

    if not prompt:
        return None  # prompt 为空，视为无效 skill

    return {
        "name": name,
        "description": description,
        "prompt": prompt,
        "source": "user",
    }


def _skill_to_markdown(name: str, description: str, prompt: str) -> str:
    """将 skill 序列化为 Markdown 格式。"""
    return f"---\nname: {name}\ndescription: {description}\n---\n{prompt}\n"


# ──────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────

def list_skills() -> List[Dict[str, Any]]:
    """
    返回所有可用 skills 的列表（内置 + 用户自定义）。

    每个元素包含：name, description, source ('builtin' | 'user')。
    用户 skill 与内置 skill 同名时，用户 skill 优先（覆盖显示）。
    """
    # 先收集内置 skills
    skills: Dict[str, Dict[str, Any]] = {}
    for key, skill in BUILTIN_SKILLS.items():
        skills[key] = {**skill, "source": "builtin"}

    # 再叠加用户 skills（覆盖同名内置）
    if SKILLS_DIR.is_dir():
        for md_file in sorted(SKILLS_DIR.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
                parsed = _parse_skill_markdown(text, md_file.name)
                if parsed:
                    skills[parsed["name"]] = parsed
            except OSError as exc:
                print(f"[skills] 读取 {md_file} 失败：{exc}")

    return list(skills.values())


def get_skill(name: str) -> Optional[Dict[str, Any]]:
    """
    返回单个 skill 的完整信息（包含 prompt）。

    优先返回用户自定义版本；若不存在则返回内置版本；都不存在返回 None。
    """
    # 先在用户目录查找
    if SKILLS_DIR.is_dir():
        md_file = SKILLS_DIR / f"{name}.md"
        if md_file.exists():
            try:
                text = md_file.read_text(encoding="utf-8")
                parsed = _parse_skill_markdown(text, md_file.name)
                if parsed:
                    return parsed
            except OSError as exc:
                print(f"[skills] 读取 {md_file} 失败：{exc}")

    # 再从内置 skills 查找
    if name in BUILTIN_SKILLS:
        return {**BUILTIN_SKILLS[name], "source": "builtin"}

    return None


def save_user_skill(name: str, description: str, prompt: str) -> Path:
    """
    保存用户自定义 skill 到 ~/.mira/skills/<name>.md。

    name 只允许字母、数字、连字符和下划线，避免路径注入。
    返回保存的文件路径。
    """
    # 校验 name 格式
    if not re.match(r"^[\w\-]+$", name):
        raise ValueError(f"skill 名称 '{name}' 包含非法字符，只允许字母/数字/连字符/下划线")

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target = SKILLS_DIR / f"{name}.md"
    content = _skill_to_markdown(name, description, prompt)
    target.write_text(content, encoding="utf-8")
    return target


def delete_user_skill(name: str) -> bool:
    """
    删除用户自定义 skill。

    返回 True 表示成功删除，False 表示文件不存在（内置 skill 不可删除）。
    抛出 ValueError 如果尝试删除内置 skill。
    """
    if name in BUILTIN_SKILLS and not (SKILLS_DIR / f"{name}.md").exists():
        raise ValueError(f"'{name}' 是内置 skill，无法删除（可通过同名用户 skill 覆盖）")

    target = SKILLS_DIR / f"{name}.md"
    if not target.exists():
        return False

    target.unlink()
    return True


# ──────────────────────────────────────────────
# 简单自测（python -m ... 直接运行时）
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== 内置 skills ===")
    for s in list_skills():
        print(f"  [{s['source']}] {s['name']}: {s['description']}")

    print("\n=== 获取 'commit' skill ===")
    skill = get_skill("commit")
    if skill:
        print(f"  name: {skill['name']}")
        print(f"  description: {skill['description']}")
        print(f"  prompt 前 60 字：{skill['prompt'][:60]}...")

    print("\n=== 保存用户 skill ===")
    path = save_user_skill("hello", "打招呼", "请用中文说你好。")
    print(f"  已保存到：{path}")

    print("\n=== 列出（含用户 skill）===")
    for s in list_skills():
        print(f"  [{s['source']}] {s['name']}: {s['description']}")

    print("\n=== 删除用户 skill ===")
    ok = delete_user_skill("hello")
    print(f"  删除结果：{ok}")
