<p align="center">
  <img src="assets/logo.png" alt="Mira" height="80">
</p>

# Mira — AI 智能编程助手

> v1.1.0 · 支持 16 大 AI 提供商的 CLI + Web UI 智能编程助手，内置 Agentic Loop 自动调用工具完成任务。

---

## 目录

- [功能概览](#功能概览)
- [安装](#安装)
- [快速开始](#快速开始)
- [支持的 AI 提供商](#支持的-ai-提供商)
- [CLI 命令参考](#cli-命令参考)
- [工具列表](#工具列表)
- [权限系统](#权限系统)
- [项目记忆](#项目记忆)
- [Web UI](#web-ui)
- [自定义提供商](#自定义提供商)
- [插件与 MCP](#插件与-mcp)
- [配置参考](#配置参考)
- [打包发行](#打包发行)

---

## 功能概览

| 类别 | 说明 |
|------|------|
| **双模式** | CLI 交互终端 + Web UI（FastAPI + WebSocket 实时流式） |
| **Agentic Loop** | AI 自主连续调用工具直至任务完成 |
| **多提供商** | 16 大 AI 提供商 + 任意 OpenAI 兼容接口 |
| **工具集** | 42 个内置工具：文件、命令、Git、搜索、HTTP、压缩包、进程、哈希、Base64、时间 |
| **CLI 命令** | 26 个斜杠命令覆盖会话、模型、文件、任务、记忆等 |
| **会话持久化** | 对话自动保存，随时恢复历史会话 |
| **撤销** | `/undo` 或 `Ctrl+Z` 撤销上一轮 AI 的所有文件修改 |
| **计划模式** | `/plan` 进入只规划不执行的模式，确认后再执行 |
| **子任务** | AI 可在后台并行创建和管理子代理任务 |
| **技能/插件** | 内置技能库 + 用户自定义插件（热加载） |
| **MCP** | 通过 `~/.mira/mcp.json` 接入外部 MCP 工具服务器 |
| **分级权限** | 工具调用前按文件/目录/工具三级粒度交互确认 |
| **项目记忆** | 自动加载 `NOTES.md` / `CLAUDE.md`（兼容）/ `.mira/memory/*.md` |
| **上下文管理** | Token 用量实时估算，82% 自动压缩，费用追踪 |
| **Prompt 缓存** | Anthropic 模型自动添加 cache_control，节省重复前缀费用 |
| **扩展思考** | 扩展思考模式，Web UI 可折叠展示思考过程 |
| **图片输入** | 支持粘贴剪贴板图片（Ctrl+V）和拖拽上传 |

---

## 安装

**Python 版本要求**：>= 3.8

```bash
git clone <repo-url>
cd mira
pip install -e .
```

**依赖**：openai, anthropic, google-generativeai, httpx, fastapi, uvicorn, websockets, aiofiles, pydantic, ddgs, PyPDF2

---

## 快速开始

### 配置 API 密钥

**方式一：环境变量**

```bash
export OPENAI_API_KEY=sk-xxxxxxxx
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
export GOOGLE_API_KEY=AIza...xxxxxxx
export XAI_API_KEY=xai-xxxxxxxx
export MISTRAL_API_KEY=xxxxxxxx
export DEEPSEEK_API_KEY=sk-xxxxxxxx
export DASHSCOPE_API_KEY=sk-xxxxxxxx      # 阿里云通义千问
export ZHIPU_API_KEY=xxxxxxxx
export MOONSHOT_API_KEY=sk-xxxxxxxx
export DOUBAO_API_KEY=xxxxxxxx
export MINIMAX_API_KEY=xxxxxxxx
export LINGYI_API_KEY=xxxxxxxx            # 零一万物 Yi
export BAICHUAN_API_KEY=xxxxxxxx
export ERNIE_API_KEY=xxxxxxxx             # 百度文心
export SPARK_API_KEY=xxxxxxxx             # 科大讯飞星火
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
/model                              # 列出所有可用提供商和模型
/model deepseek                     # 切换到 DeepSeek 默认模型
/model anthropic claude-sonnet-4-6  # 切换到指定模型
```

### 退出

```bash
/exit          # 命令退出
Ctrl+C         # 连按两次（2 秒内）退出；单次仅显示提示
```

---

## 支持的 AI 提供商

| 提供商 | 标识符 | 常用模型 |
|--------|--------|----------|
| OpenAI | `openai` | gpt-5.4, gpt-4o, gpt-4o-mini |
| Anthropic Claude | `anthropic` | claude-opus-4-6, claude-sonnet-4-6 |
| Google Gemini | `google` | gemini-2.5-pro, gemini-2.5-flash |
| xAI Grok | `xai` | grok-4, grok-3, grok-3-mini |
| Mistral AI | `mistral` | mistral-large-latest, codestral-latest |
| DeepSeek | `deepseek` | deepseek-chat, deepseek-reasoner |
| 阿里云通义千问 | `qwen` | qwen-max, qwen-plus, qwen-turbo |
| 智谱 GLM | `zhipu` | glm-5, glm-5-turbo |
| 月之暗面 Kimi | `moonshot` | kimi-k2.5, moonshot-v1-128k |
| 豆包（字节跳动）| `doubao` | doubao-seed-2-0-pro-260215 |
| MiniMax | `minimax` | MiniMax-M2.7, MiniMax-M2.7-highspeed |
| 零一万物 Yi | `lingyi` | yi-large, yi-large-turbo |
| 百川智能 | `baichuan` | Baichuan4, Baichuan4-Turbo |
| 百度文心 ERNIE | `ernie` | ERNIE-4.0-Turbo-8K, ERNIE-3.5-8K |
| 科大讯飞星火 | `spark` | 4.0Ultra, generalv3.5 |
| LongCat | `longcat` | LongCat-Flash-Omni-2603, LongCat-Flash-Chat |
| **自定义** | 任意 | 任意 OpenAI 兼容接口 |

---

## CLI 命令参考

在 CLI 中输入 `/help` 查看完整帮助。

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

### 权限管理

| 命令 | 说明 |
|------|------|
| `/permissions` | 查看会话权限状态和工具列表 |
| `/permissions allow file <路径>` | 授权某个文件（本会话） |
| `/permissions allow dir <目录>` | 授权某个目录及子目录（本会话） |
| `/permissions allow tool <工具名>` | 授权某个工具（本会话） |
| `/permissions revoke file\|dir\|tool <值>` | 撤销某条权限 |
| `/permissions clear` | 清空所有会话权限 |

### 其他

| 命令 | 说明 |
|------|------|
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

AI 在 Agentic Loop 中可调用以下工具：

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

### 系统工具（7个）

| 工具 | 功能 |
|------|------|
| `HttpRequestTool` | 发送 HTTP 请求（GET/POST/PUT/DELETE 等），测试 REST API |
| `ArchiveTool` | 压缩包操作：列出内容 / 解压 / 创建 zip、tar.gz 等 |
| `EnvTool` | 读写环境变量（get / set / unset / list） |
| `ProcessTool` | 进程管理：列出进程、按端口查找、结束进程 |
| `DateTimeTool` | 获取当前日期时间，支持时区和格式化、Unix 时间戳转换 |
| `HashTool` | 计算文件或字符串的哈希摘要（MD5/SHA1/SHA256/SHA512） |
| `Base64Tool` | Base64 编码/解码（支持文件和文本，可保存二进制输出） |

---

## 权限系统

Mira 在 AI 调用会修改文件或执行命令的工具前，会弹出交互式确认菜单。

### 确认菜单

```
  ┌─ 权限请求 ──────────────────────────────────────────────────
  │ 编辑文件: src/mira/utils/memory.py
  │ --- a/memory.py
  │ +++ b/memory.py
  │ @@ -49 +49 @@
  │ -    # .claude/memory/*.md
  │ +    # .mira/memory/*.md
  └────────────────────────────────────────────────────────────

  1  允许本次
  2  允许此文件的所有操作  src/mira/utils/memory.py
  3  允许此目录的所有操作  src/mira/utils/
  4  允许 FileEditTool 的所有操作
  5  拒绝

  请选择 [1-5]，直接回车=1:
```

- **选 1**：仅允许本次调用
- **选 2**：本会话内对该文件的所有操作自动放行
- **选 3**：本会话内对该目录（含子目录）的所有操作自动放行
- **选 4**：本会话内该工具的所有调用自动放行
- **选 5**：拒绝，并打印后续授权方法

### 拒绝后的提示

```
  ✗ 已拒绝。若稍后想授权，可输入：
      /permissions allow file src/mira/utils/memory.py
      /permissions allow dir  src/mira/utils/
      /permissions allow tool FileEditTool
  或在下次提示时选择对应选项。
```

### 权限粒度

| 级别 | 命令 | 说明 |
|------|------|------|
| 文件 | `/permissions allow file <路径>` | 指定文件的所有工具操作 |
| 目录 | `/permissions allow dir <目录>` | 该目录及所有子目录 |
| 工具 | `/permissions allow tool <工具名>` | 该工具的所有参数 |

所有权限均为**会话内有效**，进程退出后自动清空。

### 需要确认的工具

| 工具 | 触发条件 |
|------|----------|
| `FileEditTool` | 所有调用，展示 diff 预览 |
| `FileWriteTool` | 所有调用（新建/覆盖） |
| `FileAppendTool` | 所有调用 |
| `DeleteTool` | 所有调用 |
| `MoveTool` | 所有调用 |
| `BashTool` / `PowerShellTool` | 仅含危险模式时（`rm -rf`、`DROP TABLE` 等） |
| `GitCommitTool` | 所有调用 |
| `GitPushTool` | 所有调用 |

### 跳过所有确认

启动时加 `--dangerously-skip-permissions` 可跳过所有确认（不推荐用于生产环境）：

```bash
mira --dangerously-skip-permissions
```

---

## 项目记忆

Mira 在每次对话开始时自动加载记忆文件注入系统提示，帮助 AI 了解项目背景和约定。

### 加载优先级（从高到低）

1. `<当前目录>/NOTES.md`
2. `<当前目录>/CLAUDE.md`（只读兼容，不写入）
3. `<当前目录>/.mira/memory/*.md`（结构化记忆目录）
4. 向上递归父目录，重复以上三步
5. `~/.mira/memory/*.md`（全局记忆）
6. `~/.mira/NOTES.md`（全局笔记）

### 记忆命令

```bash
/init                  # 在当前目录创建 NOTES.md 模板
/memory show           # 显示当前加载的所有记忆内容及来源
/memory add <内容>     # 向最优先的记忆文件追加一条笔记
/memory edit           # 用系统编辑器打开当前记忆文件
```

### 结构化记忆目录

在项目根目录创建 `.mira/memory/` 目录，可放多个 `.md` 文件分类管理：

```
<项目>/
└── .mira/
    └── memory/
        ├── conventions.md   # 代码规范
        ├── architecture.md  # 架构说明
        └── decisions.md     # 技术决策记录
```

所有文件按文件名排序后合并加载。

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
- 扩展思考块可折叠展示
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
├── memory/            # 全局记忆文件（*.md）
├── plugins/           # 用户插件目录
├── skills/            # 自定义技能
└── mcp.json           # MCP 服务器配置

<项目目录>/
├── NOTES.md           # 项目记忆（优先写入）
├── CLAUDE.md          # 兼容读取，不写入
└── .mira/
    └── memory/        # 项目结构化记忆（*.md）
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

## 打包

使用 `build_dist.py` 将 Mira 及所有 Python 依赖打包为当前平台的可执行文件，用户无需预装 Python。

### 产物

| 平台 | 可执行文件 | Web UI 启动 | 卸载 |
|------|-----------|------------|------|
| Windows | `dist/mira/mira.exe` | `启动 Web UI.vbs`（无控制台窗口） | `uninstall.bat` |
| macOS | `dist/mira/mira` | `mira-web.sh` | `uninstall.sh` |
| Linux | `dist/mira/mira` | `mira-web.sh` | `uninstall.sh` |

Web UI 启动时会自动扫描从 `8080` 开始的端口，找到第一个空闲端口后启动并打开浏览器：

```
  端口 8080 已被占用，自动切换到 8081

✦  Mira Web UI
   地址: http://127.0.0.1:8081
   按 Ctrl+C 停止
```

### 前置依赖

```bash
pip install pyinstaller>=6.0.0
```

### 构建命令

```bash
# 打包
python build_dist.py

# 清理旧产物后打包
python build_dist.py --clean
```

---

## 许可证

请参阅仓库根目录的 LICENSE 文件。
