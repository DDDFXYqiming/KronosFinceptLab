# KronosFinceptLab

Version: v10.8.7

An independent Python + Rust + Web quantitative finance analytics platform integrated with the Kronos candlestick foundation model.

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Rust acceleration**: Cargo workspace + PyO3/maturin (optional native extension)
- **Frontend**: Next.js + Tailwind CSS + Framer Motion + TradingView Lightweight Charts
- **CLI**: Click (supports Hermes Agent remote invocation)

## Data Sources and Models

| Component | Name | Purpose |
|---|---|---|
| **Market Data** | BaoStock | A-share daily data (primary source) |
| | AkShare | A-share data (automatically degraded when anti-crawling is triggered) |
| | Yahoo Finance | Global stock markets |
| | Binance | Crypto assets (global) |
| | OKX | Crypto assets (China) |
| **Web Search** | Tavily/Brave/Serper/custom | Optional public information retrieval for the agent |
| **Official Disclosures** | CNINFO (Juchao) | A-share announcements, periodic reports, interim forecasts, buybacks/dividends, etc. |
| **LLM Endpoint** | DeepSeek Chat Completions | `https://api.deepseek.com/chat/completions` |
| **Forecast Models** | NeoQuasar/Kronos-base | Default candlestick forecast model (CPU inference) |
| | NeoQuasar/Kronos-mini/base | Optional model |
| | NeoQuasar/Kronos-Tokenizer-base | Tokenizer |
| **Data Format** | OHLCV | Open/High/Low/Close/Volume/Amount |

## Upstream Projects

- **Kronos**: https://github.com/shiyu-coder/Kronos — financial candlestick foundation model
- **FinceptTerminal**: https://github.com/Fincept-Corporation/FinceptTerminal — financial terminal reference design, not directly depended on
- **Digital Oracle**: https://github.com/komako-workshop/digital-oracle — macro signal and provider methodology (reference integration starting v10.1)

Macroeconomic analysis is coordinated by `MacroDataManager` in a Digital-Oracle-style provider flow, currently covering 17 signal types such as predicted market conditions, yield curves, CFTC COT, on-chain/crypto, SEC/EDGAR, BIS, WorldBank, Yahoo/options, fear & greed, FedWatch, web search, FX, DBnomics, Stooq, and more.

## Capabilities Matrix

| Capability | Web | API | CLI |
|---|---|---|---|
| Market Data | `/data`, `/forecast` | `GET /api/data/*` | `kronos data fetch` |
| Kronos Forecast | `/forecast`, `/batch` | `POST /api/forecast`, `POST /api/batch` | `kronos forecast`, `kronos batch` |
| Agent Analysis | `/analysis` | `POST /api/v1/analyze/agent` | `kronos analyze agent` |
| Macroeconomic Analysis | `/macro` with `/analysis` as needed | `POST /api/v1/analyze/macro` | `kronos analyze macro` |
| Risk/Valuation/Portfolio | `/analysis` summarized view | `POST /api/v1/analyze/*` | `kronos analyze risk/dcf/portfolio` |
| Backtest | `/backtest` | `POST /api/backtest/ranking` | `kronos backtest ranking` |
| Health Check | Header status | `GET /api/health` | Access `health` after `kronos serve` |

## Quality Gates

```bash
python -m pytest tests -q

cd web
npm run typecheck
npm run lint
npm run test:frontend
npm run build
npm run check:bundle

# Run when local web is already started
npm run smoke:pages
```

## Quick Start

### Windows (recommended)

```bash
# Use the batch script (environment auto-configured)
kronos.bat forecast --symbol 600036 --pred-len 5

# Or configure manually if needed
set PYTHONPATH=src;external\Kronos
set KRONOS_REPO_PATH=external\Kronos
python scripts\win_launcher.py forecast --symbol 600036 --pred-len 5
```

### WSL/Linux

```bash
# Option 1: one-click install (recommended for pure WSL)
bash scripts/install_torch.sh
source .venv/bin/activate

# Option 2: use Windows Python from WSL (recommended if no PyTorch installation needed)
chmod +x kronos.sh
./kronos.sh forecast --symbol 600036 --pred-len 5 --sample-count 10

# Manually specify Python path if auto-detection fails
WIN_PYTHON=/mnt/c/Users/your-username/AppData/Local/Programs/Python/Python313/python.exe ./kronos.sh forecast ...
```

**How WSL works**:
- `kronos.sh` auto-detects the Windows Python path
- Converts WSL paths to Windows paths (`/mnt/e/...` -> `E:\...`)
- Calls `win_launcher.py` to configure environment variables and execute CLI
- Market data (BaoStock/Yahoo) is fetched over WSL network access

### CLI (common)

```bash
# Install
pip install -e .

# Single-asset forecast (dry-run)
kronos forecast --symbol 600036 --pred-len 5 --dry-run

# Single-asset forecast (real inference)
kronos forecast --symbol 600036 --pred-len 5

# Probabilistic forecast (Monte Carlo sampling)
kronos forecast --symbol 600036 --pred-len 5 --sample-count 10

# Batch forecast
kronos batch --symbols 600036,000858,000001 --pred-len 5

# Fetch data
kronos data fetch --symbol 600036 --start 20240101 --end 20260429

# Strategy backtest
kronos backtest ranking --symbols 600036,000858 --start 20240101 --end 20260429

# Strategy backtest with HTML report
kronos backtest ranking --symbols 600036,000858 --start 20240101 --end 20260429 --report

# AI analysis (A-shares)
kronos analyze ai-analyze --symbol 600036 --market cn

# Natural-language agent analysis
kronos analyze agent --question "Can you tell me if China Merchants Bank is a good buy now?"

# AI analysis (US stocks)
kronos analyze ai-analyze --symbol AAPL --market us

# Add alert rule
kronos alert add --type price_change --symbol 600036 --threshold 3.0

# List alert rules
kronos alert list

# Run alert check
kronos alert check

# Start continuous monitoring
kronos alert monitor --interval 5

# Start API service
kronos serve --port 8000
```

### API Service

```bash
# Start
kronos serve --host 0.0.0.0 --port 8000

# Open Swagger UI
open http://localhost:8000/docs
```

### Web Frontend

```bash
cd web
npm install
npm run dev
# Open http://localhost:3000
```

## Testing

```bash
python -m pytest tests -q
cd web && npm run typecheck && npm run lint && npm run test:frontend
cd web && npm run build && npm run check:bundle
```

## Logging and Operations

By default, logs are written to `logs/kronos-YYYYMMDD.log` and also emitted to stderr. For containerized deployments, JSON stdout is recommended and in-container file logging should be disabled. Common settings:

```bash
KRONOS_LOG_LEVEL=DEBUG
KRONOS_LOG_FORMAT=json
KRONOS_LOG_ENABLE_FILE=1
KRONOS_LOG_DIR=logs
KRONOS_LOG_RETENTION_DAYS=14
KRONOS_LOG_MAX_BYTES=10485760
```

Check logs:

```bash
# PowerShell
Get-Content logs\kronos-*.log -Tail 100

# With JSON Lines format, each line is an independent JSON object
Get-Content logs\kronos-*.log -Tail 10
```

To clean old logs, delete outdated files under `logs/` directly; the directory is already ignored by git. API error responses include `request_id`, which can be used to locate the full exception stack in logs. The frontend automatically sends `X-Request-ID`; for full end-to-end validation runs, write `kronos-test-run-id` to browser sessionStorage or set `NEXT_PUBLIC_TEST_RUN_ID` at build time so backend logs will include the matching `test_run_id`.

### Rust Native Acceleration (optional)

First-time Windows Rust setup:

```powershell
# Install Rust toolchain
Invoke-WebRequest -Uri https://win.rustup.rs/x86_64 -OutFile $env:TEMP\rustup-init.exe
& $env:TEMP\rustup-init.exe -y --profile minimal --default-host x86_64-pc-windows-gnu --default-toolchain stable-x86_64-pc-windows-gnu

# Install GNU linker (if gcc is not present)
winget install --id BrechtSanders.WinLibs.POSIX.MSVCRT -e --accept-source-agreements --accept-package-agreements --silent

# Install Python build utilities
python -m pip install maturin
```

Build and enable native extension:

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

## CLI JSON Parameters

| Field | Type | Default | Description |
|------|------|--------|-------------|
| symbol | string | required | Asset symbol |
| timeframe | string | "1d" | K-line timeframe |
| pred_len | int | required | Number of predicted K-lines |
| dry_run | bool | false | Use dry-run predictor |
| model_id | string | NeoQuasar/Kronos-base | Model ID |
| temperature | float | 1.0 | Sampling temperature |
| top_k | int | 0 | Top-k filtering |
| top_p | float | 0.9 | Nucleus sampling threshold |
| sample_count | int | 1 | Parallel sample count |

## Output Format

Successful response: `ok`, `symbol`, `timeframe`, `model_id`, `pred_len`, `forecast`, `metadata`

All prediction outputs are for research purposes only and do not constitute investment advice.
