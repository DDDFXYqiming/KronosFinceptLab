# Kronos 模型服务 - Windows 使用指南

## 概述

Kronos 模型服务已部署到 Windows 系统，可以通过以下方式使用：

1. **FinceptTerminal PythonRunner** - 直接在 FinceptTerminal 中调用
2. **命令行工具** - 通过批处理脚本调用
3. **MCP 服务器** - 供 AI Agent 调用

## 环境要求

- **操作系统**: Windows 10/11
- **Python**: 3.13.6 (已安装)
- **PyTorch**: 2.11.0 (已安装)
- **存储空间**: 约 500MB (模型文件)

## 模型位置

```
E:\AI_Projects\KronosFinceptLab\external\
├── Kronos\                    # Kronos 上游代码
├── Kronos-small\              # Kronos-small 模型 (98MB)
├── Kronos-Tokenizer-base\     # 分词器 (15MB)
├── hub\                       # HuggingFace Hub 缓存
└── xet\                       # 其他缓存
```

## 快速开始

### 方法 1: 使用批处理脚本 (推荐)

```batch
# 进入 FinceptTerminal 脚本目录
cd E:\FinceptTerminal\scripts

# 运行测试预测
run_kronos_forecast.bat --test

# 从文件输入
run_kronos_forecast.bat --input request.json

# 从标准输入
echo {"symbol":"600519",...} | run_kronos_forecast.bat --stdin
```

### 方法 2: 使用主项目脚本

```batch
# 进入项目目录
cd E:\AI_Projects\KronosFinceptLab

# 运行测试
kronos_forecast.bat --test

# 运行批量预测
kronos_forecast.bat --batch

# 启动 MCP 服务器
kronos_forecast.bat --mcp
```

### 方法 3: 手动设置环境变量

```batch
# 设置环境变量
set KRONOS_REPO_PATH=E:\AI_Projects\KronosFinceptLab\external\Kronos
set HF_HOME=E:\AI_Projects\KronosFinceptLab\external
set PYTHONPATH=E:\AI_Projects\KronosFinceptLab\src

# 进入脚本目录
cd E:\FinceptTerminal\scripts

# 运行预测
python kronos_forecast.py --input request.json
```

## 输入格式

### 单资产预测

```json
{
  "symbol": "600519",
  "timeframe": "1d",
  "pred_len": 5,
  "dry_run": false,
  "rows": [
    {
      "timestamp": "2026-04-01",
      "open": 1400,
      "high": 1420,
      "low": 1390,
      "close": 1410,
      "volume": 1000000,
      "amount": 1400000000
    },
    ...
  ]
}
```

### 批量预测

```json
{
  "assets": [
    {
      "symbol": "600519",
      "rows": [...]
    },
    {
      "symbol": "000858",
      "rows": [...]
    }
  ],
  "pred_len": 5,
  "dry_run": false
}
```

## 输出格式

```json
{
  "ok": true,
  "symbol": "600519",
  "timeframe": "1d",
  "model_id": "NeoQuasar/Kronos-small",
  "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
  "pred_len": 5,
  "forecast": [
    {
      "timestamp": "2026-04-15 00:00:00+00:00",
      "open": 1500.0,
      "high": 1510.0,
      "low": 1490.0,
      "close": 1505.0,
      "volume": 0.0,
      "amount": 0.0
    },
    ...
  ],
  "metadata": {
    "device": "cpu",
    "elapsed_ms": 1234,
    "warning": "Research forecast only; not trading advice."
  }
}
```

## 在 FinceptTerminal 中使用

### 1. PythonRunner 调用

FinceptTerminal 的 PythonRunner 可以直接调用 `kronos_forecast.py`:

```python
# 在 FinceptTerminal 的 Python 脚本中
import subprocess
import json

# 准备输入数据
input_data = {
    "symbol": "600519",
    "timeframe": "1d",
    "pred_len": 5,
    "dry_run": False,
    "rows": [...]  # 历史 K 线数据
}

# 调用 Kronos 预测
result = subprocess.run(
    ["python", "kronos_forecast.py"],
    input=json.dumps(input_data),
    capture_output=True,
    text=True,
    cwd="E:\\FinceptTerminal\\scripts"
)

# 解析输出
if result.returncode == 0:
    forecast = json.loads(result.stdout)
    print(f"预测结果: {forecast}")
else:
    print(f"错误: {result.stderr}")
```

### 2. Agent 调用

FinceptTerminal 的 Agent 可以通过 MCP 协议调用 Kronos:

```json
{
  "tool": "forecast_ohlcv",
  "arguments": {
    "symbol": "600519",
    "pred_len": 5,
    "rows": [...]
  }
}
```

## 故障排除

### 1. Python 未找到

```
错误: 未找到 Python
```

**解决方案**: 确保 Python 3.13.6 已安装并添加到 PATH。

### 2. PyTorch 未找到

```
错误: 未找到 PyTorch
```

**解决方案**: 安装 PyTorch:
```batch
pip install torch torchvision torchaudio
```

### 3. kronos_fincept 包未找到

```
错误: 未找到 kronos_fincept 包
```

**解决方案**: 安装包:
```batch
cd E:\AI_Projects\KronosFinceptLab
pip install -e .
```

### 4. 模型加载失败

```
错误: 无法加载模型
```

**解决方案**: 
1. 检查模型文件是否存在
2. 检查 `KRONOS_REPO_PATH` 环境变量
3. 检查网络连接 (首次运行需要下载模型)

### 5. 内存不足

```
错误: 内存不足
```

**解决方案**:
1. 使用 `Kronos-mini` 模型 (更小)
2. 减少 `pred_len` 参数
3. 增加系统内存

## 性能优化

### 1. 使用 GPU (如果可用)

```batch
# 检查 CUDA 是否可用
python -c "import torch; print(torch.cuda.is_available())"
```

如果 CUDA 可用，PyTorch 会自动使用 GPU。

### 2. 缓存模型

首次运行会下载模型，后续运行会使用缓存。

### 3. 批量处理

使用 `batch_forecast_ohlcv` 可以批量处理多个资产，效率更高。

## 安全注意事项

1. **仅用于研究**: 所有预测结果仅用于研究/回测/纸交易
2. **不用于实盘**: 不要将预测结果用于真实交易
3. **风险自担**: 使用 Kronos 预测的风险由用户自行承担

## 更新日志

- **v0.5** (2026-04-29): 初始部署
  - Kronos-small 模型部署完成
  - FinceptTerminal 桥接脚本部署完成
  - Windows 批处理脚本创建完成

## 联系方式

如有问题，请联系项目维护者。
