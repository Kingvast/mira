# Mira 架构设计文档

> v1.1.0

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Mira v1.1.0                          │
│                AI 智能编程助手架构设计                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐
│    CLI 模式     │    │   Web UI 模式   │
│  (main.py)      │    │ (web/server.py) │
└────────┬────────┘    └────────┬────────┘
         └───────────┬──────────┘
                     ▼
        ┌────────────────────────┐
        │      QueryEngine       │
        │     (query.py)         │
        └────────────────────────┘
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
  ┌─────────┐  ┌──────────┐  ┌──────────┐
  │ 工具系统 │  │  状态管理 │  │ 实用工具  │
  │ tools/  │  │  state/  │  │  utils/  │
  └─────────┘  └──────────┘  └──────────┘
       │                           │
  ┌────▼────┐                 ┌────▼────┐
  │ 服务层  │                 │ 配置系统 │
  │services/│                 │~/.mira/ │
  └─────────┘                 └─────────┘
```

---

## 核心组件详解

### 1. 查询引擎（QueryEngine）

**文件**: `src/mira/query.py`

```
QueryEngine
├── Agentic Loop 控制器
│   ├── 智能工具调用决策
│   ├── 可配置最大步数（默认无限制）
│   └── 错误恢复机制
├── 多模态处理器
│   ├── 文本消息处理
│   ├── 图片输入（Base64）
│   └── 工具结果处理
├── 流式响应管理器
│   ├── 实时 token 推送
│   ├── CLI Spinner 指示器
│   └── ANSI 彩色格式化
├── 会话管理
│   ├── 自动保存（含 AI 生成标题）
│   ├── Undo 栈（最近 20 轮）
│   └── 消息历史压缩
└── 交互控制
    ├── /exit → SystemExit(0) 干净退出
    ├── Ctrl+C 单次：提示；双击（2s 内）：退出
    └── 多行输入（行末 \ 续行）
```

**Agentic Loop 流程**:
```
用户输入
    ↓
构建系统提示（含记忆文件）
    ↓
检查上下文用量（>82% 自动压缩）
    ↓
┌── Agentic Loop ──────────────────────┐
│  1. 流式调用 AI API                  │
│  2. 解析工具调用                     │
│  3. 权限检查（分级确认菜单）         │
│  4. 执行工具（async/stream/sync）    │
│  5. 保存结果，继续循环               │
│  6. 无工具调用时退出循环             │
└──────────────────────────────────────┘
    ↓
推入 Undo 栈 / 自动保存会话
```

---

### 2. 工具系统（Tools）

**目录**: `src/mira/tools/`（42 个工具）

```
工具基类 (base.py)
└── Tool
    ├── name / description / parameters
    ├── execute(args) → str          # 同步执行
    ├── execute_async(args, cb, engine)  # 异步执行
    └── execute_stream(args, cb)     # 流式执行

文件操作 (file_tools.py)
├── FileReadTool      读取文件内容
├── FileWriteTool     新建/覆盖文件           ← 需权限确认
├── FileEditTool      精确字符串替换（含 diff 预览）← 需权限确认
├── FileAppendTool    追加内容                ← 需权限确认
├── LSTool            列出目录
├── MkdirTool         创建目录
├── DeleteTool        删除文件/目录           ← 需权限确认
├── MoveTool          移动/重命名             ← 需权限确认
├── CopyTool          复制文件
├── GlobTool          glob 模式匹配
├── GrepTool          正则内容搜索
└── DiffTool          文件差异对比

命令执行 (command_tools.py)
├── BashTool          执行 Shell（危险命令需确认）
└── PowerShellTool    执行 PowerShell（Windows）

Git 操作 (git_tools.py)
├── GitStatusTool     工作区状态
├── GitDiffTool       查看差异
├── GitLogTool        提交历史
├── GitAddTool        暂存文件
├── GitCommitTool     提交                    ← 需权限确认
├── GitPushTool       推送到远端              ← 需权限确认
└── GitBranchTool     分支管理

网络与搜索 (ai_tools.py)
├── WebSearchTool     DuckDuckGo / Bing 搜索
└── WebFetchTool      抓取网页转纯文本

交互工具 (interactive_tools.py)
├── AskUserQuestionTool  向用户提问
├── SleepTool            主动等待
├── EnterPlanModeTool    进入计划模式
└── ExitPlanModeTool     退出计划模式

子任务 (task_tools.py)
├── TaskCreateTool    创建后台子任务
├── TaskListTool      列出任务
├── TaskGetTool       获取详情
├── TaskOutputTool    读取输出
├── TaskUpdateTool    更新状态
└── TaskStopTool      停止任务

记忆与任务 (todo_tools.py / memory)
├── NotesWriteTool    写入 NOTES.md
└── TodoWriteTool     管理 Todo 列表

系统工具 (system_tools.py)
├── HttpRequestTool   HTTP 请求（GET/POST/PUT/DELETE 等）
├── ArchiveTool       压缩包列出 / 解压 / 创建
├── EnvTool           环境变量读写
├── ProcessTool       进程列表 / 端口查找 / 结束进程  ← kill 需权限确认
├── DateTimeTool      当前时间 / 时区 / Unix 时间戳 / 格式化
├── HashTool          文件或字符串哈希（MD5/SHA1/SHA256/SHA512）
└── Base64Tool        Base64 编码 / 解码
```

---

### 3. 权限系统（Permissions）

**文件**: `src/mira/utils/permissions.py`

#### 三级会话权限

```
权限粒度（细 → 粗）
├── 文件级  _allowed_files: Set[str]   绝对路径精确匹配
├── 目录级  _allowed_dirs:  Set[str]   绝对路径前缀匹配（含子目录）
└── 工具级  _allowed_tools: Set[str]   工具名匹配

命中任意一级 → 直接放行，不弹出确认菜单
所有权限仅会话内有效，进程退出后清空
```

#### 确认菜单流程

```
工具调用
    ↓
needs_confirm(tool, args) → (True, prompt_text)?
    ↓ 否
直接执行
    ↓ 是
_is_permitted_by_session(tool_name, args)?
    ↓ 命中
直接执行
    ↓ 未命中
弹出编号菜单
  1  允许本次
  2  允许此文件 (本会话)
  3  允许此目录 (本会话)
  4  允许此工具 (本会话)
  5  拒绝 → 打印授权提示

选择 2/3/4 → 写入对应 Set → 本次及后续同范围调用直接放行
```

#### 公开 API

```python
allow_tool(name)        # 工具级授权
allow_file(path)        # 文件级授权（绝对路径）
allow_dir(path)         # 目录级授权（含子目录）
revoke_tool/file/dir()  # 撤销单条权限
clear_all()             # 清空所有会话权限
get_status() → dict     # 返回当前权限快照
check_permission_sync(tool, args) → bool  # CLI 交互确认入口
```

---

### 4. 记忆系统（Memory）

**文件**: `src/mira/utils/memory.py`

#### 加载优先级（从高到低）

```
level 0    <cwd>/NOTES.md           项目记忆（优先写入目标）
           <cwd>/CLAUDE.md          兼容读取，不写入
level 0.5  <cwd>/.mira/memory/*.md  项目结构化记忆目录
level 1    <parent>/NOTES.md        父目录递归（重复上述两步）
           <parent>/.mira/memory/*.md
...
level N    （直到文件系统根）
level 100  ~/.mira/memory/*.md      全局记忆目录
level 101  ~/.mira/NOTES.md         全局笔记（可通过 notes_path 配置）
```

所有来源合并后注入系统提示（多来源时以 `<!-- 路径 -->` 分隔）。

#### 关键函数

```python
load_memory_sources() → List[{path, content, level}]
load_memory()         → str          # 合并为系统提示字符串
save_memory(content)                 # 写入最优先的 NOTES.md
append_note(entry)                   # 追加时间戳条目
init_notes(project_name)             # 在 cwd 创建 NOTES.md 模板
get_memory_path()     → Path         # 当前最优先记忆文件路径
```

---

### 5. 服务层（Services）

**目录**: `src/mira/services/`

```
API 客户端 (api/)
├── base.py              基础客户端接口
├── anthropic_client.py  Claude API（扩展思考、Prompt Cache、SSE 流式）
├── google_client.py     Gemini API
└── openai_compatible.py OpenAI 兼容接口（OpenAI / xAI / Mistral / DeepSeek /
                         通义千问 / 智谱 / Kimi / 豆包 / MiniMax / Yi /
                         百川 / 文心 / 星火 / LongCat 等）

技能服务 (skills.py)
├── 内置技能注册与执行
├── 自定义技能（存储于 ~/.mira/skills/）
└── 技能参数解析

插件服务 (plugins.py)
├── 热加载 ~/.mira/plugins/*.py
├── 注册自定义工具和命令
└── 生命周期管理

MCP 客户端 (mcp_client.py)
├── 读取 ~/.mira/mcp.json 连接外部服务器
├── 工具发现与代理
└── 消息路由
```

---

### 6. Web UI 层

**文件**: `src/mira/web/server.py`

```
FastAPI 应用
├── WebSocket 管理器        实时流式推送（文本/工具/思考块）
├── REST API 端点
│   ├── /api/sessions       会话 CRUD
│   ├── /api/config         配置读写
│   ├── /api/memory         记忆读写
│   ├── /api/files          文件浏览
│   └── /api/mcp            MCP 服务器管理
├── 权限确认 WebSocket      异步等待用户点击确认/拒绝
└── 静态文件服务            HTML / CSS / JS（5 套主题）

端口管理
├── find_free_port(start, end)  扫描空闲 TCP 端口
└── start_server(host, port)    被占用时自动向后查找
```

---

## 数据流

### 工具执行流

```
AI 生成工具调用
    ↓
_execute_tool(tc, callback)
    ↓
快照文件内容（供 /undo 使用）
    ↓
check_permission_sync(tool, args)  ← 三级权限缓存检查 → 弹出菜单
    ↓ 允许
plan_mode? → 返回描述，不执行
    ↓ 否
execute_async / execute_stream / execute（线程）
    ↓
callback(tool_result / tool_error)
    ↓
追加到消息历史，继续 Agentic Loop
```

### 记忆注入流

```
每次 process_message() 调用
    ↓
_build_system_prompt()
    ↓
load_memory()                       ← 扫描 cwd → 父目录 → 全局
    ↓
合并为系统提示前缀
    ↓
随 API 请求发送（Anthropic 启用 cache_control）
```

---

## 扩展点

### 插件接口

```python
# ~/.mira/plugins/my_plugin.py

def register_tools(registry):
    registry.add(MyCustomTool())

def register_commands(registry):
    registry.add(MyCustomCommand())
```

### MCP 配置（`~/.mira/mcp.json`）

```json
{
  "servers": [
    {
      "name": "my-server",
      "command": "python",
      "args": ["/path/to/server.py"]
    }
  ]
}
```

---

## 安全设计

### 权限控制

| 场景 | 机制 |
|------|------|
| 文件写入/删除 | 每次弹出分级确认菜单 |
| Shell 危险命令 | 关键字模式匹配 + 确认 |
| Git push/commit | 强制确认 |
| 已授权范围 | 会话缓存，自动放行 |
| 完全跳过 | `--dangerously-skip-permissions` |

### 数据安全

- API Key 存于 `~/.mira/config.json`，展示时脱敏（`sk-***...xxx`）
- 用户配置与项目配置隔离
- 命令执行结果不持久化到日志

---

## 性能优化

| 策略 | 实现 |
|------|------|
| 异步 I/O | asyncio + httpx |
| 流式响应 | 逐 token 实时推送，首字延迟低 |
| Prompt Cache | Anthropic cache_control，重复前缀节省费用 |
| 上下文压缩 | 超 82% 自动摘要，保留最近 N 条 |
| 连接复用 | httpx 连接池 |

---

## 部署架构

### 本机安装（推荐）

```
python build_dist.py
    ↓ PyInstaller 打包所有依赖
    ↓
Windows : dist/mira/mira.exe
macOS   : dist/mira/mira
Linux   : dist/mira/mira
```

### 开发环境

```
pip install -e ".[web]"
mira --web          # CLI 启动 Web UI
mira                # CLI 交互模式
```

### 用户数据目录

```
~/.mira/
├── config.json      API 密钥、默认提供商等配置
├── sessions/        会话历史（JSON）
├── memory/          全局记忆（*.md）
├── plugins/         用户插件（*.py）
├── skills/          自定义技能（*.json）
└── mcp.json         MCP 服务器配置
```

---

## 版本历史

### v1.1.0（当前）

- 权限系统重构：三级粒度（文件/目录/工具）+ 编号菜单 + 拒绝后授权提示
- `/permissions allow/revoke/clear` 命令
- 记忆目录：`.claude/memory/` → `.mira/memory/`
- CLAUDE.md 保留只读兼容
- `/exit` 修复（`SystemExit(0)` 替代 `KeyboardInterrupt`）
- Ctrl+C 双击退出
- Web UI 空闲端口自动检测（`find_free_port`）
- 安装包构建：Windows Inno Setup / macOS DMG / Linux tar.gz+install.sh

### v1.0.1

- 初始发布
- Agentic Loop、16 大 AI 提供商、36 个工具、Web UI
