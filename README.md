# 课程报告生成工具 (Course Report Generator)

少儿编程课程报告自动生成工具 - 为少儿编程教师设计，选择程序文件夹，AI 生成报告内容，4 页 A4 模板输出 PDF。

## 快速开始

```bash
# 安装依赖
uv sync

# 启动开发模式
uv run python main.py

# 运行测试
uv run pytest

# 运行测试 + 覆盖率
uv run pytest --cov

# 代码检查
uv run ruff check .
```

## 项目结构

```
backend/      # 后端代码（FastAPI + AI + 报告渲染）
frontend/     # 前端代码（HTML + Vue）
templates/    # 报告模板（PDF/Word 通用）
data/         # 本地数据（SQLite + 文件）
config/       # 配置文件（LLM、应用设置）
tests/        # 测试（单元 + 集成）
logs/         # 日志输出
```

## 版本路线

| 版本 | 阶段 | 内容 |
|------|------|------|
| v0.1.0 | P0 准备 | 项目脚手架、日志、测试 |
| v0.2.0 | P1 学生/班级管理 | 增删改查、批量导入 |
| v0.3.0 | P2 代码分析 | AST 解析、注释提取 |
| v0.4.0 | P3 AI 集成 | LangChain、多家 LLM |
| v0.5.0 | P4 报告编辑 + 草稿 | 9 项内容可编辑、自动保存 |
| v0.6.0 | P5 模板 + PDF | 3 套模板、A4 输出 |
| v0.7.0 | P6 Word 导入导出 | python-docx、AI 辅助识别 |
| v0.8.0 | P7 批量 + 历史 | 多学生差异化、报告中心 |
| v1.0.0 | P8 发布 | 测试、打包、安装包 |

详见 [项目策划书.md](项目策划书.md)。

## 技术栈

- **后端**: Python 3.11 + FastAPI
- **AI**: LangChain (组件 + 自定义编排) + 5 家 LLM 适配
- **模板**: Jinja2 + WeasyPrint（PDF）+ python-docx（Word）
- **存储**: SQLite + 文件系统
- **前端**: HTML + Vue 3（计划）
- **打包**: pywebview + PyInstaller

## 配置

LLM 配置：`config/llm.yaml`（首次启动自动生成模板）

```yaml
provider: deepseek
api_key: <your-key>
default_model: deepseek-chat
```

## 测试

```bash
# 单元测试
uv run pytest tests/unit -v

# 集成测试
uv run pytest tests/integration -v

# 查看覆盖率
uv run pytest --cov --cov-report=html
# 打开 htmlcov/index.html
```
