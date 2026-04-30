#!/bin/bash
# KronosFinceptLab CLI wrapper for WSL
# 使用 Windows Python 运行真实推理（利用已安装的 PyTorch）
#
# 用法: ./kronos.sh forecast --symbol 600132 --pred-len 5
#       ./kronos.sh forecast --symbol 600132 --pred-len 5 --sample-count 10
#       ./kronos.sh analyze ai-analyze --symbol 0700.HK --market hk
#       ./kronos.sh analyze ai-analyze --symbol AAPL --market us

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

# 检查是否是 analyze ai-analyze 命令，且 market 不是 cn
# 如果是港股/美股/大宗商品，预获取数据并保存到临时文件
MARKET=""
SYMBOL=""
PREFETCH_DATA=false

for arg in "$@"; do
    if [ "$prev_arg" = "--market" ]; then
        MARKET="$arg"
    fi
    if [ "$prev_arg" = "--symbol" ]; then
        SYMBOL="$arg"
    fi
    prev_arg="$arg"
done

# 如果是港股/美股/大宗商品，预获取数据
if [ "$MARKET" != "cn" ] && [ -n "$MARKET" ] && [ -n "$SYMBOL" ]; then
    PREFETCH_DATA=true
    # 使用 Windows 可访问的临时目录（使用正确的 Windows 用户）
    WIN_USER=$(ls /mnt/c/Users/ | grep -E "^[0-9]+$" | head -1)
    TEMP_DIR="/mnt/c/Users/${WIN_USER}/AppData/Local/Temp"
    TEMP_FILE_WSL="${TEMP_DIR}/kronos_${SYMBOL//[^a-zA-Z0-9]/_}.json"
    TEMP_FILE_WIN="C:\\Users\\${WIN_USER}\\AppData\\Local\\Temp\\kronos_${SYMBOL//[^a-zA-Z0-9]/_}.json"
    
    echo "[WSL] 预获取全球市场数据: $SYMBOL ($MARKET)"
    
    # 根据 market 设置 Yahoo Finance ticker 格式
    case "$MARKET" in
        hk)
            YAHOO_SYMBOL="$SYMBOL"
            ;;
        us)
            YAHOO_SYMBOL="$SYMBOL"
            ;;
        commodity)
            # 大宗商品 ticker 格式
            case "$SYMBOL" in
                gold|黄金) YAHOO_SYMBOL="GC=F" ;;
                oil|石油) YAHOO_SYMBOL="CL=F" ;;
                copper|铜) YAHOO_SYMBOL="HG=F" ;;
                *) YAHOO_SYMBOL="$SYMBOL" ;;
            esac
            ;;
        *)
            YAHOO_SYMBOL="$SYMBOL"
            ;;
    esac
    
    # 通过 WSL curl 获取数据（保存到 Windows 可访问的位置）
    curl -s "https://query1.finance.yahoo.com/v8/finance/chart/${YAHOO_SYMBOL}?range=6mo&interval=1d" \
        -H "User-Agent: Mozilla/5.0" \
        -o "$TEMP_FILE_WSL" 2>/dev/null
    
    if [ -f "$TEMP_FILE_WSL" ] && [ -s "$TEMP_FILE_WSL" ]; then
        # 验证是否是有效的 JSON
        if python3 -c "import json; json.load(open('$TEMP_FILE_WSL'))" 2>/dev/null; then
            # 将数据保存为 Kronos 格式
            python3 -c "
import json
from datetime import datetime

with open('$TEMP_FILE_WSL', 'r') as f:
    data = json.load(f)

chart_data = data.get('chart', {}).get('result', [{}])[0]
timestamps = chart_data.get('timestamp', [])
quotes = chart_data.get('indicators', {}).get('quote', [{}])[0]

if timestamps and quotes:
    rows = []
    for i, ts in enumerate(timestamps):
        dt = datetime.utcfromtimestamp(ts)
        rows.append({
            'timestamp': dt.strftime('%Y-%m-%d'),
            'open': float(quotes['open'][i]) if quotes['open'][i] else 0,
            'high': float(quotes['high'][i]) if quotes['high'][i] else 0,
            'low': float(quotes['low'][i]) if quotes['low'][i] else 0,
            'close': float(quotes['close'][i]) if quotes['close'][i] else 0,
            'volume': float(quotes['volume'][i]) if quotes['volume'][i] else 0,
            'amount': float(quotes['volume'][i] * quotes['close'][i]) if quotes['volume'][i] and quotes['close'][i] else 0
        })
    
    # 获取公司名称
    company_name = chart_data.get('meta', {}).get('longName', '$SYMBOL')
    
    print(f'[WSL] Got data: {company_name}, {len(rows)} days')
else:
    print('[WSL] No data received')
" 2>&1
            
            # 传递环境变量给 Windows Python
            export KRONOS_GLOBAL_DATA_FILE="$TEMP_FILE_WIN"
        else
            echo "[WSL] Warning: Invalid JSON data, falling back to Windows Python"
        fi
    else
        echo "[WSL] Warning: Failed to fetch data, falling back to Windows Python"
    fi
fi

# 执行（设置 HF_HOME 和离线模式）
exec env \
    HF_HOME="$WIN_EXTERNAL" \
    HF_HUB_OFFLINE=1 \
    KRONOS_GLOBAL_DATA_FILE="$TEMP_FILE_WIN" \
    "$WIN_PYTHON" "$WIN_SCRIPT_DIR\\scripts\\win_launcher.py" "$@"
