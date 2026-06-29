# 📄 课程报告生成工具 v1.0

**Course Report Generator** — 少儿编程教师课后报告自动生成工具。

选择学生本节课的程序文件夹 + 上传运行截图，一键生成 9 项结构化报告内容，导出排版精美的 4 页 A4 PDF，批量支持最多 50 名学生。

## 快速体验

```bash
# 1. 安装依赖
pip install uv && uv sync

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
| **PDF 导出** | Jinja2 + WeasyPrint 渲染，精准 4 页 A4 排版，图文混排 |
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
| PDF 渲染 | Jinja2 + WeasyPrint |
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
