# Mira — AI 智能编程助手

支持 9 大 AI 提供商的 CLI + Web UI 智能编程助手，内置 Agentic Loop 自动调用工具完成任务。

---

## 目录

- [功能概览](#功能概览)
- [安装](#安装)
- [快速开始](#快速开始)
- [支持的 AI 提供商](#支持的-ai-提供商)
- [CLI 命令参考](#cli-命令参考)
- [工具列表](#工具列表)
- [Web UI](#web-ui)
- [自定义提供商](#自定义提供商)
- [插件与 MCP](#插件与-mcp)
- [配置参考](#配置参考)

---

## 功能概览

| 类别 | 说明 |
|------|------|
| **双模式** | CLI 交互终端 + Web UI（FastAPI + WebSocket 实时流式） |
| **Agentic Loop** | AI 自主连续调用工具直至任务完成，最多 20 步 |
| **多提供商** | 9 大 AI 提供商 + 任意 OpenAI 兼容接口 |
| **工具集** | 36 个内置工具：文件、命令、Git、搜索、任务、记忆 |
| **CLI 命令** | 26 个斜杠命令覆盖会话、模型、文件、任务、记忆等 |
| **会话持久化** | 对话自动保存，随时恢复历史会话 |
| **撤销** | `/undo` 或 `Ctrl+Z` 撤销上一轮 AI 的所有文件修改 |
| **计划模式** | `/plan` 进入只规划不执行的模式，确认后再执行 |
| **子任务** | AI 可在后台并行创建和管理子代理任务 |
| **技能/插件** | 内置技能库 + 用户自定义插件（热加载） |
| **MCP** | 通过 `~/.mira/mcp.json` 接入外部 MCP 工具服务器 |
| **项目记忆** | 自动加载 `NOTES.md` / `CLAUDE.md` / `.claude/memory/*.md` |
| **上下文管理** | Token 用量实时估算，82% 自动压缩，费用追踪 |
| **Prompt 缓存** | Anthropic 模型自动添加 cache_control，节省重复前缀费用 |
| **扩展思考** | Claude 扩展思考模式，Web UI 可折叠展示思考过程 |
| **图片输入** | 支持粘贴剪贴板图片（Ctrl+V）和拖拽上传 |

---

## 安装

**Python 版本要求**：>= 3.8

```bash
git clone <repo-url>
cd mira

# 基础安装（CLI 模式）
pip install -e .

# 完整安装（含 Web UI 依赖）
pip install -e ".[web]"
```

**核心依赖**：openai, anthropic, google-generativeai, requests, httpx, PyPDF2

**Web UI 额外依赖**：fastapi, uvicorn, websockets, aiofiles, pydantic

---

## 快速开始

### 配置 API 密钥

**方式一：环境变量**

```bash
export OPENAI_API_KEY=sk-xxxxxxxx
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
export GOOGLE_API_KEY=AIza...xxxxxxx
export DEEPSEEK_API_KEY=sk-xxxxxxxx
export ZHIPU_API_KEY=xxxxxxxx
export MOONSHOT_API_KEY=sk-xxxxxxxx
export DOUBAO_API_KEY=xxxxxxxx
export MINIMAX_API_KEY=xxxxxxxx
export LONGCAT_API_KEY=ak_xxxxxxxx
```

**方式二：首次运行引导**

```bash
mira  # 首次启动时交互式引导配置
```

**方式三：CLI 命令**

```bash
mira
/config key <provider> <api-key>
```

### 启动

```bash
# CLI 交互模式
mira

# Web UI 模式（http://127.0.0.1:8080）
mira --web

# 非交互执行单条任务
mira -p "帮我分析 main.py 的结构"
```

### 切换模型

```bash
/model                        # 列出所有可用提供商和模型
/model deepseek               # 切换到 DeepSeek 默认模型
/model anthropic claude-sonnet-4-6  # 切换到指定模型
```

---

## 支持的 AI 提供商

| 提供商 | 标识符 | 常用模型 |
|--------|--------|----------|
| OpenAI | `openai` | gpt-4o, gpt-4o-mini |
| Anthropic Claude | `anthropic` | claude-opus-4-6, claude-sonnet-4-6 |
| Google Gemini | `google` | gemini-1.5-pro, gemini-1.5-flash |
| DeepSeek | `deepseek` | deepseek-chat, deepseek-reasoner |
| 智谱 GLM | `zhipu` | glm-4-plus |
| 月之暗面 Kimi | `moonshot` | moonshot-v1-8k |
| 豆包（字节跳动）| `doubao` | doubao-pro-4k |
| MiniMax | `minimax` | abab6.5s-chat |
| LongCat | `longcat` | longcat-v1 |
| **自定义** | 任意 | 任意 OpenAI 兼容接口 |

---

## CLI 命令参考

在 CLI 中输入 `/help` 查看完整帮助，或使用 Tab 补全命令。

### 会话管理

| 命令 | 说明 |
|------|------|
| `/clear` | 清空当前对话历史 |
| `/session list` | 列出所有历史会话 |
| `/session save [名称]` | 保存当前会话 |
| `/session del <id>` | 删除指定会话 |
| `/resume [id]` | 恢复历史会话（不指定 id 则列出选择） |

### 模型与配置

| 命令 | 说明 |
|------|------|
| `/model` | 列出所有提供商和模型 |
| `/model <provider> [model]` | 切换提供商或模型 |
| `/config show` | 显示当前配置 |
| `/config set <key> <value>` | 设置配置项 |
| `/config key <provider> <key>` | 设置 API 密钥 |
| `/config provider add/list/remove` | 管理自定义提供商 |
| `/config path` | 显示配置文件路径 |

### 文件与 Git

| 命令 | 说明 |
|------|------|
| `/diff [文件]` | 显示 Git 差异 |
| `/commit` | AI 生成并执行 Git 提交 |

### 上下文与状态

| 命令 | 说明 |
|------|------|
| `/compact` | 压缩对话历史（保留摘要） |
| `/context` | 显示上下文 Token 详情 |
| `/status` | 显示当前模型、费用、会话等完整状态 |
| `/cost` | 显示本次会话累计 API 费用 |

### 撤销与导出

| 命令 | 说明 |
|------|------|
| `/undo` | 撤销上一轮 AI 的所有文件修改 |
| `/export [文件名]` | 导出对话为 Markdown 文件 |

### 记忆与项目

| 命令 | 说明 |
|------|------|
| `/init` | 在当前目录创建 NOTES.md |
| `/memory show` | 显示当前加载的项目记忆 |
| `/memory add <内容>` | 向 NOTES.md 追加记忆 |
| `/memory edit` | 打开编辑器编辑 NOTES.md |
| `/add-dir <路径>` | 添加额外工作目录（持久化） |

### 工作流

| 命令 | 说明 |
|------|------|
| `/plan [on\|off]` | 进入/退出计划模式 |
| `/todo list` | 查看任务列表 |
| `/todo add <内容>` | 添加任务 |
| `/todo done <id>` | 标记任务完成 |
| `/todo del <id>` | 删除任务 |
| `/task list` | 查看后台子任务列表 |
| `/task get <id>` | 查看子任务详情 |
| `/task output <id>` | 查看子任务输出 |
| `/task stop <id>` | 停止子任务 |

### 技能与插件

| 命令 | 说明 |
|------|------|
| `/skill list` | 列出所有技能 |
| `/skill <名称>` | 执行指定技能 |
| `/skill save <名称>` | 将当前对话保存为技能 |
| `/skill del <名称>` | 删除技能 |
| `/plugin list` | 列出已加载插件 |
| `/plugin reload` | 热重载插件 |
| `/plugin dir` | 显示插件目录路径 |

### 其他

| 命令 | 说明 |
|------|------|
| `/permissions` | 查看工具权限设置 |
| `/doctor` | 检查运行环境 |
| `/version` | 显示版本信息 |
| `/help` | 显示帮助 |
| `/exit` | 退出 |

### 多行输入

在行末加 `\` 后回车，可继续输入下一行：

```
请帮我重构以下代码，\
要求保持接口不变，\
并添加类型注解。
```

---

## 工具列表

AI 在 Agentic Loop 中可调用以下 36 个工具：

### 文件操作（12个）

| 工具 | 功能 |
|------|------|
| `FileReadTool` | 读取文件内容 |
| `FileWriteTool` | 写入/覆盖文件 |
| `FileEditTool` | 精确替换文件片段 |
| `FileAppendTool` | 追加内容到文件末尾 |
| `LSTool` | 列出目录内容 |
| `MkdirTool` | 创建目录 |
| `DeleteTool` | 删除文件或目录 |
| `MoveTool` | 移动/重命名文件 |
| `CopyTool` | 复制文件 |
| `GlobTool` | 按模式匹配文件路径 |
| `GrepTool` | 正则搜索文件内容 |
| `DiffTool` | 显示两个文件/版本的差异 |

### 命令执行（2个）

| 工具 | 功能 |
|------|------|
| `BashTool` | 执行 Bash/Shell 命令（实时流式输出） |
| `PowerShellTool` | 执行 PowerShell 命令（Windows） |

### Git 操作（7个）

| 工具 | 功能 |
|------|------|
| `GitStatusTool` | 查看 Git 工作区状态 |
| `GitDiffTool` | 查看差异 |
| `GitLogTool` | 查看提交历史 |
| `GitCommitTool` | 执行提交 |
| `GitBranchTool` | 分支管理 |
| `GitAddTool` | 暂存文件 |
| `GitPushTool` | 推送到远端 |

### 网络与搜索（2个）

| 工具 | 功能 |
|------|------|
| `WebSearchTool` | 联网搜索，DuckDuckGo 为主、Bing 为备，支持 `engine=auto/ddg/bing` |
| `WebFetchTool` | 抓取网页内容转纯文本 |

### 交互与控制（4个）

| 工具 | 功能 |
|------|------|
| `AskUserQuestionTool` | 向用户提问（暂停等待输入） |
| `SleepTool` | 等待指定时间（0.1~60s） |
| `EnterPlanModeTool` | 进入计划模式 |
| `ExitPlanModeTool` | 退出计划模式 |

### 子任务（6个）

| 工具 | 功能 |
|------|------|
| `TaskCreateTool` | 创建后台子任务 |
| `TaskListTool` | 列出子任务 |
| `TaskGetTool` | 获取子任务详情 |
| `TaskOutputTool` | 读取子任务输出 |
| `TaskUpdateTool` | 更新子任务状态 |
| `TaskStopTool` | 停止子任务 |

### 记忆与任务（2个）

| 工具 | 功能 |
|------|------|
| `NotesWriteTool` | 写入项目记忆（NOTES.md） |
| `TodoWriteTool` | 管理任务列表 |

---

## Web UI

```bash
mira --web
# 启动后访问 http://127.0.0.1:8080
```

### 界面功能

**侧边栏**
- 会话历史：查看、切换、重命名历史对话
- 文件浏览：浏览工作目录文件，点击加入上下文
- 技能库：查看和执行内置及自定义技能
- 工具列表：查看所有可用工具及其说明
- 记忆编辑器：直接编辑 NOTES.md

**输入区**
- `/` 触发斜杠命令下拉补全（Tab/方向键选择）
- `Ctrl+U` 上传图片或文件
- 拖拽文件到输入框上传
- 支持粘贴剪贴板图片（Ctrl+V）

**消息区**
- 实时流式输出
- 扩展思考块可折叠展示（Claude 模型）
- 工具执行状态卡片（显示工具名、参数、结果）
- AI 消息操作栏：复制、重试

**主题**：暗黑 / 暗灰 / 深海 / 摩卡 / 亮色（共 5 套）

**设置面板**（`Ctrl+E` 打开）
- 切换提供商和模型
- 管理自定义提供商
- 配置 MCP 外部工具
- 权限确认对话框

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 发送消息 |
| `Shift+Enter` | 换行 |
| `Ctrl+K` | 新建对话 |
| `Ctrl+U` | 上传文件/图片 |
| `Ctrl+E` | 打开设置面板 |
| `Ctrl+Z` | 快速撤销上一轮文件修改 |
| `/` + `Tab` / `↑↓` | 斜杠命令补全 |

---

## 自定义提供商

任何兼容 OpenAI API 格式的接口都可以作为自定义提供商接入。

### 通过 CLI 配置

```bash
# 添加自定义提供商
/config provider add myapi "My API" https://api.example.com/v1 sk-xxx model-v1,model-v2

# 列出所有提供商
/config provider list

# 删除提供商
/config provider remove myapi
```

### 通过 Web UI 配置

在设置面板（`Ctrl+E`）中选择「自定义提供商」，填写：
- 标识符、显示名称
- API Base URL（`https://api.example.com/v1`）
- API 密钥
- 支持的模型列表（逗号分隔）

---

## 插件与 MCP

### 用户插件

将 Python 文件放入 `~/.mira/plugins/` 目录，实现自定义工具或命令：

```bash
~/.mira/plugins/my_tool.py
```

```bash
/plugin reload   # 热重载，无需重启
/plugin list     # 查看已加载插件
/plugin dir      # 查看插件目录路径
```

### MCP 外部工具

编辑 `~/.mira/mcp.json` 配置 MCP 服务器：

```json
{
  "servers": [
    {
      "name": "my-mcp-server",
      "command": "python",
      "args": ["/path/to/mcp_server.py"]
    }
  ]
}
```

MCP 工具在 Web UI 设置面板中也可图形化配置。

---

## 配置参考

配置文件路径：`~/.mira/config.json`

```bash
/config path     # 显示配置文件路径
/config show     # 显示所有配置项
```

### 常用配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider` | 当前 AI 提供商 | `deepseek` |
| `model` | 当前模型 | 提供商默认值 |
| `max_steps` | Agentic Loop 最大步数 | `20` |
| `auto_compact_threshold` | 自动压缩上下文阈值（%） | `82` |
| `web_port` | Web UI 端口 | `8080` |
| `web_host` | Web UI 监听地址 | `127.0.0.1` |

### 目录结构

```
~/.mira/
├── config.json        # 主配置文件
├── sessions/          # 历史会话存储
├── plugins/           # 用户插件目录
├── skills/            # 自定义技能
└── mcp.json           # MCP 服务器配置
```

---

## 撤销功能

AI 修改文件后，可通过以下方式撤销上一轮的所有文件变更：

- **CLI**：输入 `/undo`
- **Web UI**：按 `Ctrl+Z`，或点击撤销按钮

撤销操作会同时从对话历史中移除对应的 AI 回复，恢复到上一轮执行前的状态。

---

## 上下文管理

Mira 实时估算 Token 使用量并在 Web UI 中以进度条显示：

- **70%**：显示警告，建议执行 `/compact` 压缩
- **82%**：自动触发对话压缩，保留摘要继续工作
- `/compact`：手动压缩，将历史对话浓缩为摘要
- `/context`：查看当前上下文各部分的 Token 占比
- `/cost`：查看本次会话累计 API 费用（含缓存命中节省量）

---

## 许可证

请参阅仓库根目录的 LICENSE 文件。
