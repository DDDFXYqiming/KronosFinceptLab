# KronosFinceptLab

独立的 Python + Rust + Web 金融量化分析平台，集成 Kronos K 线基础模型。

## 技术栈

- **后端**: FastAPI (Python 3.11+)
- **Rust 加速**: Cargo workspace + PyO3/maturin（可选 native extension）
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
| **网页检索** | Tavily/Brave/Serper/custom | Agent 可选公开信息检索 |
| **预测模型** | NeoQuasar/Kronos-base | 默认 K 线预测模型（CPU 推理） |
| | NeoQuasar/Kronos-mini/base | 可选模型 |
| | NeoQuasar/Kronos-Tokenizer-base | Tokenizer |
| **数据格式** | OHLCV | 开/高/低/收/量/额 |

## 上游项目

- **Kronos**: https://github.com/shiyu-coder/Kronos — 金融 K 线基础模型
- **FinceptTerminal**: https://github.com/Fincept-Corporation/FinceptTerminal — 金融终端（参考设计，不直接依赖）
- **Digital Oracle**: https://github.com/komako-workshop/digital-oracle — 宏观金融信号与 provider 方法论（v10.1 起参考集成）

## Current status

Version: v10.0

V10 已启动：v10.0 先完成线上已知 Bug 修复与部署加固，包括 Agent 多标的稳定展示、DeepSeek endpoint 容错、分析页最近 5 轮临时历史、常见标的别名补全和移动端/Zeabur 错误提示增强。Digital Oracle 将作为后续宏观信号层的开发参考。

## 三端能力对照

| 能力 | Web | API | CLI |
|---|---|---|---|
| 行情获取 | `/data`, `/forecast` | `GET /api/data/*` | `kronos data fetch` |
| Kronos 预测 | `/forecast`, `/batch` | `POST /api/forecast`, `POST /api/batch` | `kronos forecast`, `kronos batch` |
| Agent 分析 | `/analysis` | `POST /api/v1/analyze/agent` | `kronos analyze agent` |
| 风险/估值/组合 | `/analysis` 汇总展示 | `POST /api/v1/analyze/*` | `kronos analyze risk/dcf/portfolio` |
| 回测 | `/backtest` | `POST /api/backtest/ranking` | `kronos backtest ranking` |
| 健康检查 | Header 状态 | `GET /api/health` | `kronos serve` 后访问 health |

## Zeabur 配置

必要变量：`PORT`、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`JWT_SECRET`。`DEEPSEEK_BASE_URL` 推荐填写根地址 `https://api.deepseek.com`；若误填完整 `https://api.deepseek.com/chat/completions`，后端会兼容处理。

可选变量：`KRONOS_MODEL_ID`、`HF_TOKEN`、`WEB_SEARCH_PROVIDER`、`WEB_SEARCH_API_KEY`、`WEB_SEARCH_MAX_RESULTS`、`WEB_SEARCH_TIMEOUT_SECONDS`。

忽略边界：`.env`、`SPEC.md`、`external/`、`models/`、`.cache/`、`logs/`、`web/node_modules/`、`web/.next/` 不进入 git；Docker 镜像同样排除这些路径。

## 质量闸门

```bash
python -m pytest tests -q

cd web
npm run typecheck
npm run lint
npm run test:frontend
npm run build:zeabur
npm run check:bundle

# 本地 Web 已启动时执行
npm run smoke:pages
```

## 快速开始

### Windows（推荐）

```bash
# 使用 bat 脚本（自动配置环境）
kronos.bat forecast --symbol 600036 --pred-len 5

# 或手动配置（如需）
set PYTHONPATH=src;external\Kronos
set KRONOS_REPO_PATH=external\Kronos
python scripts\win_launcher.py forecast --symbol 600036 --pred-len 5
```

### WSL/Linux

```bash
# 方式 1：一键安装（推荐，纯 WSL）
bash scripts/install_torch.sh
source .venv/bin/activate

# 方式 2：使用 Windows Python（推荐，无需安装 PyTorch）
chmod +x kronos.sh
./kronos.sh forecast --symbol 600036 --pred-len 5 --sample-count 10

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
kronos forecast --symbol 600036 --pred-len 5 --dry-run

# 单资产预测（真实推理）
kronos forecast --symbol 600036 --pred-len 5

# 概率预测（Monte Carlo 采样）
kronos forecast --symbol 600036 --pred-len 5 --sample-count 10

# 批量预测
kronos batch --symbols 600036,000858,000001 --pred-len 5

# 获取数据
kronos data fetch --symbol 600036 --start 20240101 --end 20260429

# 策略回测
kronos backtest ranking --symbols 600036,000858 --start 20240101 --end 20260429

# 策略回测并生成 HTML 报告
kronos backtest ranking --symbols 600036,000858 --start 20240101 --end 20260429 --report

# AI 分析（A股）
kronos analyze ai-analyze --symbol 600036 --market cn

# 自然语言 Agent 分析
kronos analyze agent --question "帮我看看招商银行现在能不能买"

# AI 分析（美股）
kronos analyze ai-analyze --symbol AAPL --market us

# 添加告警规则
kronos alert add --type price_change --symbol 600036 --threshold 3.0

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
python -m pytest tests -q
cd web && npm run typecheck && npm run lint && npm run test:frontend
cd web && npm run build:zeabur && npm run check:bundle
```

## 日志与运维

默认日志写入 `logs/kronos-YYYYMMDD.log`，同时输出到 stderr。常用配置：

```bash
KRONOS_LOG_LEVEL=DEBUG
KRONOS_LOG_FORMAT=json
KRONOS_LOG_DIR=logs
KRONOS_LOG_RETENTION_DAYS=14
KRONOS_LOG_MAX_BYTES=10485760
```

查看日志：

```bash
# PowerShell
Get-Content logs\kronos-*.log -Tail 100

# JSON Lines 模式下每一行都是独立 JSON
Get-Content logs\kronos-*.log -Tail 10
```

清理历史日志可直接删除 `logs/` 下旧文件；目录已被 git 忽略。API 错误响应会返回 `request_id`，可用该 ID 在日志里定位完整异常栈。

### Rust native 加速（可选）

首次配置 Windows Rust 环境：

```powershell
# 安装 Rust 工具链
Invoke-WebRequest -Uri https://win.rustup.rs/x86_64 -OutFile $env:TEMP\rustup-init.exe
& $env:TEMP\rustup-init.exe -y --profile minimal --default-host x86_64-pc-windows-gnu --default-toolchain stable-x86_64-pc-windows-gnu

# 安装 GNU linker（如系统没有 gcc）
winget install --id BrechtSanders.WinLibs.POSIX.MSVCRT -e --accept-source-agreements --accept-package-agreements --silent

# 安装 Python 构建工具
python -m pip install maturin
```

构建并启用 native extension：

```powershell
$mingwBin = (Get-ChildItem -Path $env:LOCALAPPDATA\Microsoft\WinGet\Packages -Recurse -Filter gcc.exe | Select-Object -First 1).Directory.FullName
$env:Path="$env:USERPROFILE\.cargo\bin;$mingwBin;$env:Path"

cargo test --workspace
cargo clippy --workspace -- -D warnings
python -m maturin build --manifest-path crates/kronos-python/Cargo.toml --release --out dist/native
python -m pip install --force-reinstall (Get-ChildItem -LiteralPath dist\native -Filter *.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

$env:USE_RUST_ENGINE="1"
python -m pytest tests/test_rust_native_bridge.py -v
python scripts/benchmark_rust_native.py
```

## CLI JSON 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| symbol | string | required | 资产代码 |
| timeframe | string | "1d" | K 线周期 |
| pred_len | int | required | 预测 K 线数 |
| dry_run | bool | false | 使用 dry-run 预测器 |
| model_id | string | NeoQuasar/Kronos-base | 模型 ID |
| temperature | float | 1.0 | 采样温度 |
| top_k | int | 0 | Top-k 过滤 |
| top_p | float | 0.9 | 核采样阈值 |
| sample_count | int | 1 | 并行采样数 |

## 输出格式

成功响应：`ok`, `symbol`, `timeframe`, `model_id`, `pred_len`, `forecast`, `metadata`

所有预测结果仅为研究用途，不构成投资建议。
