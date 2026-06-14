#!/bin/bash
set -e

echo "========================================"
echo "  Sakura 依赖安装"
echo "========================================"
echo ""

# ============================================================
# 检测 Python：优先使用 runtime 内置 Python，其次系统 Python
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/python_env.sh"

if ! PYTHON_EXE="$(select_install_python "$PROJECT_ROOT")"; then
    echo "[错误] 未找到带 pip 的 Python3，请安装 Python 或下载完整 release 包"
    echo "       https://www.python.org/downloads/"
    exit 1
fi
echo "[OK] 使用 Python: $PYTHON_EXE"

# ============================================================
# 检测 requirements.txt
# ============================================================
if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
    echo "[错误] 未找到 requirements.txt"
    exit 1
fi

# ============================================================
# pip install 依赖
# ============================================================
echo ""
echo "Installing dependencies..."
echo ""

cd "$PROJECT_ROOT"
"$PYTHON_EXE" -m pip install -r requirements.txt

echo ""
echo "========================================"
echo "  安装完成！运行 scripts/start.sh 启动"
echo "========================================"
