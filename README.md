# 📄 课程报告生成工具 v1.3.0

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

# 2. 启动（开发模式）
uv run python main.py

# 3. 浏览器打开 http://localhost:8765，在「设置」页面填写 AI 配置
```

首次启动自动创建 SQLite 数据库，无需额外配置。AI 供应商、API Key、模型、默认模板都在「设置」页面维护，保存后即时生效。

### C/C++ 工程

除 Python 外，也支持 C / C++ 工程。把项目文件夹填入“项目文件夹”即可，例如：

```text
/Users/kylo/Documents/Workspace/WaliCode/CPlus/01 基本语法
```

系统会自动识别：

- 入口文件：`main.cpp` / `main.c` / 包含 `main()` 的文件
- 函数、类 / 结构体、`#include`
- 文件顶部的 `/* 课程 ... 作业 ... */` 或 `// 课程 ...` 注释

之后与 Python 工程一样，走同一套 AI 生成、模板预览、PDF / Word 导出流程。

---

## Docker 部署

### 前置条件

- 安装 [Docker](https://docs.docker.com/engine/install/) 和 [Docker Compose](https://docs.docker.com/compose/install/)（Compose 插件一般随 Docker Desktop 自带）
- 一个 AI 供应商的 API Key（DeepSeek / 通义千问 / OpenAI / Claude 等）

### 方式一：docker compose（推荐）

非敏感的应用配置在 **`config/app.yaml`**；AI 配置与默认模板在应用「设置」页面维护，保存到挂载的 `./data/user_settings.json`，API Key 加密保存在系统钥匙串或 `data/.llm_secret.*`。

```bash
# 1. 构建并启动（之后改代码也用这条）
docker compose up -d --build

# 2. 打开浏览器，进入「设置」页面填写 AI 配置
open http://localhost:8765

# 3. 查看日志
docker compose logs -f

# 4. 停止服务
docker compose down
```

`docker-compose.yml` 只挂载 `./data` 用于持久化用户设置与加密密钥；宿主机只发布 **8765** 一个入口。设置页面保存后即时生效，无需重启容器。

### 方式二：纯 docker

```bash
# 构建镜像
docker build -t course-report-generator .

# 运行容器
docker run -d \
  --name course-report \
  -p 8765:8765 \
  -v "$PWD/data:/app/data" \
  course-report-generator
```

> 注意：`./data` 必须挂载，否则用户设置、加密密钥和报告不会持久化。也可以在运行时用 `-e CRG_LLM__API_KEY=...` 环境变量覆盖页面配置（最高优先级）。

### 配置文件说明

| 文件 | 用途 | 是否入 git |
|---|---|---|
| `config/app.yaml` | 应用配置：服务器端口、数据库、报告目录、Logo 等 | 是 |
| `data/user_settings.json` | 用户设置：AI 配置（不含明文 Key）、默认模板、路径等 | 否 |
| `data/.llm_secret.key` / `.llm_secret.enc` | API Key 加密密钥与密文 | 否（已忽略） |
| `config/llm.yaml.example` | 旧版配置格式参考（已废弃） | 是 |

### 环境变量参考

所有配置都可以用 `CRG_` 前缀的环境变量覆盖，优先级高于「设置」页面和 `config/*.yaml`。完整字段对应关系见 [backend/config.py](backend/config.py)。

| 环境变量 | 对应配置 | 说明 | 默认值 |
|---|---|---|---|
| `CRG_LLM__API_KEY` | `llm.api_key` | **AI API Key（必填）** | — |
| `CRG_LLM__PROVIDER` | `llm.provider` | AI 供应商 | `deepseek` |
| `CRG_LLM__DEFAULT_MODEL` | `llm.default_model` | 默认模型 | `deepseek-chat` |
| `CRG_LLM__BASE_URL` | `llm.base_url` | 自定义 API 地址 | （自动） |
| `CRG_LLM__TIMEOUT` | `llm.timeout` | 请求超时（秒） | `60` |
| `CRG_LLM__MAX_RETRIES` | `llm.max_retries` | 失败重试次数 | `2` |
| `CRG_SERVER__HOST` | `server.host` | 监听地址 | `0.0.0.0` |
| `CRG_SERVER__PORT` | `server.port` | 监听端口 | `8765` |
| `CRG_APP__DEBUG` | `app.debug` | 调试模式 | `false` |
| `CRG_APP__LOG_LEVEL` | `app.log_level` | 日志级别 | `INFO` |
| `CRG_DATABASE__URL` | `database.url` | 数据库连接 | `sqlite+aiosqlite:///./data/app.db` |
| `CRG_REPORT__OUTPUT_DIR` | `report.output_dir` | PDF 输出目录 | `./data/reports` |
| `CRG_REPORT__SCREENSHOT_DIR` | `report.screenshot_dir` | 截图目录 | `./data/screenshots` |
| `CRG_REPORT__ASSET_DIR` | `report.asset_dir` | 资产目录 | `./data/assets` |
| `CRG_LOGO__ENABLED` | `logo.enabled` | 启用 Logo | `false` |

> **嵌套字段语法**：双下划线 `__` 表示嵌套层级。例如 `CRG_LLM__API_KEY` 对应配置文件中的 `llm.api_key`。

> **关于 `.env`**：Docker Compose 只会用 `.env` 做 compose 文件里的变量替换，**不会自动把 `.env` 中的变量注入容器**。如果确实想用环境变量覆盖配置，请在 `docker-compose.yml` 的 `environment:` 段显式声明，例如：

```yaml
services:
  course-report-generator:
    environment:
      - CRG_APP__DEBUG=false
      - CRG_LLM__TIMEOUT=120
```

### 持久化数据

容器内部的数据存储在 `/app/data` 目录，默认通过 `./data` bind mount 持久化（也保留 `crg_data` 命名卷写法），包含：

- SQLite 数据库（`app.db`）
- 导出的 PDF 报告
- 上传的截图
- Logo 资产
- 自定义模板

如需将数据存储到宿主机特定目录，修改 `docker-compose.yml` 中的卷映射：

```yaml
volumes:
  - ./data:/app/data     # 挂载宿主机 ./data 目录
```

---

## 功能一览

| 模块 | 功能 |
|------|------|
| **AI 生成** | 基于程序代码 + 注释，一键生成知识点、内容概述、能力提升、课后作业、学生评价等 9 项内容。支持单字段重试和批量差异化评价 |
| **项目分析** | 支持 Python / C / C++ 工程；自动识别 main.py / main.cpp / main.c、函数、类、#include，解析文件顶部课程与作业注释 |
| **学生管理** | 学生/班级 CRUD、Excel/CSV 批量导入导出、搜索、批量删除 |
| **报告编辑** | 富文本编辑器，9 项内容均可手动修改；截图上传（支持 JPG/PNG/WebP） |
| **草稿系统** | 自动保存（30s 间隔）+ 手动保存，关闭可续编。状态机：草稿 → 已导出 → 已归档 |
| **模板系统** | 5 套内置 A4 模板（经典简约/少儿卡通/学术风/科技前沿/素白极简），支持自定义排版 JSON 配置、Logo 上传（6 位置 × 3 尺寸） |
| **PDF 导出** | Playwright（Chromium 内核）渲染，精准 4 页 A4 排版，图文混排；与 Word 一起通过「导出报告」一键导出 |
| **Word 导出/导入** | python-docx 原生生成 A4 打印版。Classic / 素白极简采用 PDF 风格卡片版式（Classic 整页背景，素白极简纯白细边框），全部文字可编辑、图片为内嵌型可右键替换；其他模板沿用简洁原生版式。修改后的 docx 可导回工具重新识别 |
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
| 代码解析 | Python `ast` 模块 + C/C++ 轻量正则解析 |
| PDF 渲染 | Playwright（Chromium 内核，零系统依赖） |
| Word 处理 | python-docx 原生生成（非 PDF 转 Word） |
| 存储 | SQLite (aiosqlite) + 文件系统 |
| 打包 | PyInstaller（目标：单文件夹发布） |

## 项目结构

```
├── main.py                 # 应用入口（uvicorn 启动）
├── backend/
│   ├── app.py              # FastAPI 应用工厂
│   ├── config.py           # 配置加载（app.yaml + data/user_settings.json）
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
├── templates/              # 报告模板（classic / cartoon / academic / 科技前沿 / minimal）
├── config/                 # 配置文件（app.yaml；llm.yaml.example 仅作迁移参考）
├── data/                   # 运行期数据（SQLite + 报告输出 + 截图 + Logo）
└── tests/                  # 单元测试 + 集成测试
```

## 配置

### 如何编写项目代码以获得最准确的报告

工具通过分析学生项目文件夹中的 Python / C / C++ 文件来生成报告内容。代码注释和结构的格式决定了 AI 能否准确理解课程内容。

### 顶部注释格式（最关键）

启动文件（`main.py` / `main.cpp` / `main.c`）顶部的注释是报告的基础，支持以下**课程主题**格式：

| 格式 | 示例 | 说明 |
|------|------|------|
| `# Course: <主题>` | `# Course: 飞翔的小鸟第一课` | 英文标记+冒号 |
| `# 课程：<主题>` | `# 课程：飞翔的小鸟第一课` | 中文标记+中文冒号 |
| `# 课程: <主题>` | `# 课程: 飞翔的小鸟第一课` | 中文标记+英文冒号 |
| `# 课程 <主题>` | `# 课程 飞翔的小鸟第一课` | 中文标记+空格（Walimaker 风格） |
| `# 课程名：<主题>` | `# 课程名：飞翔的小鸟第一课` | 冗余写法 |
| `# 主题：<主题>` | `# 主题：飞翔的小鸟第一课` | 主题词写法 |

> **推荐**使用 `# Course: 课程名称` 格式，最简单明确。
>
> C/C++ 工程使用 `//` 或 `/* ... */` 注释，标记文字与上表相同，例如 `// 课程：绘制五角星`、`// 作业:`。

### 课程目标（入口注释）

标题之后，每行一个目标，AI 会将其作为知识点提取的依据：

```python
# Course: 飞向地球
# 目标：
# 1. 使用键盘方向键控制飞船移动
# 2. 为黑洞添加引力效果
# 3. 让飞船与地球发生碰撞时显示"成功着陆"
```

### 作业引导配置

如需让 AI 根据指定要求出题，在注释中加入作业引导标记。标记后的内容会传给 AI 作为出题指导：

| 标记 | 示例 |
|------|------|
| `# 作业引导:` | `# 作业引导:` |
| `# 作业指导:` | `# 作业指导:` |
| `# 作业:` | `# 作业:`（Walimaker 风格） |
| `# HomeworkGuidance:` | `# HomeworkGuidance:` |

**示例：**

```python
# Course: 飞向地球
# 目标：
# 1. 使用键盘方向键控制飞船移动
# 2. 为黑洞添加引力效果
# 作业:
#  - 给飞船添加燃料条效果
#  - 给黑洞增加旋转动画
```

### 完整示例

**Walimaker / pgzero 游戏项目（推荐格式）：**

```python
"""
课程 飞向地球
目标：
1. 使用键盘的上下左右四个按键控制飞船的移动
2. 让黑洞有引力
作业:
 - 地球和飞船判断碰撞，地球使用say("成功着陆")
"""
from Walimaker import *

earth = Character('地球.png')
ufo = Character('ufo.png')

while True:
    if key_pressed(K_RIGHT):
        ufo.x += 5
    # ... 更多游戏逻辑
    if ufo.collide(earth):
        ufo.say("成功着陆")

    # 黑洞引力公式
    dis = ufo.distance(blackhole)
    force = 10000 / (dis**2 + 1)
    ufo.slide_to(blackhole.pos, force)
```

**Pygame / 标准 Python 项目：**

```python
# Course: 太空大战第三课
# 目标：
# 1. 实现子弹发射逻辑
# 2. 添加敌机自动生成

import pygame
import random

class Spaceship:
    def __init__(self):
        self.x = 400
        self.bullets = []

    def shoot(self):
        self.bullets.append(Bullet(self.x, self.y))

    def update(self):
        for b in self.bullets[:]:
            b.move()
            if b.off_screen():
                self.bullets.remove(b)
```

**C/C++ 工程（`main.cpp`）：**

```cpp
/*
 * 课程 01 基本语法
 * 目标：
 * 1. 变量与类型
 * 2. 标准输入输出
 * 作业:
 * 使用输入获取长方形边长 a、b，计算并输出周长
 */
#include <stdio.h>

int main() {
    int a, b;
    scanf("%d %d", &a, &b);
    printf("%d\n", (a + b) * 2);
    return 0;
}
```

### 非 Python 课程（Scratch / 机器人 / 硬件等）

在项目文件夹中创建 `course.py`，用注释描述课程内容：

```python
# Course: 小猫过马路第一课
#
# 本节课教学内容：
# 1. 认识 Scratch 界面（舞台、角色区、积木区）
# 2. 使用"移动10步"积木让角色前进
# 3. 使用"当绿旗被点击"事件积木启动程序
# 4. 使用"碰到边缘就反弹"控制角色边界
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

### 项目类型自动识别

工具根据文件中的 `import` / `#include` 语句自动判断项目类型，影响 AI 的知识点取向：

| 框架/库 | 识别的项目类型 | 说明 |
|---------|---------------|------|
| `pygame` | `pygame` | 标准 pygame 游戏 |
| `pgzero` | `pgzero` | PG Zero 框架 |
| `walimaker` | `pgzero` | Walimaker ≈ pgzero（游戏框架）|
| `turtle` | `turtle` | 海龟画图 |
| `tkinter` | `tkinter` | GUI 桌面应用 |
| `pyqt` / `pyside` | `pyqt` | Qt 桌面应用 |
| `arcade` | `arcade` | Arcade 游戏框架 |
| `flask` / `fastapi` / `django` | `web` | Web 服务 |
| `<iostream>` / `<stdio.h>` | `cpp` / `c` | C/C++ 控制台程序 |
| SFML / SDL / Qt / EasyX | `cpp_gui` | C/C++ 图形/游戏程序 |
| 无 GUI import / include | `algorithm` | 纯算法/逻辑项目（C/C++ 控制台会识别为 `cpp`/`c`） |

> **需要注意**：如果检测到错误的项目类型（如将游戏项目识别为 `algorithm`），AI 生成的知识点会偏离课程方向。一旦发现，检查代码中是否正确导入了对应框架包。

### 代码分析范围

工具对代码的分析包括：
- **Python AST / C/C++ 轻量解析**—Python 提取函数定义、类结构、import 依赖、装饰器；C/C++ 提取函数、类/结构体、`#include`
- **启动文件识别**—Python 优先 `main.py`；C/C++ 优先 `main.cpp` / `main.c`，其次包含 `main()` 的文件
- **关联文件读取**—从入口注释的 `# 文件:` / `// 文件:` 行引用的文件也会被完整读取
- **代码截断**—AI 接收最多 10,000 字符的源代码（一般课程完全够用）

### 提高 AI 准确度的建议

1. **注释要具体**："实现碰撞检测"不如"使用 `collide()` 方法检测飞船与陨石的碰撞"
2. **代码结构清晰**：把每节课的核心函数独立出来，函数名体现功能
3. **注释与代码一致**：如果注释说"黑洞引力"但代码里没有引力计算，AI 会产生困惑
4. **作业指导明确**：用 Python 的 `# 作业:` 或 C/C++ 的 `// 作业:` 标记给出具体任务，AI 出题会更贴近课程内容
5. **避免过多无关文件**：项目文件夹中只放本节课相关的 `.py` / `.cpp` / `.c` / `.h` 文件，无关文件会分散 AI 注意力

### AI 配置（设置页面）

在应用左侧「设置」→「AI 服务」卡片中填写供应商、API Key、模型、超时、重试次数、最大 Token 与各步骤温度参数，点击「保存设置」即时生效。

- API Key 优先保存在系统钥匙串（macOS 钥匙串 / Windows 凭据管理器），不可用时保存为本地加密文件；
- `data/user_settings.json` 中不写入明文 Key，接口只返回「已配置」状态和脱敏尾号；
- 旧版 `config/llm.yaml` 仅在首次升级时迁移一次，之后不再生效；
- 也可以用 `CRG_LLM__*` 环境变量覆盖页面配置（适合 CI / 无界面部署）。

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

### 版本号管理

版本号唯一来源是 [backend/version.py](backend/version.py)。

- `pyproject.toml` 通过 Hatchling 动态读取该文件；
- `backend/config.py`、`build.py`、`build.spec` 也从该文件读取；
- `config/app.yaml` 不再单独写 `app.version`，避免多处不一致。

发版时只需修改 `backend/version.py` 中的 `__version__`，然后执行 `uv lock` 更新锁文件、同步更新 README 的版本历史，不要再在其它文件手写版本号。

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
└── app.yaml            # 应用配置（可编辑）
data/
├── app.db              # SQLite 数据库
├── user_settings.json  # 用户设置（AI 配置、默认模板等，不含明文 Key）
├── .llm_secret.key     # API Key 加密密钥（钥匙串不可用时生成）
├── .llm_secret.enc     # API Key 密文
├── reports/            # 导出 PDF
├── screenshots/        # 上传截图
└── assets/             # Logo 等资产
```

### AI 配置

启动程序后访问 `http://127.0.0.1:8765`，进入「设置」页面：

1. 在「AI 服务」卡片选择供应商并填入 API Key；
2. 确认模型与地址，点击「保存并测试连接」；
3. 在「报告」卡片选择默认模板并保存。

设置即时生效，无需重启。API Key 加密保存，不会明文写入配置文件。

支持的供应商：

| 供应商 | `provider` 值 | 推荐 `default_model` |
|--------|--------------|-------------------|
| DeepSeek | `deepseek` | `deepseek-chat` |
| 通义千问 | `qwen` | `qwen-plus` |
| 智谱 GLM | `glm` | `glm-4` |
| OpenAI | `openai` | `gpt-4o-mini` |
| Claude | `claude` | `claude-sonnet-4-6` |

> 旧版本已有的 `config/llm.yaml` 会在首次启动时自动迁移到设置页面，并清除其中的明文 Key。

### 打包文件结构

```
dist/课程报告生成工具/
├── 课程报告生成工具.exe    # 主程序（Windows）— 直接双击运行
├── _internal/              # Python 运行时 + 依赖库（不要动里面的文件）
├── browser/               # [可选] Chromium 浏览器引擎（~200MB）
└── 首次启动后自动创建:
    ├── config/            # 用户配置文件目录
    │   └── app.yaml       # 应用设置
    └── data/              # 运行数据
        ├── app.db         # 数据库
        ├── user_settings.json  # 用户设置（页面维护）
        ├── .llm_secret.*  # API Key 加密存储
        ├── reports/       # 导出 PDF
        ├── screenshots/   # 截图
        └── assets/        # Logo
```

## 版本历史

```
v1.3.0 — AI 配置迁移到「设置」页面；API Key 加密存储（系统钥匙串 / 本地加密文件）；默认模板改为后端持久化；配置保存即时生效
v1.2.0 — 支持 C/C++ 工程；新增「素白极简」低打印负担模板；Classic/素白极简 Word 采用 PDF 风格卡片版式；导出按钮合并为「导出报告」；宿主机端口固定 8765
v1.1.0 — 重构项目文档，详述代码注释规范以提高AI准确度；去除作业评分标准
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
