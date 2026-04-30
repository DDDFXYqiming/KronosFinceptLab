#!/bin/bash
# KronosFinceptLab CLI wrapper for WSL
# 使用 Windows Python 运行真实推理（利用已安装的 PyTorch）
#
# 用法: ./kronos.sh forecast --symbol 600132 --pred-len 5
#       ./kronos.sh forecast --symbol 600132 --pred-len 5 --sample-count 10

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 自动检测 Windows Python 路径
WIN_PYTHON=""
for candidate in \
    "/mnt/c/Users/$USER/AppData/Local/Programs/Python/Python313/python.exe" \
    "/mnt/c/Users/*/AppData/Local/Programs/Python/Python313/python.exe" \
    "/mnt/c/Python313/python.exe"; do
    for p in $candidate; do
        if [ -f "$p" ]; then
            WIN_PYTHON="$p"
            break 2
        fi
    done
done

if [ -z "$WIN_PYTHON" ]; then
    echo "错误: 找不到 Windows Python"
    echo "请手动设置 WIN_PYTHON 环境变量"
    exit 1
fi

# 将 WSL 路径转换为 Windows 路径 (使用 wslpath)
WIN_SCRIPT_DIR=$(wslpath -w "$SCRIPT_DIR" 2>/dev/null || echo "$SCRIPT_DIR" | sed 's|^/mnt/\([a-z]\)/|\U\1:\\|g')

# 设置 HuggingFace 环境变量（使用本地模型）
WIN_EXTERNAL=$(wslpath -w "$SCRIPT_DIR/external" 2>/dev/null || echo "$SCRIPT_DIR/external" | sed 's|^/mnt/\([a-z]\)/|\U\1:\\|g')

echo "[WSL] 使用 Windows Python: $WIN_PYTHON"
echo "[WSL] 项目路径: $WIN_SCRIPT_DIR"

# 执行（设置 HF_HOME 和离线模式）
exec env \
    HF_HOME="$WIN_EXTERNAL" \
    HF_HUB_OFFLINE=1 \
    "$WIN_PYTHON" "$WIN_SCRIPT_DIR\\scripts\\win_launcher.py" "$@"
