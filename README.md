# KronosFinceptLab

独立的 Python + Web 金融量化分析平台，集成 Kronos K 线基础模型。

## 技术栈

- **后端**: FastAPI (Python 3.11+)
- **前端**: Next.js + Tailwind CSS + Framer Motion + TradingView Lightweight Charts
- **CLI**: Click（支持 Hermes Agent 远程调用）

## 数据源与模型

| 组件 | 名称 | 用途 |
|---|---|---|
| **数据源** | BaoStock | A 股日线数据（主数据源） |
| | AkShare | A 股数据（被反爬，自动降级） |
| | Yahoo Finance | 全球股票市场 |
| | Binance | 加密货币（国际） |
| | OKX | 加密货币（中国） |
| **预测模型** | NeoQuasar/Kronos-base | K 线预测（CPU 推理） |
| | NeoQuasar/Kronos-Tokenizer-base | Tokenizer |
| **数据格式** | OHLCV | 开/高/低/收/量/额 |

**自动降级链路**: AkShare → BaoStock → Yahoo Finance（熔断机制：连续失败 5 次禁用 5 分钟）

## 上游项目

- **Kronos**: https://github.com/shiyu-coder/Kronos — 金融 K 线基础模型
- **FinceptTerminal**: https://github.com/Fincept-Corporation/FinceptTerminal — 金融终端（参考设计，不直接依赖）

## Current status

Version: v8.2

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

### CFA 级别分析 (v4.0)
- DCF 模型（现金流折现）
- 风险指标（VaR, Sharpe, Sortino, 最大回撤, 波动率）
- 投资组合优化（马科维茨均值-方差, 有效前沿, 风险平价）
- 衍生品定价（Black-Scholes, 希腊字母, 隐含波动率）
- 财务数据获取（BaoStock + Yahoo Finance）
- CLI 命令：`kronos analyze dcf/risk/portfolio/derivative`
- API 路由：`/api/v1/analyze/*`

### 技术指标与策略 (v5.0)
- 技术指标：SMA, EMA, RSI, MACD, Bollinger Bands, KDJ, ATR, OBV
- 量化策略：均线交叉、RSI超买超卖、MACD金叉死叉、布林带突破
- CLI 命令：`kronos analyze indicator/strategy`
- 统一技术分析接口

### 全球市场数据 (v5.0)
- 美股数据：AAPL, MSFT, GOOGL, etc.
- 港股数据：0700.HK, 9988.HK, etc.
- 加密货币：BTC-USD, ETH-USD, etc.
- CLI 命令：`kronos analyze global-data/market-summary`

### AI 投资顾问 (v6.0)
- DeepSeek LLM 集成
- 自然语言股票分析
- 投资建议生成
- 风险评估报告
- CLI 命令：`kronos analyze ai-analyze/ai-report/ai-question`

### Web 前端 (v8.0)
- **TradingView K 线图表** — 预测叠加显示
- **AI 分析面板** — DeepSeek + Kronos 全量分析
- **自选股管理** — localStorage 持久化，Zustand 状态管理
- **批量预测对比** — 多股票排序，Recharts 可视化
- **设计系统** — 渐变文字、圆角卡片、入场动画

### 实时监控与告警 (v8.0)
- 价格变动告警（价格突破阈值、涨跌幅）
- 技术指标异动告警（RSI 超买超卖、MACD 金叉死叉）
- 预测偏差告警（实际价格与预测值偏离超过阈值）
- 成交量异动告警（成交量超过均值 N 倍）
- 通知渠道：飞书 Webhook / 邮件（可配置）
- CLI 命令：`kronos alert add/list/remove/check/monitor`
- API 路由：`/api/alert/*`

### 回测报告增强 (v8.0)
- HTML 报告生成（暗色主题，matplotlib 图表内嵌 base64）
- 收益曲线可视化
- 回撤曲线可视化
- 多策略对比回测
- 基准对比（沪深300、标普500 等）
- CLI 命令：`kronos backtest ranking --report`
- API 路由：`POST /api/backtest/report`

### Bug 修复与稳定性 (v8.1)
- `start.bat` 换行符 LF→CRLF + UTF-8 编码 + 自动安装依赖
- 预测 API 返回缺少 `model_id`/`tokenizer_id` 导致前端 `KeyError`
- 前端图表 `D1`~`D5` 相对日期无法解析

### 后端代码重构 (v8.2)
- service.py 提取 `_build_forecast_response()` 公共响应构建
- backtest.py 提取 `_fetch_and_prepare_data()` 和 `_run_ranking_backtest()` 公共回测引擎
- alert_engine.py 提取 `_evaluate_alert_conditions()` 通用告警条件评估
- schemas.py 添加 `ForecastRow.from_pydantic()` 和 `ForecastRequest.from_pydantic()` 类方法

### MCP 服务器
- `kronos_mcp/kronos_mcp_server.py` — 暴露 3 个 MCP 工具
- 支持 Claude Desktop / Cursor 等 MCP 客户端

### FinceptTerminal 兼容层（保留）
- PythonRunner 桥接脚本
- PythonWorker 协议验证通过
- C++ 服务层 `KronosForecastService.h/.cpp`

### Windows 部署
- Kronos-small 模型已部署（CPU 推理，PyTorch 2.11.0）
- 批处理脚本 `kronos.bat`（推荐用于真实推理）

### WSL/Linux 部署
- 支持 CPU 推理（PyTorch）
- 安装脚本：`bash scripts/install_torch.sh`
- 也可使用 Windows Python 运行真实推理（见下方）

## 快速开始

### Windows（推荐）

```bash
# 使用 bat 脚本（自动配置环境）
kronos.bat forecast --symbol 600519 --pred-len 5

# 或手动配置（如需）
set PYTHONPATH=src;external\Kronos
set KRONOS_REPO_PATH=external\Kronos
python scripts\win_launcher.py forecast --symbol 600519 --pred-len 5
```

### WSL/Linux

```bash
# 方式 1：一键安装（推荐，纯 WSL）
bash scripts/install_torch.sh
source .venv/bin/activate

# 方式 2：使用 Windows Python（推荐，无需安装 PyTorch）
chmod +x kronos.sh
./kronos.sh forecast --symbol 600519 --pred-len 5 --sample-count 10

# 手动指定 Python 路径（如自动检测失败）
WIN_PYTHON=/mnt/c/Users/你的用户名/AppData/Local/Programs/Python/Python313/python.exe ./kronos.sh forecast ...
```

**WSL 工作原理**：
- `kronos.sh` 自动检测 Windows Python 路径
- 将 WSL 路径转换为 Windows 路径（`/mnt/e/...` → `E:\...`）
- 调用 `win_launcher.py` 配置环境变量后执行 CLI
- 数据源（BaoStock/Yahoo）从 WSL 网络获取

### CLI（通用）

```bash
# 安装
pip install -e .

# 单资产预测（dry-run）
kronos forecast --symbol 600519 --pred-len 5 --dry-run

# 单资产预测（真实推理）
kronos forecast --symbol 600519 --pred-len 5

# 概率预测（Monte Carlo 采样）
kronos forecast --symbol 600519 --pred-len 5 --sample-count 10

# 批量预测
kronos batch --symbols 600519,000858,000001 --pred-len 5

# 获取数据
kronos data fetch --symbol 600519 --start 20240101 --end 20260429

# 策略回测
kronos backtest ranking --symbols 600519,000858 --start 20240101 --end 20260429

# 策略回测并生成 HTML 报告
kronos backtest ranking --symbols 600519,000858 --start 20240101 --end 20260429 --report

# AI 分析（A股）
kronos analyze ai-analyze --symbol 600519 --market cn

# AI 分析（美股）
kronos analyze ai-analyze --symbol AAPL --market us

# 添加告警规则
kronos alert add --type price_change --symbol 600519 --threshold 3.0

# 查看告警规则
kronos alert list

# 检查所有告警
kronos alert check

# 启动持续监控
kronos alert monitor --interval 5

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
