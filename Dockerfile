# ===================================================================
# 课程报告生成工具 — Docker 镜像
# ===================================================================
# 构建：docker build -t course-report-generator .
# 运行：docker run -p 8765:8765 -v crg_data:/app/data \
#         -e CRG_LLM__API_KEY=sk-xxx course-report-generator
# ===================================================================
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/your-username/course-report-generator"
LABEL org.opencontainers.image.description="少儿编程课程报告自动生成工具"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# ------------------------------------------------------------------
# 系统依赖
# ------------------------------------------------------------------
# uv — 快速 Python 包管理器
RUN pip install --no-cache-dir uv

# Playwright Chromium 运行所需动态库
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
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------
# 应用代码
# ------------------------------------------------------------------
COPY . .

# ------------------------------------------------------------------
# Python 依赖 & Playwright Chromium
# ------------------------------------------------------------------
# uv sync 默认以 editable 模式安装本项目，使得 __file__ 路径
# 解析（backend/paths.py）仍指向 /app/backend/，与开发环境一致。
RUN uv sync --no-dev

# Playwright Chromium 浏览器（用于 HTML → PDF 渲染）
RUN uv run python -m playwright install chromium

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
# 使用 uvicorn 直起（跳过 main.py 中的浏览器打开逻辑）
CMD ["uv", "run", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8765"]
