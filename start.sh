#!/usr/bin/env bash
# ============================================================
# start.sh — 快速启动课程报告生成工具
# 用法：
#   chmod +x start.sh
#   ./start.sh            # 正常启动
#   ./start.sh -d         # debug 模式
#   ./start.sh --help     # 查看所有选项
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 颜色 ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── 默认值 ────────────────────────────────────────────
PORT=8765
DEBUG=false
RELOAD=false
HOST="0.0.0.0"

# ── 解析参数 ──────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--debug)
      DEBUG=true
      shift
      ;;
    --reload)
      RELOAD=true
      shift
      ;;
    -p|--port)
      PORT="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    -h|--help)
      echo "用法: $0 [选项]"
      echo ""
      echo "选项:"
      echo "  -d, --debug     启用 debug 日志"
      echo "  --reload        启用热重载（开发用）"
      echo "  -p, --port PORT 指定端口（默认 8765）"
      echo "  --host HOST     指定监听地址（默认 0.0.0.0）"
      echo "  -h, --help      显示此帮助"
      exit 0
      ;;
    *)
      echo -e "${RED}未知参数: $1${NC}"
      echo "用法: $0 [选项]  （使用 --help 查看帮助）"
      exit 1
      ;;
  esac
done

# ── 检查 uv ───────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo -e "${RED}✗ 未找到 uv 命令${NC}"
  echo "  请先安装 uv："
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# ── 检查 .venv ────────────────────────────────────────
if [[ ! -d .venv ]]; then
  echo -e "${YELLOW}⚠ 未找到 .venv，正在创建...${NC}"
  uv sync
  echo -e "${GREEN}✓ 虚拟环境创建完成${NC}"
fi

# ── 检查配置文件 ──────────────────────────────────────
if [[ ! -f config/llm.yaml ]]; then
  echo -e "${YELLOW}⚠ 未找到 config/llm.yaml，将使用默认配置${NC}"
  echo "  首次使用请编辑 config/llm.yaml 填入 API Key"
fi

# ── 启动信息 ──────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   📄 课程报告生成工具                    ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║  ${NC}地址: http://$HOST:$PORT${NC}"
echo -e "${CYAN}║  ${NC}模式: $($DEBUG && echo 'DEBUG' || echo '正常')${NC}"
echo -e "${CYAN}║  ${NC}重载: $($RELOAD && echo '开启' || echo '关闭')${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 构建启动命令 ──────────────────────────────────────
CMD="uv run python main.py"
if $DEBUG; then
  export CRG_APP__LOG_LEVEL=DEBUG
fi
if $RELOAD; then
  CMD="$CMD --reload"
fi

# ── 启动 ──────────────────────────────────────────────
echo -e "${GREEN}→ 启动中...${NC}"
echo -e "${YELLOW}   按 Ctrl+C 停止${NC}"
echo ""
$CMD
