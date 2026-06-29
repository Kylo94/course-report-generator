# 📄 课程报告生成工具 v1.0

**Course Report Generator** — 少儿编程教师课后报告自动生成工具。

选择学生本节课的程序文件夹 + 上传运行截图，一键生成 9 项结构化报告内容，导出排版精美的 4 页 A4 PDF，批量支持最多 50 名学生。

## 快速体验

### 安装 uv（包管理器）

```bash
# macOS（Homebrew）
brew install uv

# macOS / Linux（官方脚本）
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows（PowerShell）
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或用 pip 安装
pip install uv
```

### 安装 & 启动

```bash
# 1. 安装项目依赖
uv sync

# 2. 配置 LLM（编辑 config/llm.yaml，填入 API Key）
#    支持 DeepSeek / 通义千问 / 智谱 GLM / OpenAI / Claude

# 3. 启动（开发模式）
uv run python main.py

# 4. 浏览器打开 http://localhost:8765
```

首次启动自动创建 SQLite 数据库，无需额外配置。

## 功能一览

| 模块 | 功能 |
|------|------|
| **AI 生成** | 基于程序代码 + 注释，一键生成知识点、内容概述、能力提升、课后作业、学生评价等 9 项内容。支持单字段重试和批量差异化评价 |
| **学生管理** | 学生/班级 CRUD、Excel/CSV 批量导入导出、搜索、批量删除 |
| **报告编辑** | 富文本编辑器，9 项内容均可手动修改；截图上传（支持 JPG/PNG/WebP） |
| **草稿系统** | 自动保存（30s 间隔）+ 手动保存，关闭可续编。状态机：草稿 → 已导出 → 已归档 |
| **模板系统** | 3 套内置 A4 模板（经典简约/少儿卡通/学术风），支持自定义排版 JSON 配置、Logo 上传（6 位置 × 3 尺寸） |
| **PDF 导出** | Playwright（Chromium 内核）渲染，精准 4 页 A4 排版，图文混排 |
| **Word 导出/导入** | python-docx 原生生成，结构清晰可编辑；修改后的 docx 可导回工具重新识别（AI 辅助字段匹配） |
| **批量生成** | 单次 ≤ 50 名学生，共用知识点+差异化评价与作业难度 |
| **报告中心** | 按学生/班级/日期检索历史报告，可二次编辑、重新导出 |
| **班级排序** | 支持手动调整班级显示顺序，影响全部下拉选择 |

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | HTML + Vue 3 (CDN) + Element Plus |
| 后端 | **Python 3.11+** + **FastAPI** |
| AI 编排 | LangChain 组件 + 自定义业务编排（多步链式生成 + 单步重试） |
| LLM 适配 | 自定义 `LLMProvider` 抽象层，支持 **DeepSeek / 通义千问 / 智谱 GLM / OpenAI / Claude** |
| 代码解析 | Python `ast` 模块 + 正则注释提取 |
| PDF 渲染 | Playwright（Chromium 内核，零系统依赖） |
| Word 处理 | python-docx 原生生成（非 PDF 转 Word） |
| 存储 | SQLite (aiosqlite) + 文件系统 |
| 打包 | PyInstaller（目标：单文件夹发布） |

## 项目结构

```
├── main.py                 # 应用入口（uvicorn 启动）
├── backend/
│   ├── app.py              # FastAPI 应用工厂
│   ├── config.py           # 配置加载（app.yaml + llm.yaml）
│   ├── db.py               # SQLAlchemy 异步引擎 + 迁移
│   ├── api/                # RESTful 路由（students/classes/reports/projects/…）
│   ├── services/           # 业务逻辑层（AI 编排、PDF/Word 生成、代码分析…）
│   ├── schemas/            # Pydantic 请求/响应模型
│   ├── models/             # SQLAlchemy ORM 模型
│   ├── llm/                # AI 适配（providers/ + prompts/）
│   └── utils/              # 日志等工具
├── frontend/
│   ├── index.html          # 单页应用入口
│   └── src/                # Vue 3 组件（7 个视图：Dashboard/Classes/Students/…）
├── templates/              # 报告模板（classic / cartoon / academic / python）
├── config/                 # 配置文件（app.yaml / llm.yaml）
├── data/                   # 运行期数据（SQLite + 报告输出 + 截图 + Logo）
└── tests/                  # 单元测试 + 集成测试
```

## 配置

### 项目文件夹要求

工具通过分析项目文件夹中的代码或文本来生成报告内容。不同课程类型需准备不同的文件。

#### Python 编程课

将学生本节课编写的 `.py` 文件放入一个文件夹。推荐在启动文件顶部用注释标注课程主题：

```python
# Course: 飞翔的小鸟第一课
# 1. 模拟重力效果
# 2. 实现管道移动效果

import pygame
# ...
```

支持任意 Python 项目类型：pygame、turtle、算法、小游戏、工具类等。

工具会自动分析：
- AST 语法树 → 函数定义、类结构、import 依赖
- 顶部注释 → 课程主题（`# Course: <主题>`）
- 项目类型 → 判断是 pygame / turtle / 算法 / 通用

#### 非 Python 课程（Scratch、机器人、硬件编程等）

在项目文件夹中创建一个 `course.py` 文件，把本节课的教学内容以注释形式写在里面。工具会读取注释并传递给 AI 生成报告。

**示例：Scratch 课程**

```python
# Course: 小猫过马路第一课
# 项目类型: scratch
#
# 本节课教学内容：
# 1. 认识 Scratch 界面（舞台、角色区、积木区）
# 2. 使用"移动10步"积木让角色前进
# 3. 使用"当绿旗被点击"事件积木启动程序
# 4. 使用"碰到边缘就反弹"控制角色边界
# 5. 添加背景和第二个角色
#
# 学生完成内容：
# - 让小猫从舞台左侧走到右侧
# - 碰到边缘后自动折返
# - 添加了一个小狗角色跟着移动
#
# 本节课重点：
# - 事件驱动编程概念（点击绿旗→执行）
# - 坐标与方向的基本理解
# - 顺序执行的概念
```

**示例：机器人 / 硬件课程**

```python
# Course: LED 交通灯第二课
# 项目类型: hardware
#
# 本节课教学内容：
# 1. 回顾 Arduino 数字引脚（D3/D4/D5）
# 2. 连接红黄绿三个 LED 到面包板
# 3. 编写循环程序实现交通灯时序
# 4. 红灯 5 秒 → 黄灯 2 秒 → 绿灯 5 秒
# 5. 串联电阻的计算方法
#
# 学生完成内容：
# - 正确连接了 3 个 LED 电路
# - 编写了时序循环程序
# - 万用表测量了电流值
```

**文件命名规则：**

工具会自动识别以下文件的注释作为课程内容：

| 文件名 | 说明 |
|--------|------|
| `course.py` | 纯课程描述（推荐非 Python 课程使用） |
| `main.py` | 识别为启动文件，优先读取 |
| 其他 `.py` 文件 | 按字母序读取，文件内注释都会被传给 AI |

**注意事项：**
- 文件中至少要有 `# Course: <主题>` 一行，工具才能识别课程名称
- 注释内容越详细，AI 生成的报告质量越高
- 支持 Emoji 和中文标点

### LLM 配置 (`config/llm.yaml`)

```yaml
provider: deepseek              # 当前激活的供应商
api_key: sk-xxxxx               # API Key
default_model: deepseek-chat    # 默认模型
timeout: 60                     # 请求超时（秒）
max_retries: 2                  # 失败重试次数
```

支持供应商及推荐模型：

| 供应商 | 推荐模型 | 特点 |
|--------|---------|------|
| DeepSeek | `deepseek-chat` | 性价比首选，中文效果好 |
| 通义千问 | `qwen-plus` | 阿里云稳定接入 |
| 智谱 GLM | `glm-4` | 教育领域优化 |
| OpenAI | `gpt-4o-mini` | 兜底方案，质量稳定 |
| Claude | `claude-sonnet-4-6` | 高质量长文本 |

### 应用配置 (`config/app.yaml`)

可自定义：服务器端口、报告输出目录、截图保存目录、Logo 设置、草稿自动保存间隔等。

## 开发

```bash
# 安装依赖
uv sync

# 开发模式启动（后端端口 8765，自动重载）
uv run python main.py

# 运行测试
uv run pytest -v

# 测试 + 覆盖率
uv run pytest --cov --cov-report=html

# 代码检查
uv run ruff check .
```

## 打包 & 分发

本工具支持通过 PyInstaller 打包为独立可执行程序，无需用户安装 Python 环境。

### 前置条件

```bash
# 1. 安装 PyInstaller
uv add pyinstaller --dev

# 2. 安装 Playwright + Chromium
uv run python -m playwright install chromium
```

### 构建

```bash
# 标准构建（含 Chromium，约 400MB）
uv run python build.py

# 不含 Chromium 的轻量构建（约 60MB，需接收方自行安装 Chromium）
uv run python build.py --no-chrome

# 清理旧构建后重新打包
uv run python build.py --clean
```

构建产物在 `dist/课程报告生成工具/` 目录下。

### 分发给其他人

#### 含浏览器版本（推荐）

`build.py` 会自动把 Playwright 的 Chromium 打包进去，接收方只需：

1. 将 `dist/课程报告生成工具/` 整个目录拷贝到目标机器
2. 双击 `课程报告生成工具.exe`（Windows）或运行 `课程报告生成工具`（macOS/Linux）
3. 浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)

#### 不含浏览器版本

接收方需先安装 Playwright Chromium：

```bash
uv run python -m playwright install chromium
```

### 跨平台打包

在对应的平台上分别执行 `uv run python build.py`：

| 平台 | 构建命令 | 产物 |
|------|---------|------|
| Windows | `uv run python build.py` | `dist/课程报告生成工具/课程报告生成工具.exe` |
| macOS | `uv run python build.py` | `dist/课程报告生成工具.app` |
| Linux | `uv run python build.py` | `dist/课程报告生成工具/课程报告生成工具` |

> **注意：** PyInstaller 不支持交叉编译。Windows 包必须在 Windows 上构建，macOS 包同理。

### 首次运行

启动后自动在 exe 同级创建：

```
config/
├── app.yaml            # 应用配置（可编辑）
└── llm.yaml            # AI 配置（填入 API Key）
data/
├── app.db              # SQLite 数据库
├── reports/            # 导出 PDF
├── screenshots/        # 上传截图
└── assets/             # Logo 等资产
```

### AI 配置

打包后的程序首次启动时，会自动在 exe 同级目录生成 `config/llm.yaml`。**使用前需编辑此文件**填入 API Key，然后重启应用：

```yaml
# config/llm.yaml（用记事本/VSCode 打开编辑）
provider: deepseek
api_key: sk-你的API密钥       # ← 填在这里
default_model: deepseek-chat
timeout: 60
max_retries: 2
```

支持的供应商：

| 供应商 | `provider` 值 | 推荐 `default_model` |
|--------|--------------|-------------------|
| DeepSeek | `deepseek` | `deepseek-chat` |
| 通义千问 | `qwen` | `qwen-plus` |
| 智谱 GLM | `glm` | `glm-4` |
| OpenAI | `openai` | `gpt-4o-mini` |
| Claude | `claude` | `claude-sonnet-4-6` |

> 编辑后**必须重启应用**才能使新配置生效。也可以在运行中修改后通过前端「设置」页面重载。

### 打包文件结构

```
dist/课程报告生成工具/
├── 课程报告生成工具.exe    # 主程序（Windows）— 直接双击运行
├── _internal/              # Python 运行时 + 依赖库（不要动里面的文件）
├── browser/               # [可选] Chromium 浏览器引擎（~200MB）
└── 首次启动后自动创建:
    ├── config/            # 用户配置文件目录
    │   ├── app.yaml       # 应用设置
    │   └── llm.yaml       # AI API Key（首次使用必填）
    └── data/              # 运行数据
        ├── app.db         # 数据库
        ├── reports/       # 导出 PDF
        ├── screenshots/   # 截图
        └── assets/        # Logo
```

## 版本历史

```
v1.0.0 — 正式版。完整功能闭环比对、文档完善、打包准备
v0.8.0 — 批量生成 + 报告中心 + AI 对话记忆
v0.7.0 — Word 导入导出（python-docx + AI 辅助识别）
v0.6.0 — 模板系统 + PDF 导出（3 套内置模板 + Logo 配置）
v0.5.0 — 报告编辑 + 草稿系统（自动保存 30s / 手动保存 / 续编）
v0.4.0 — AI 集成（LangChain + 多供应商 + 链式生成）
v0.3.0 — 代码分析（AST 解析 + 注释提取）
v0.2.0 — 学生/班级管理（CRUD + CSV 批量导入导出）
v0.1.0 — 项目脚手架（FastAPI + SQLAlchemy + 配置 + 日志）
```

## 许可

本项目为个人开发者工具，仅供授权用户使用。
