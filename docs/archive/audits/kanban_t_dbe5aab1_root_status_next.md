# KronosFinceptLab 当前状态与下一步建议

> 状态：Historical / Archived
> 用途：历史任务建议，不代表当前项目状态。
> 当前标准：以仓库根 README 和 `docs/` 当前文档为准。

任务：t_dbe5aab1
日期：2026-06-11

## 结论

KronosFinceptLab 当前已经是一个功能完整度较高的本地开发可运行版本，而不是空壳原型。项目具备 Web、FastAPI、CLI、MCP、Docker/Zeabur、FinceptTerminal 集成等多入口；在禁用真实 Kronos 模型和本地 API 鉴权的开发 smoke 配置下，后端 API、生产前端和页面 smoke 已验证可运行。

但它还不能被视为生产可发布版本。当前最大问题不是继续加功能，而是质量门禁与部署契约漂移：backend pytest 有 7 个已知失败，frontend contract 有 1 个失败，ruff 仍有大量既有问题，mypy/build 工具链也尚未在当前环境中复现通过。

明确建议下一步先做：P0：对齐 Docker/Zeabur 契约并修复当前 pytest 失败。

## 证据汇总

### 已确认可用

- 仓库当前分支状态：`## main...origin/main`，另有未跟踪 `temp/`。
- 环境版本：Python 3.13.6、Node v22.22.1、npm 10.9.4。
- 项目版本：Python package `10.9.0`，Web package `10.9.0`。
- CodeGraph 索引健康：242 files / 4847 nodes / 11346 edges / 10.15 MB。
- 父任务运行验证显示：
  - Python import smoke 通过。
  - CLI health 在 `KRONOS_ENABLE_REAL_MODEL=0` 下通过。
  - FastAPI `/api/health` HTTP 200。
  - Next 生产前端页面 smoke 通过。
  - 前端 typecheck、lint、build、bundle check 通过。
  - `python -m pip wheel . -w temp/wheelhouse --no-deps` 可生成 wheel。

### 当前不绿项

- `python -m pytest tests -q -o addopts=`：父任务观察到 579 passed / 6 skipped / 7 failed，命令最终因 600s timeout 标记 exit 124。
- targeted backend pytest：父任务复核仍为 7 failed / 19 passed。
- `npm run test:frontend`：本任务复核失败，错误为 `api client contract is missing: errors.apiKeyRequired`。
- `python -m ruff check src tests --statistics`：父任务记录 143 个 lint 问题。
- `python -m mypy src`：mypy 未安装。
- `python -m build --wheel --no-isolation`：build 模块未安装。
- 本任务直接运行部分 pytest 时命中环境污染：测试导入了 `E:\hermes-agent\hermes-agent\venv` 中损坏/不匹配的 pydantic_core，报 `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`。这说明后续复核应使用项目独立 venv 或执行前清理 `VIRTUAL_ENV/PYTHONPATH`，避免 Hermes 运行环境污染判断。

## 风险排序

1. 质量门禁红灯：backend pytest、frontend contract、ruff、mypy/build 仍未形成可重复全绿链路。
2. Docker/Zeabur 契约漂移：Dockerfile、Zeabur 启动脚本、部署文档和测试对预热、npm optional deps、stage 注释、git fetch 文本的期望不一致。
3. 真实模型未验收：当前 smoke 使用 `KRONOS_ENABLE_REAL_MODEL=0`；`KRONOS_REPO_PATH`、模型权重/cache、预热、资源占用未验证。
4. 生产鉴权未验收：当前 API smoke 使用 `KRONOS_AUTH_DISABLED=1`；真实 API key/admin/internal key 链路未验证。
5. 文档漂移：README/docs 覆盖面够，但版本说明、historical spec、启动脚本行为、配置来源说明需要统一。

## 下一步该做什么

### 今天

只做一件窄任务：P0：对齐 Docker/Zeabur 契约并修复当前 pytest 失败。

建议产出：

- 7 个 backend pytest 失败归因表：每一项明确是改测试、改 Dockerfile/脚本、还是改业务代码。
- 明确 Zeabur 默认 `KRONOS_PREWARM_ON_STARTUP`：建议低内存部署默认保持 `0`，除非明确追求首个预测请求低延迟并接受启动资源风险。
- 明确 Dockerfile 是否应使用 `npm ci --include=optional --no-audit --no-fund`：如果目标是跨平台 Next/SWC 可靠构建，建议恢复 `--include=optional` 并同步文档/测试。
- 给出最小 diff 方案，不要顺手做 ruff 全量清理或新功能。

验收标准：

- 当前 7 个 backend pytest 失败清零。
- Dockerfile、`scripts/zeabur_start.sh`、`docs/DEPLOYMENT.md`、相关 tests 对同一部署策略达成一致。
- 记录哪些测试是按新策略更新，哪些代码是真修复。

### 三天内

- 修复 `npm run test:frontend` 的 `errors.apiKeyRequired` contract 漂移。
- 补齐 dev/build 工具链：`build`、`mypy`，并明确项目独立 venv/uv 流程。
- 重跑并记录 targeted pytest、full pytest、frontend contract、typecheck、lint、build。

### 一周内

- 写 verified onboarding path，区分最小本地 dry-run、真实模型、本地/Zeabur 部署三条路径。
- 修正文档漂移：ARCHITECTURE 版本说明、README historical spec 标识、配置解析优先级。
- 建立真实模型与生产鉴权验收清单；等环境/密钥就绪后再跑 real-model 和 production-auth smoke。
- 等质量门禁恢复后，再进入 v11 功能增强，例如后端化批量任务、批量数据接口、宏观 provider 状态面板、模型运行时管理。

## 不建议现在做的事

- 不建议继续加大功能。
- 不建议做 ruff 全量清理作为第一步。
- 不建议在当前被 Hermes venv 污染的 Python 环境中直接声明质量结果。
- 不建议在未裁决 Zeabur 预热/optional deps 策略前盲改 Dockerfile 或测试。
