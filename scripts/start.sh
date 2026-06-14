#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/python_env.sh"

# ============================================================
# 检测 Python：选择已安装 Sakura 核心依赖的解释器
# ============================================================
if ! PYTHON_EXE="$(select_runtime_python "$PROJECT_ROOT")"; then
    echo "[错误] 未找到已安装完整 Sakura 依赖的 Python。"
    echo "       请先运行 scripts/install.sh。"
    exit 1
fi
echo "[启动] 使用 Python: $PYTHON_EXE"

# ============================================================
# 设置 sentence-transformers 模型缓存到项目目录
# ============================================================
export HF_HOME="$PROJECT_ROOT/runtime/hf-cache"
export SENTENCE_TRANSFORMERS_HOME="$PROJECT_ROOT/runtime/hf-cache"
mkdir -p "$HF_HOME"

# ============================================================
# 启动
# ============================================================
cd "$PROJECT_ROOT"
exec "$PYTHON_EXE" main.py
