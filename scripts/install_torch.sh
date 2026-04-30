#!/bin/bash
# WSL/Linux 环境下安装 PyTorch (CPU) 的脚本
# 用法: bash scripts/install_torch.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "=== KronosFinceptLab WSL 环境安装 ==="
echo ""

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

echo "Python 版本: $(python3 --version)"

# 创建虚拟环境（如果不存在）
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 安装 PyTorch CPU (使用国内镜像)
echo ""
echo "安装 PyTorch CPU..."
echo "使用阿里云镜像源..."

pip install torch \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --timeout 300 \
    --retries 3

# 验证安装
echo ""
echo "验证 PyTorch..."
python3 -c "import torch; print(f'PyTorch {torch.__version__} 安装成功')"

# 安装项目依赖
echo ""
echo "安装项目其他依赖..."
pip install -e "$PROJECT_ROOT" \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com

echo ""
echo "=== 安装完成 ==="
echo ""
echo "使用方法:"
echo "  source .venv/bin/activate"
echo "  kronos forecast --symbol 600132 --pred-len 5"
echo ""
echo "或者使用 Windows Python (推荐用于真实推理):"
echo "  scripts/win_launcher.py forecast --symbol 600132 --pred-len 5"
