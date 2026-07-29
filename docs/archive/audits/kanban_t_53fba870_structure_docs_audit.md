# KronosFinceptLab 项目结构与文档状态审计

> 状态：Historical / Archived
> 用途：一次性审计记录，不代表当前项目状态。
> 当前标准：以仓库根 README 和 `docs/` 当前文档为准。

任务：t_53fba870
审计范围：仓库根目录、README、docs、配置与依赖清单、脚本、主要源码目录、任务/路线图类文件。

## 1. 项目用途与核心模块判断

KronosFinceptLab 是一个 local-first 量化金融分析平台，目标是把市场数据、Kronos K 线预测、技术指标、宏观信号、AI 投研、新闻/告警、回测、自选股与 MCP 集成在同一个本地可运行系统里。

主要入口：

- Web UI：`web/`，Next.js，页面覆盖 dashboard、forecast、batch、data、analysis、macro、backtest、alerts、news、watchlist、settings。
- REST API：`src/kronos_fincept/api/app.py`，FastAPI，供 Web 和外部客户端调用。
- CLI：`src/kronos_fincept/cli/main.py` 与 `src/kronos_fincept/cli/commands/`，暴露 `kronos` 命令。
- MCP：`kronos_mcp/kronos_mcp_server.py`，把 forecast/data/analysis/jobs/alerts/watchlist 等能力暴露为 MCP tools。
- 部署：`Dockerfile`、`docker-compose.yml`、`scripts/zeabur_start.sh`、`start.bat`、`start.sh`。
- FinceptTerminal 集成：`integrations/fincept_terminal/`，含 Python bridge、C++ service 层和 Qlib adapter。

核心业务模块：

- `src/kronos_fincept/service.py`：预测服务主入口，连接 API/CLI/MCP 与 Kronos predictor。
- `src/kronos_fincept/predictor.py`：Kronos 模型加载、缓存、推理、采样相关逻辑。
- `src/kronos_fincept/data_sources/`：EastMoney、Tushare、AkShare、BaoStock、Yahoo、Stooq、TDX、TickFlow、Binance、OKX、source cache 等数据源与 fallback。
- `src/kronos_fincept/agent.py`：自然语言投研与 LLM 分析链。
- `src/kronos_fincept/macro/`：宏观信号管理与 provider。
- `src/kronos_fincept/financial/`：DCF、风险、组合、衍生品、技术指标、策略等金融分析。
- `src/kronos_fincept/api/routes/`：REST 路由。
- `web/src/lib/api.ts`：前端 API client 的核心契约点。

## 2. 目录结构说明

仓库顶层：

- `README.md`：项目总览、能力矩阵、快速启动、文档索引、配置变量、质量门禁。
- `docs/`：当前架构、API、CLI、部署、启动、Windows、Fincept 集成、历史 spec 与设计提示。
- `src/kronos_fincept/`：Python 后端与业务核心。
- `web/`：Next.js 前端，含 `package.json`、`next.config.js`、`src/app`、`src/components`、`src/lib`、`src/types`。
- `kronos_mcp/`：MCP server 与 README。
- `integrations/fincept_terminal/`：FinceptTerminal 桥接与 C++ 集成文件。
- `examples/`：请求 JSON、示例脚本、样例 OHLCV CSV。
- `scripts/`：Zeabur 启动、依赖检查、hook、torch 安装、建议预生成、Windows launcher 等脚本。
- `tests/`：后端、部署契约、前端契约、LLM/provider、数据源、Web completion 等测试。
- `data/`：预生成建议数据。
- `.cache/`、`.hermes/`、`build/`、`logs/`、`temp/`、`.pytest_cache/`、`.ruff_cache/`、`web/.next/`：本地运行/测试/构建产物或缓存，不应作为新人主要阅读入口。

关键配置与依赖文件：

- `pyproject.toml`：Python 包元数据，版本 `10.9.0`，依赖分组 `api`、`kronos`、`astock`、`cli`、`mcp`、`dev`、`deploy`、`deploy-model`。
- `requirements.txt`：扁平依赖清单，覆盖 core/API/CLI/A-stock/Kronos/dev。
- `web/package.json`：前端版本 `10.9.0`，脚本包括 `dev`、`build`、`build:zeabur`、`lint`、`typecheck`、`test:frontend`、`smoke:pages`、`check:bundle`。
- `.env.example`：配置模板；真实 `.env`、`.env.local` 存在但未读取内容。
- `Dockerfile`：前端 build、后端 build、combined runtime 三阶段镜像。
- `docker-compose.yml`：单服务 app，暴露 3000，内部 API 健康检查走 8000。

## 3. 已有文档是否足以让新人启动

结论：基本足够让有 Python/Node 经验的新人完成“本地启动与粗略理解”，但不足以让新人稳定完成“真实模型、生产部署、完整质量门禁、Fincept 集成”。

足够的部分：

- `README.md` 给出了项目用途、能力矩阵、入口、安装、CLI/API/Web、质量门禁、环境变量总览。
- `docs/START_GUIDE.md` 给出 Windows 双击、WSL/Linux、手动启动、端口、API key、低内存启动和常见故障。
- `docs/ARCHITECTURE.md` 明确当前架构边界，说明 Web/API/CLI/MCP 四入口、后端分层、数据源、宏观、前端、部署。
- `docs/API.md` 和 `docs/CLI.md` 足以让新人查 endpoint/command。
- `kronos_mcp/README.md` 足以让 MCP 客户端配置一个基础 server。

不足的部分：

- 缺少“一条命令/一组命令”的 verified onboarding 流程：例如从干净环境开始，按顺序安装 Python、Node、依赖、启动 API/Web、跑最小 smoke、跑质量门禁。
- 真实模型启动前置条件分散在 `README.md`、`docs/DEPLOYMENT.md`、`docs/WINDOWS_KRONOS_GUIDE.md`、`.env.example`，新人不容易知道何时可以 dry-run，何时需要 `KRONOS_REPO_PATH`、HF cache、外部 Kronos repo。
- `.env.example` 很完整，但缺少“最小本地开发 .env”和“真实模型 .env”的分层模板说明。
- 质量门禁文档列了命令，但没有说明当前已知失败、环境依赖、哪些属于 deploy contract、哪些属于 lint debt。
- FinceptTerminal 集成文档描述了已验证/待办，但需要外部项目编译步骤，新人无法仅靠本仓库验证闭环。

## 4. 明显缺失、过期或自相矛盾之处

### 4.1 版本说明漂移

- `pyproject.toml` 当前版本是 `10.9.0`。
- `web/package.json` 当前版本是 `10.9.0`。
- 但 `docs/ARCHITECTURE.md:249-252` 的 “Known Drift Risks” 写着 `pyproject.toml` 和 `web/package.json` 使用 `2.0.0`，部署/build metadata 可能为 `v10.8.9`。
- 这条说明已经与当前文件不一致，应更新或删除。

### 4.2 历史 spec 与当前状态并存，容易误导优先级

- `docs/spec_v109_upstream_integration.md` 和 `docs/spec_web_page_completion.md` 已标明 historical spec，并提示以 `README.md`、`docs/API.md`、`docs/CLI.md`、`docs/ARCHITECTURE.md` 为准。
- 这两个文件仍包含大量“需新增/待支持/验收”内容，适合作为历史路线图，但不适合作为当前真实状态入口。
- 建议在 README 文档索引里明确标注它们是历史 spec / archived planning，而不是当前 roadmap。

### 4.3 启动脚本文档与实际安全/环境体验存在风险

- `start.bat` 会在缺依赖时直接运行 `pip install fastapi "uvicorn[standard]" pydantic python-multipart --quiet`，这可能污染用户当前全局 Python，而不是项目 `.venv`。
- `start.sh` 输出 API docs 地址 `http://localhost:8000/docs`，但 API docs 默认关闭；虽然 `START_GUIDE.md` 解释了这一点，脚本输出仍可能误导。
- `docs/START_GUIDE.md` troubleshooting 中给出 `rm -rf node_modules package-lock.json`，对 Windows 新人不友好，也有误删 lockfile 的风险；建议改成平台化命令并强调不要随意删除 lockfile。

### 4.4 Docker/Zeabur 契约与测试存在不一致

来自当前仓库文件与近期运行验证的交叉结论：

- `Dockerfile` 当前 `KRONOS_PREWARM_ON_STARTUP=0`，但已有 Zeabur 契约测试曾期望 `KRONOS_PREWARM_ON_STARTUP=1`。
- `Dockerfile` 当前 frontend builder 使用 `npm ci --no-audit --no-fund`，测试曾期望 `npm ci --include=optional --no-audit --no-fund`。
- `Dockerfile` Stage 3 注释、git fetch 命令字符串也与测试期望有漂移。
- 这说明 deploy contract 测试与实际 Dockerfile 的目标未统一。需要产品/部署侧先决定真实期望，再同步 Dockerfile 或测试。

### 4.5 配置真实来源不够清晰

- `.env.example` 是配置参考，但 `docs/ARCHITECTURE.md` 明确提醒 runtime truth 应以 `config.py`、`agent.py`、`api/security.py` 为准。
- `src/kronos_fincept/config.py` 还包含自动读取 Hermes gateway model config 的逻辑，这属于跨项目环境耦合，对新人不是显性信息。
- 建议补一节“配置解析优先级与外部 Hermes 配置联动”，说明 env、.env、默认值、Hermes fallback 的优先级和安全边界。

### 4.6 仓库中有本地运行产物

本次审计看到以下本地产物或缓存目录：

- `build/`
- `temp/`
- `logs/`
- `.cache/`
- `.pytest_cache/`
- `.ruff_cache/`
- `web/.next/`
- `web/tsconfig.tsbuildinfo`
- `src/kronos_fincept_lab.egg-info/`

这些不一定都是错误，但会干扰新人阅读和文件搜索。`git status` 当前显示 `?? temp/`，说明至少 `temp/` 有未跟踪内容。

## 5. 后续重点关注文件或模块

建议后续优先关注：

1. `Dockerfile`、`scripts/zeabur_start.sh`、`tests/test_v1052_kronos_single_model_performance.py`、`tests/test_v1061_zeabur_npm_retry.py`、`tests/test_v89_zeabur_deploy.py`、`tests/test_v901_zeabur_runtime.py`、`tests/test_v902_zeabur_lowmem.py`
   - 目的：统一 Zeabur/Docker 真实部署策略与契约测试。

2. `README.md`、`docs/START_GUIDE.md`、`docs/DEPLOYMENT.md`
   - 目的：补一条 verified onboarding path，区分 local dry-run、local real model、Docker/Zeabur 三条路径。

3. `docs/ARCHITECTURE.md`
   - 目的：修正版本漂移说明，保持 architecture doc 与当前 `pyproject.toml` / `web/package.json` 一致。

4. `.env.example`、`src/kronos_fincept/config.py`
   - 目的：明确配置优先级、最小配置模板、真实模型配置模板，以及 Hermes 配置自动读取的边界。

5. `src/kronos_fincept/data_sources/`
   - 目的：这是 fallback、cache、circuit-breaker、stale cache 的核心，后续运行可靠性很依赖它。

6. `src/kronos_fincept/agent.py`、`src/kronos_fincept/macro/`
   - 目的：LLM 与宏观分析复杂度最高，最需要文档说明 provider 缺失时的降级行为。

7. `web/src/lib/api.ts`、`web/src/types/api.ts`、`web/src/app/*`
   - 目的：前端契约、错误提示、API key、本地状态和页面闭环都集中在这里。

8. `kronos_mcp/kronos_mcp_server.py` 与 `kronos_mcp/README.md`
   - 目的：MCP 是 agent 集成入口，应持续保证 tool 列表和 README 同步。

9. `integrations/fincept_terminal/` 与 `docs/FINCEPT_INTEGRATION.md`
   - 目的：外部桌面端集成仍有 pending 编译/注册/UI 步骤，需要单独验收。

## 6. 明确结论

- 项目当前结构不是空壳，已经是 Python 后端、Next 前端、CLI、MCP、Docker、Fincept 集成并存的完整应用型仓库。
- 文档覆盖面较好，适合后续汇总使用；但新人启动仍需要更强的“按场景分层”的 onboarding 文档。
- 当前最大的文档/配置风险不是缺文档，而是“文档、测试契约、Dockerfile、版本说明之间存在漂移”。
- 后续最应该先统一部署契约和启动路径，再处理历史 spec 与 roadmap 的归档标识。
