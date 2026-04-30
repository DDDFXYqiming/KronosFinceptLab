# KronosFinceptLab

独立的 Python + Web 金融量化分析平台，集成 Kronos K 线基础模型。

## 技术栈

- **后端**: FastAPI (Python 3.11+)
- **前端**: Next.js + Tailwind CSS + Framer Motion
- **CLI**: Click（支持 Hermes Agent 远程调用）
- **模型**: Kronos K 线预测模型（CPU/GPU）
- **数据**: 多数据源自动降级架构（AkShare → BaoStock → Yahoo Finance）

## 上游项目

- **Kronos**: https://github.com/shiyu-coder/Kronos — 金融 K 线基础模型
- **FinceptTerminal**: https://github.com/Fincept-Corporation/FinceptTerminal — 金融终端（参考设计，不直接依赖）

## Current status

Version: v3.0 ✅ (2026-04-30)

## 已实现

### 核心引擎
- Python 包 `src/kronos_fincept/`：schema 验证、数据适配器、服务层
- Kronos 推理封装：dry-run + real 模式，支持 Kronos-mini/small/base
- 采样参数：`temperature`, `top_k`, `top_p`, `sample_count`, `max_context`
- HuggingFace 缓存检测 + 离线失败提示
- JSON CLI 桥接：stdin/stdout + `--input`/`--output`

### 数据源
- 多数据源自动降级架构（AkShare → BaoStock → Yahoo Finance）
- 统一数据源管理器（DataSourceManager）
- 指数退避重试 + 熔断机制 + 内存/文件缓存
- ✅ CLI/API **全链路降级集成** — `kronos data fetch`、`kronos forecast` 等命令自动走 DataSourceManager，AkShare 失败时无缝切换到 BaoStock
- ✅ `akshare_adapter.py` — 统一数据入口，所有 6 个调用方（CLI、API、backtest）自动享受降级
- AkShare A 股 OHLCV 适配器
- BaoStock 数据源适配器（已验证可用）
- Yahoo Finance 数据源适配器（已验证可用）
- 通用 CSV/OHLCV 适配器（`data_adapter.py`）

### 量化引擎
- Qlib-style 模型适配器 + `batch_predict` 多资产批量预测
- 排序信号生成（predicted_return）
- A 股排名回测示例（`examples/backtest_a_stock_ranking.py`）

### MCP 服务器
- `kronos_mcp/kronos_mcp_server.py` — 暴露 3 个 MCP 工具
- 支持 Claude Desktop / Cursor 等 MCP 客户端

### FinceptTerminal 兼容层（保留）
- PythonRunner 桥接脚本
- PythonWorker 协议验证通过
- C++ 服务层 `KronosForecastService.h/.cpp`

### Windows 部署
- Kronos-small 模型已部署（CPU 推理，PyTorch 2.11.0）
- 批处理脚本 `kronos_forecast.bat`

## 快速开始

### CLI（推荐）

```bash
# 安装
pip install -e .

# 单资产预测（dry-run）
kronos forecast --symbol 600519 --pred-len 5 --dry-run

# 单资产预测（真实推理）
kronos forecast --symbol 600519 --pred-len 5

# 批量预测
kronos batch --symbols 600519,000858,000001 --pred-len 5

# 获取数据
kronos data fetch --symbol 600519 --start 20240101 --end 20260429

# 启动 API 服务
kronos serve --port 8000
```

### API 服务

```bash
# 启动
kronos serve --host 0.0.0.0 --port 8000

# 访问 Swagger UI
open http://localhost:8000/docs
```

### Web 前端

```bash
cd web
npm install
npm run dev
# 访问 http://localhost:3000
```

## 测试

```bash
PYTHONPATH=src python3 -m pytest tests -v
```

## CLI JSON 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| symbol | string | required | 资产代码 |
| timeframe | string | "1d" | K 线周期 |
| pred_len | int | required | 预测 K 线数 |
| dry_run | bool | false | 使用 dry-run 预测器 |
| model_id | string | NeoQuasar/Kronos-small | 模型 ID |
| temperature | float | 1.0 | 采样温度 |
| top_k | int | 0 | Top-k 过滤 |
| top_p | float | 0.9 | 核采样阈值 |
| sample_count | int | 1 | 并行采样数 |

## 输出格式

成功响应：`ok`, `symbol`, `timeframe`, `model_id`, `pred_len`, `forecast`, `metadata`

所有预测结果仅为研究用途，不构成投资建议。
