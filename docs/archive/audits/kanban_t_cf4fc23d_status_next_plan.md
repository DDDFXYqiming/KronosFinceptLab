# KronosFinceptLab 当前状态与下一步计划

> 状态：Historical / Archived
> 用途：历史任务状态与计划，不代表当前路线图。
> 当前标准：以仓库根 README 和 `docs/` 当前文档为准。

任务：t_cf4fc23d
日期：2026-06-11
依据：

- 结构与文档审计：t_53fba870，报告 `temp/kanban_t_53fba870_structure_docs_audit.md`
- 运行与质量验证：t_0200402c，看板 handoff metadata
- 当前仓库状态：`git status --short --branch` 返回 `## main...origin/main`，另有未跟踪 `temp/`
- CodeGraph 索引：242 files / 4847 nodes / 11346 edges / 10.15 MB

## 0. 一句话结论

KronosFinceptLab 当前不是空壳，已经是一个 Web/API/CLI/MCP/Docker/Fincept 多入口的本地量化金融应用；它已经可以在“禁用真实 Kronos 模型、禁用本地 API 鉴权”的本地开发模式下安装、构建、启动和通过页面 smoke，但还不能视为生产可发布版本。

当前最应该先做的不是继续加新功能，而是先做一轮 P0 稳定化：统一 Docker/Zeabur 契约与测试，修掉当前 7 个 pytest 失败和 1 个前端契约失败，把质量门禁恢复到可重复全绿。

## 1. 当前项目成熟度判断

建议定位：功能完整度较高的本地开发可运行版本，处于“集成稳定化 / pre-release hardening”阶段。

成熟度分层判断：

| 维度 | 当前判断 | 依据 |
|---|---|---|
| 功能完整度 | 高 | 已有 Web、FastAPI、CLI、MCP、Docker、Fincept 集成入口；页面覆盖 forecast、analysis、batch、data、backtest、watchlist 等核心场景。 |
| 本地可运行性 | 中高 | 后端 API、生产前端和页面 smoke 均已跑通；Python import smoke 与 CLI health smoke 成功。 |
| 文档覆盖 | 中高 | README、START_GUIDE、ARCHITECTURE、API、CLI、DEPLOYMENT 基本齐全；但 onboarding 路径和当前质量状态不够明确。 |
| 自动化质量 | 中低 | 前端 typecheck/lint/build 通过；但 pytest 仍有 7 个失败，frontend contract 有 1 个失败，ruff 有 143 个问题，mypy/build 模块缺失。 |
| 生产部署就绪度 | 低到中 | Docker/Zeabur 契约测试与 Dockerfile 当前内容不一致；真实模型、真实密钥、生产鉴权链路未验证。 |
| 新人可接手性 | 中 | 文件和文档足够理解项目，但历史 spec、版本漂移、启动脚本行为和配置来源会误导新人。 |

综合判断：项目已经跨过“原型”阶段，但还没进入“可稳定交付/部署”阶段。当前核心任务是把工程契约、测试和文档重新对齐。

## 2. 已完成 / 当前可用部分

### 2.1 可用入口

- Web UI：`web/`，Next.js 生产构建通过，页面 smoke 通过。
- REST API：`src/kronos_fincept/api/app.py`，FastAPI 可启动，`/api/health` 返回 HTTP 200。
- CLI：`src/kronos_fincept/cli/main.py` 可导入，health 命令在模型禁用模式下返回 ok。
- MCP：`kronos_mcp/kronos_mcp_server.py` 与 README 存在，作为 agent 集成入口已成形。
- Docker/Zeabur：有 Dockerfile、docker-compose、Zeabur 启动脚本，但契约需重对齐。
- FinceptTerminal 集成：有 bridge、C++ service、Qlib adapter 和文档，但外部闭环未在本轮验证。

### 2.2 已验证通过的运行能力

已通过：

- Python/Node 环境可用：Python 3.13.6、pip 25.2、Node v22.22.1、npm 10.9.4。
- Python 关键模块导入成功：`kronos_fincept`、`kronos_fincept.api.app`、`kronos_fincept.cli.main`、FastAPI、pandas、numpy。
- 后端以开发 smoke 配置启动成功：
  - `KRONOS_AUTH_DISABLED=1`
  - `KRONOS_ENABLE_API_DOCS=1`
  - `KRONOS_PREWARM_ON_STARTUP=0`
  - `KRONOS_ENABLE_REAL_MODEL=0`
- `/api/health` 返回 HTTP 200。
- Next 生产前端启动成功。
- 页面 smoke 通过：`/`、`/forecast`、`/analysis`、`/batch`、`/backtest`、`/data`、`/watchlist`、`/api/health` 均 HTTP 200。
- 前端质量命令通过：
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`
  - `npm run check:bundle`
- Python wheel 可通过 `python -m pip wheel . -w temp/wheelhouse --no-deps` 生成。

### 2.3 文档可用部分

- `README.md` 能说明项目目标、入口、能力矩阵和基本启动。
- `docs/START_GUIDE.md` 能支持 Windows / WSL / Linux 的基础启动。
- `docs/API.md`、`docs/CLI.md` 可作为 endpoint/command 查询入口。
- `docs/ARCHITECTURE.md` 说明了 Web/API/CLI/MCP 等主要边界。
- `kronos_mcp/README.md` 足以让 MCP 客户端做基础配置。

## 3. 最大风险与阻塞点

### R1. 质量门禁没有全绿，是当前最大阻塞

当前完整质量状态不是 green：

- `python -m pytest tests -q -o addopts=`：观察到 579 passed / 6 skipped / 7 failed；命令最终因 600s timeout 标记 exit 124。
- targeted pytest 复核：同样 7 个失败，19 passed。
- `npm run test:frontend`：1 个 contract 失败，缺 `errors.apiKeyRequired`。
- `python -m ruff check src tests --statistics`：143 个 lint 问题。
- `python -m mypy src`：mypy 未安装。
- `python -m build --wheel --no-isolation`：build 模块未安装。

影响：无法可靠声明“当前主分支质量可发布”，也不适合直接继续叠大功能。

### R2. Docker/Zeabur 真实部署策略与测试契约漂移

7 个 pytest 失败中，多数集中在 Dockerfile/Zeabur 契约：

- `KRONOS_PREWARM_ON_STARTUP` 测试期望与 Dockerfile 当前值不一致。
- `npm ci --include=optional --no-audit --no-fund` 期望与当前 Dockerfile 不一致。
- Stage comment、git fetch command 字符串与测试期望不一致。

这类问题不能盲改。需要先决定“真实期望”：是以当前低内存部署策略为准，还是恢复测试中旧契约。决定后再同步 Dockerfile、Zeabur 脚本、部署文档和测试。

### R3. 真实模型 / 真实外部服务没有完成验收

本轮 smoke 明确禁用了真实模型：`KRONOS_ENABLE_REAL_MODEL=0`。

未验证：

- `KRONOS_REPO_PATH` / external Kronos code。
- 模型权重、HF cache、模型预热。
- LLM provider、Tushare、FRED、Web Search 等真实外部服务。
- 生产 API 鉴权：本轮 API smoke 使用 `KRONOS_AUTH_DISABLED=1`。

影响：当前只能声明“本地开发 dry-run / smoke 可用”，不能声明“真实投研生产能力完整可用”。

### R4. 文档不是缺，而是容易误导

明显漂移点：

- `docs/ARCHITECTURE.md` 的 Known Drift Risks 仍提旧版本信息，但当前 `pyproject.toml` 与 `web/package.json` 是 10.9.0。
- `docs/spec_*` 已标 historical，但仍容易被当作当前路线图。
- README/docs 缺少 verified onboarding path 和当前质量门禁状态说明。
- `.env.example` 完整但不分层，新人不容易区分最小本地开发、真实模型、生产部署三类配置。
- `start.bat` 缺依赖时可能安装到当前 Python，而不是项目 venv。

### R5. 当前 Python 环境存在全局依赖冲突

`python -m pip check` 报告了与 Hermes、flask-limiter、torch/setuptools 相关的环境冲突。虽然不一定全部属于 Kronos 项目本身，但它会污染“可复现安装/构建”的判断。

建议后续用项目独立 `.venv` 或明确的 uv/venv 流程重跑质量门禁，避免全局环境误差。

## 4. 下一步任务清单（按优先级）

### P0-1. 统一 Docker/Zeabur 契约并修复 7 个 pytest 失败

目标：让部署契约测试与真实部署策略一致。

建议动作：

1. 逐个确认 7 个失败中哪些应改测试、哪些应改 Dockerfile/脚本。
2. 如果低内存 Zeabur 策略以当前 Dockerfile 为准：更新旧测试期望。
3. 如果测试期望是正确产品策略：更新 Dockerfile/Zeabur 脚本。
4. 同步 `docs/DEPLOYMENT.md` 和 `docs/START_GUIDE.md`。
5. 重跑 targeted pytest，再跑完整 pytest。

验收标准：

- 当前 7 个 pytest 失败清零。
- Docker/Zeabur 策略在 Dockerfile、scripts、docs、tests 四处一致。

### P0-2. 修复前端 API contract 失败

当前失败：`web/src/lib/api.ts` contract scan 缺 `errors.apiKeyRequired`。

建议动作：

1. 检查 `web/src/lib/api.ts` 与前端 contract 测试期望。
2. 决定 `apiKeyRequired` 是否仍是当前 API 错误契约。
3. 若是：补回错误码/错误映射。
4. 若不是：更新 contract 测试和文档。

验收标准：

- `npm run test:frontend` 通过。
- 前端 API 错误提示与后端认证策略一致。

### P0-3. 固定质量工具链，使质量门禁可复现

建议动作：

1. 在 dev extra 或本地 dev bootstrap 中确保 `build`、`mypy` 可用。
2. 明确推荐使用项目独立 `.venv`，不要混用全局 Python。
3. 重新跑：
   - `python -m build --wheel --no-isolation`
   - `python -m mypy src`
   - `python -m pytest tests -q -o addopts=`
4. 将当前已知 ruff 问题分为“必须清理”和“暂时接受/配置忽略”。

验收标准：

- build/mypy 命令不再因为模块缺失失败。
- README 或 START_GUIDE 明确质量门禁命令和预期状态。

### P1-1. 写一条 verified onboarding path

目标：让新人从干净机器到本地 smoke 有明确路径。

建议分三条路径：

1. 最小本地开发：模型禁用、鉴权禁用、跑 API/Web smoke。
2. 真实模型本地运行：配置 `KRONOS_REPO_PATH`、模型 cache、预热策略。
3. Docker/Zeabur 部署：低内存策略、端口、API key、内部代理。

验收标准：

- 新人按文档可复现：安装依赖、启动 API、启动 Web、跑 smoke。
- 文档明确哪些密钥可选、哪些能力需要真实密钥。
- 文档明确当前质量门禁是否全绿，以及失败时如何判断。

### P1-2. 清理文档漂移与历史 spec 入口

建议动作：

1. 修正 `docs/ARCHITECTURE.md` 的版本漂移说明。
2. 在 README 文档索引中标注 `docs/spec_*` 为 historical/archived planning。
3. 增加“当前 roadmap / 下一步计划”入口，避免历史 spec 被误认为当前任务。
4. 补“配置解析优先级”：env、`.env`、默认值、Hermes fallback 的边界。

验收标准：

- README、ARCHITECTURE、DEPLOYMENT、START_GUIDE 对版本、部署策略和配置来源说法一致。

### P1-3. 建立真实模型与生产鉴权验收清单

建议动作：

1. 明确真实模型所需目录、依赖、显存/内存、cache 和启动变量。
2. 明确生产 API keys / admin/internal keys 的配置方式。
3. 做一次不泄露密钥的配置 presence check。
4. 在真实模型可用环境中跑 API health、forecast smoke、Web forecast smoke。

验收标准：

- 可以明确区分：dry-run green、real-model green、production-auth green。

### P2. 在质量稳定后再推进功能增强

建议排序：

1. 后端化批量股票池任务：`POST /api/jobs/batch`、任务进度、失败重试、后端缓存复用。
2. 市场数据批量接口与预热：`POST /api/data/batch`、`POST /api/data/prewarm`。
3. 宏观 provider 状态面板：展示 provider 延迟、cache、suspend、最近错误。
4. 模型运行时管理：prewarm、cache stats、clear-cache、diagnostics。
5. `agent.py` 模块化拆分：intent/evidence/llm_router/report/tools/prompts。

注意：这些应放在 P0/P1 稳定化之后，否则会把已有质量债继续放大。

## 5. 建议短期里程碑

### 今天应该完成

目标：先把“下一步先做什么”落地为一个窄任务。

建议今天只做一件事：P0-1 Docker/Zeabur 契约裁决与 7 个 pytest 失败归因。

具体产出：

- 一张 7 个 pytest 失败的归因表：改测试 / 改 Dockerfile / 改业务代码。
- 明确 `KRONOS_PREWARM_ON_STARTUP` 在 Zeabur 默认应为 0 还是 1。
- 明确 `npm ci --include=optional --no-audit --no-fund` 是否为当前必须策略。
- 给出最小 diff 方案。

不要今天同时做 ruff 全量清理和新功能开发。

### 三天内应该完成

目标：恢复主要质量门禁。

建议完成：

1. 修复或更新 7 个 pytest 失败。
2. 修复 `npm run test:frontend` contract 失败。
3. 补齐 `build` / `mypy` 工具链或在文档中明确安装路径。
4. 重跑并记录：
   - targeted pytest
   - full pytest
   - `npm run test:frontend`
   - `npm run typecheck`
   - `npm run lint`
   - `npm run build`

三天内不建议推进大功能，除非质量门禁已恢复。

### 一周内应该完成

目标：把项目恢复到“新人可启动、负责人可判断、后续可开发”的稳定状态。

建议完成：

1. Verified onboarding 文档。
2. Docker/Zeabur 部署文档与测试契约一致。
3. ARCHITECTURE 版本漂移修正。
4. README 标注 historical spec 与当前 roadmap。
5. 真实模型 / 生产鉴权验收清单完成；如果用户提供环境，再跑 real-model smoke。
6. 决定 v11.0 是否以“后端化批量任务 + 数据批量接口”为主线。

## 6. 需要用户补充的信息

目前不需要用户立刻补充密钥才能继续 P0 修复，因为 P0 主要是契约、测试和文档对齐。

但以下决策最终需要项目负责人确认：

1. Zeabur 默认是否应该启动预热：`KRONOS_PREWARM_ON_STARTUP=0` 还是 `1`？
   - 如果目标是低内存稳定启动，建议保持 0，并更新旧测试。
   - 如果目标是首个预测请求低延迟，才考虑 1，但要接受启动内存/耗时风险。
2. Dockerfile 中 `npm ci --include=optional` 是否必须？
   - 如果 Next/SWC 或平台 optional deps 需要它，建议加入。
   - 如果当前环境不需要，应更新测试说明原因。
3. 是否近期要验收真实 Kronos 模型？
   - 如果要，需要提供或确认 `KRONOS_REPO_PATH`、模型权重/cache、机器资源。
4. 生产 API 鉴权策略是否已经确定？
   - 如果确定，需要用真实 API keys 做一次不泄露密钥的 auth smoke。
5. v11.0 的主线是否采用“批量/任务/数据性能增强”？
   - 如果确认，建议质量门禁恢复后立即开 v11.0 规划任务。

## 7. 明确推荐：下一步先做什么

先做 P0-1：统一 Docker/Zeabur 契约并修复 7 个 pytest 失败。

原因：

- 这是当前 full pytest 不绿的主要来源。
- 它影响部署可信度和文档可信度。
- 它是“改测试还是改部署策略”的产品/工程边界问题，不先裁决，后面所有部署文档和 onboarding 都会继续漂移。
- 修完后，再处理前端 contract、工具链、文档，路径最短、收益最大。

推荐的第一张后续工单标题：

`P0: 对齐 Docker/Zeabur 契约并修复当前 pytest 失败`

验收标准：

- 7 个 backend pytest 失败清零。
- Dockerfile、scripts/zeabur_start.sh、docs/DEPLOYMENT.md、相关 tests 对同一部署策略达成一致。
- 完整记录哪些测试是按新策略更新的，哪些代码是真修复。
