# KronosFinceptLab 需求与实现说明

> 当前定位：独立的 Python + Rust + Web 金融量化分析平台，围绕 Kronos K 线基础模型、市场数据适配、量化分析、AI 投资顾问、宏观信号和 Web/CLI/MCP 多入口提供本地或云端分析能力。

**项目路径**：`/mnt/e/AI_Projects/KronosFinceptLab`

---

## 1. 产品范围

### 1.1 核心使用场景

1. 用户输入股票、指数、商品、加密货币等标的，获取行情、预测、技术指标和风险分析。
2. 系统通过 BaoStock、Yahoo Finance、Binance、OKX、AkShare 等数据源拉取或降级获取 OHLCV 数据。
3. 系统调用 Kronos 模型或规则/统计方法生成 K 线预测、概率预测和批量分析。
4. 用户通过 CLI、FastAPI、Next.js Web、MCP 或 Hermes Agent 入口使用同一分析能力。
5. 可选 LLM 对分析结果进行自然语言解释、投资顾问式问答和报告生成。
6. 宏观信号层聚合利率、CFTC、链上、SEC/EDGAR、BIS、WorldBank、预测市场等 provider 输出。

### 1.2 项目边界

- 本项目是研究与辅助分析工具，不构成投资建议。
- 模型预测和 LLM 解释均应与数据来源、失败降级和不确定性一起呈现。
- `external/FinceptTerminal/` 是参考/外部集成目录，不是核心业务代码的唯一事实来源。
- `secrets/`、`.env`、日志、缓存、上传文件和本地模型缓存不得提交。

---

## 2. 技术架构

| 层 | 技术 |
|---|---|
| 后端/API | Python 3.11+、FastAPI、Pydantic、uvicorn |
| CLI | Click、Rich |
| 前端 | Next.js、Tailwind CSS、Framer Motion、TradingView Lightweight Charts |
| 模型 | Kronos base/mini、HuggingFace Hub、PyTorch、safetensors |
| Rust 加速 | Cargo workspace、PyO3、maturin |
| 数据处理 | pandas、numpy、scipy |
| 数据源 | BaoStock、AkShare、Yahoo Finance、Binance、OKX、巨潮资讯等 |
| LLM | OpenAI/OpenRouter/DeepSeek 等兼容接口，支持 provider 降级 |
| MCP/Agent | MCP server、Hermes 远程调用脚本、自动化任务 |
| 部署 | Docker、docker-compose、Zeabur/本地双路径 |

---

## 3. 目录与模块说明

| 路径 | 职责 |
|---|---|
| `src/kronos_fincept/` | Python 核心包，承载 schema、数据源、分析服务、API/CLI 共享逻辑 |
| `src/kronos_fincept/api/` | FastAPI 路由、请求响应模型、健康检查和 Web 后端接口 |
| `src/kronos_fincept/cli/` | Click CLI 命令入口 |
| `src/kronos_fincept/data/` | 行情数据适配器、缓存和 provider 降级 |
| `src/kronos_fincept/kronos/` | Kronos 模型加载、预测、tokenizer 与推理封装 |
| `src/kronos_fincept/analysis/` | 技术指标、策略、风险、估值、组合、衍生品等分析逻辑 |
| `src/kronos_fincept/llm/` | LLM provider、上下文预算、fallback、报告解释和 Agent 问答 |
| `src/kronos_fincept/macro/` | 宏观 provider、统一信号、MacroDataManager 和缓存 |
| `kronos_mcp/` | MCP server 与工具暴露 |
| `web/` | Next.js 前端应用 |
| `crates/kronos-kernel/` | Rust 核心计算库 |
| `crates/kronos-python/` | PyO3/maturin Python 扩展 |
| `docs/` | API、CLI、部署、集成和架构文档 |
| `examples/` | 批量预测、真实数据预测、回测等示例请求和脚本 |
| `scripts/` | 启动、验证、部署、数据检查等辅助脚本 |
| `automations/` | 自动化任务与监控脚本 |
| `integrations/` | 外部系统集成代码 |
| `tests/` | 单元、集成、API、Web 契约和可选模型 smoke 测试 |
| `external/` | 上游参考/外部项目资料 |

---

## 4. 当前功能行为

### 4.1 市场数据

- 支持 A 股、港股、美股、商品、全球股票、加密货币等多市场标的。
- 支持多数据源自动降级。
- 支持官方披露和宏观 provider 的异步聚合。

### 4.2 预测与量化分析

- 支持 Kronos 模型 K 线预测。
- 支持批量预测、概率预测和多标的分析。
- 支持 SMA、EMA、RSI、MACD、Bollinger、KDJ、ATR、OBV 等技术指标。
- 支持策略回测、DCF、风险分析、组合优化和衍生品定价。

### 4.3 AI 投资顾问

- 支持自然语言股票分析、投资建议式报告、风险评估和上下文问答。
- 支持网页检索 provider 和公开信息补充。
- 支持 LLM 上下文预算治理，避免把全量原始序列塞入模型。
- LLM provider 失败时应保留可观测元数据并降级。

### 4.4 Web 产品化

- Next.js Web 提供分析输入、图表、结果展示、告警、自选股、批量分析和 Agent 交互页面。
- 前端通过内部 API 访问 FastAPI 后端。
- 移动端和部署场景使用同一后端能力。

### 4.5 CLI / MCP / Agent

- CLI 适合本地批处理和脚本化分析。
- MCP server 向智能体暴露可调用工具。
- Hermes 相关脚本支持远程调用、自动化和报告推送工作流。

### 4.6 LLM 性能与超时

- 宏观分析报告 DeepSeek 超时从 25s 提升到 35s（`WEB_MACRO_REPORT_PROVIDER_TIMEOUTS_SECONDS`），与单 provider 超时对齐。
- 所有 LLM 调用（DeepSeek/OpenRouter/AI 投资顾问）统一关闭思考模式（`thinking: disabled`），减少隐藏推理 token 的延迟和费用。
- URL 构造 `_build_chat_completions_url` 同时兼容基础 URL（`https://api.deepseek.com`）和完整端点（`https://api.deepseek.com/chat/completions`）两种 `.env` 配置格式。

### 4.7 Web 前端设计系统

- 基于 Minimalist Modern 设计规范：纯白卡片（`#FFFFFF`）、电光蓝渐变强调（`#0052FF → #4D7CFF`）、双字体排版（Calistoga 标题 + Inter 正文 + JetBrains Mono 代码）。
- 统一 10 个页面的 SectionLabel（中性色 pill badge + 蓝色圆点）+ page-title 层级。
- Card 组件集成 framer-motion 入场动画：fadeInUp + stagger 容器，可选 `featured` 渐变边框。
- 移动端（≤767px）隐藏自定义滚动条，桌面端保留 6px 灰色滚动条。
- 全局禁止 emoji 装饰，错误/空状态使用 SVG 图标。

### 4.8 动态建议按钮

- 分析和宏观洞察页面的示例问题按钮不再硬编码，改为通过 `GET /api/v1/suggestions?type=analysis|macro` 每 8 小时自动调用 LLM 生成。
- 三层多样性保障：随机风味注入（12 种分析方向 + 12 种宏观方向）、历史去重（最近 3 次生成，重叠 >50% 重试）、最多 3 次重试循环。
- 生成结果经 scope 正则校验（`ALLOWED_SCOPE_PATTERNS` / `MACRO_ALLOWED_PATTERNS`）+ prompt 注入检测，不合格直接丢弃。
- 服务端内存缓存 8h + 客户端 sessionStorage 缓存 8h，LLM 调用失败自动回退硬编码默认值。

---

## 5. 运行方式

安装 Python 依赖：

```bash
cd /mnt/e/AI_Projects/KronosFinceptLab
python -m venv .venv
.venv/bin/python -m pip install -e .[dev,api,cli,deploy]
```

启动后端 API：

```bash
cd /mnt/e/AI_Projects/KronosFinceptLab
.venv/bin/python -m uvicorn kronos_fincept.api.main:app --host 0.0.0.0 --port 8000
```

启动前端：

```bash
cd /mnt/e/AI_Projects/KronosFinceptLab/web
npm install
npm run dev
```

常用验证：

```bash
cd /mnt/e/AI_Projects/KronosFinceptLab
.venv/bin/python -m pytest -q

cd /mnt/e/AI_Projects/KronosFinceptLab/web
npm run lint
npm run build
```

Docker：

```bash
cd /mnt/e/AI_Projects/KronosFinceptLab
docker compose up --build
```

---

## 6. 配置与凭据

常见配置来源：

| 文件/变量 | 用途 |
|---|---|
| `.env` | 本地 API Key、模型、数据源、LLM provider 配置 |
| `.env.example` | 示例配置模板 |
| `config.toml` | 项目默认配置 |
| `KRONOS_MODEL_ID` | Kronos 模型 ID |
| `KRONOS_DEVICE` | 推理设备，默认可为 CPU |
| `PORT` / `API_PORT` | Web/API 端口 |
| `INTERNAL_API_URL` | 前端服务访问后端的内部地址 |

安全规则：真实 API Key、token、cookies、secrets、`.env` 和 `secrets/` 目录不得提交或写入文档。

---

## 7. 当前验证基线

推荐验证顺序：

1. `git status --short --branch` 检查本地改动和高风险未跟踪目录。
2. Python focused tests 或全量 `pytest`。
3. Web lint/build。
4. API 健康检查。
5. 如启用真实模型，单独跑可选 Kronos smoke test，并把模型/torch 导入失败归类为环境问题。

WSL/Windows 挂载目录中出现大量 Git 修改时，先用 `git diff --ignore-space-at-eol` 判断是否只是 CRLF/LF 噪声，不要直接重置用户改动。
