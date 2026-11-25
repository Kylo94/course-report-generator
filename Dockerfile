# ===================================================================
# 课程报告生成工具 — Docker 镜像
# ===================================================================
# 构建：docker build -t course-report-generator .
# 运行：docker run -p 8765:8765 -v crg_data:/app/data \
#         -e CRG_LLM__API_KEY=sk-xxx course-report-generator
#
# 分层说明（重要）：
#   1. 系统依赖 / uv / Playwright 浏览器放在「复制业务代码」之前；
#   2. 先只复制 pyproject.toml、uv.lock，安装 Python 依赖；
#   3. 再复制 backend / templates / frontend 等业务代码；
#   4. 最后只做一次快速的 `uv sync` 安装本项目。
#   这样改业务代码时，不会重新下载 500MB+ 依赖和 1GB+ Chromium，
#   日常 rebuild 通常只需要几秒到几十秒。
# ===================================================================
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/your-username/course-report-generator"
LABEL org.opencontainers.image.description="少儿编程课程报告自动生成工具"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# ------------------------------------------------------------------
# 系统依赖
# ------------------------------------------------------------------
# uv — 快速 Python 包管理器（使用官方安装脚本，避免 PyPI hash 校验问题）
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org uv

# Playwright Chromium 运行所需动态库 + 中文字体（否则 PDF 中文会变方框）
# + poppler-utils（pdf2image 转长图依赖）
# 分两步：先装基础依赖，再装字体和 poppler（避免字体包与 poppler 触发顺序问题）
# 分三步安装：先基础库，再字体+poppler，最后做字体缓存
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0t64 \
    libatk-bridge2.0-0t64 \
    libcups2t64 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 \
    libatspi2.0-0t64 \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN fc-cache -fv

# ------------------------------------------------------------------
# Python 依赖（只依赖 pyproject.toml + uv.lock，不依赖业务代码）
# ------------------------------------------------------------------
# 先复制依赖清单。README.md 是 pyproject.toml 的 readme 字段需要的。
COPY pyproject.toml uv.lock README.md ./

# 只安装第三方依赖，不安装本项目；这一层只在依赖变化时重建。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# Playwright 只安装 headless shell（PDF 渲染只需要它），体积约为完整 Chromium 的 1/3。
# 加入 3 次重试与更长下载超时，避免网络抖动导致整次 build 失败。
ENV PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000
RUN set -e; \
    for i in 1 2 3; do \
        if .venv/bin/python -m playwright install --only-shell chromium --no-progress; then \
            exit 0; \
        fi; \
        echo "Playwright install failed, retry $i/3 ..."; \
        sleep 5; \
    done; \
    exit 1

# ------------------------------------------------------------------
# 应用代码
# ------------------------------------------------------------------
COPY . .

# 依赖已经装好，这一步只把本项目以 editable 方式安装进 .venv，速度很快。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# 清理开发产物
RUN rm -rf .git tests htmlcov .coverage .ruff_cache

# ------------------------------------------------------------------
# 环境变量
# ------------------------------------------------------------------
# 容器内必须监听 0.0.0.0 才能对外暴露端口
ENV CRG_SERVER__HOST=0.0.0.0
ENV CRG_SERVER__RELOAD=false
ENV CRG_APP__DEBUG=false
# 关闭 main.py 中的自动打开浏览器逻辑（使用 uvicorn 直起不会触发，
# 但留作兜底）
ENV CRG_NO_BROWSER=1

EXPOSE 8765

# ------------------------------------------------------------------
# 启动
# ------------------------------------------------------------------
# 直接使用 .venv 里的 uvicorn 启动。
# 不要用 `uv run uvicorn`：uv run 默认会重新 sync（包括 dev 组），
# 导致容器启动时还要联网下载 ruff/pygments 等开发依赖，启动慢且容易失败。
CMD [".venv/bin/python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8765"]
