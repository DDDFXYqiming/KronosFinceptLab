# KronosFinceptLab Web 页面补完 Spec

> 日期：2026-05-09
> 范围：除已重点完善的「预测 / 分析 / 宏观洞察」外，补齐仪表盘、自选股、批量对比、回测、数据、设置/监控等页面的产品功能闭环。
> 原则：优先复用现有后端能力，不新增重型依赖；先做“能用、可验证、可导出”，再做高级量化能力。
> 三模同步：Web、API、CLI 尽可能保持参数、导出、告警与诊断能力一致；若后端暂不支持，Web 端必须明确标注“待支持”。

---

## 1. 当前现状

| 页面 | 当前能力 | 主要缺口 |
|---|---|---|
| 仪表盘 `/` | 展示 API 状态、版本、模型、设备、运行时间；展示本地自选股；快捷入口仅含预测/分析/批量对比 | 没有项目总览、最近任务、数据源/LLM 状态、完整页面入口；自选股没有行情摘要 |
| 自选股 `/watchlist` | 本地添加/移除标的；支持市场字段；可跳转分析/预测 | 只是本地列表，缺少价格、涨跌、指标、批量操作、告警、分组/备注、导入导出 |
| 批量对比 `/batch` | 多标的拉取行情后调用 `/batch`；有限并发、取消、进度、失败重试、收益率排名图表 | 缺少股票池管理、筛选条件、导出、添加到自选/回测、风险/置信度列、历史结果 |
| 回测 `/backtest` | 调用 `/backtest/ranking`；配置 symbols/start/end/top_k；展示总收益、夏普、最大回撤、胜率、权益曲线 | 后端已有 window/pred_len/step/report/benchmark 等能力但前端没暴露；缺少交易明细、持仓、基准对比、费用滑点、报告导出 |
| 数据 `/data` | A 股搜索；A 股 K 线拉取；表格展示 OHLCV | 后端已支持 global data 与 technical indicators，但页面固定 A 股；缺少市场选择、复权选择、图表、指标、导出、跳转下游分析 |
| 设置 `/settings` | 当前直接 redirect 到首页 | 没有运行配置、模型/LLM 状态、缓存管理、主题偏好、诊断入口 |
| 告警/监控 | 后端已有 `/api/alert/*` | 前端没有入口，无法管理规则或手动检查 |

---

## 2. P0：最小闭环补完

### 2.1 回测页增强

目标：让截图里的「策略回测」从简单按钮页变成可复盘、可导出的研究页面。

前端改动：
- 文件：`web/src/app/backtest/page.tsx`
- 新增参数：
  - `pred_len`：预测步长，默认 5
  - `window_size`：历史窗口，默认 120
  - `step`：调仓周期，默认等于 pred_len
  - `initial_equity`：初始资金，默认 100000（若后端暂未支持，前端先展示为说明项）
  - `benchmark`：基准代码，默认空，可选沪深300/上证指数等
  - `fee_bps`、`slippage_bps`：先作为 UI 预留，后端未实现前禁用或标注“待支持”
- 新增结果区：
  - 指标卡补充：年化收益、交易次数、平均持仓天数
  - 权益曲线下方展示每期 `selected` 持仓列表
  - 新增“生成 HTML 报告”按钮，调用后端 `/backtest/report`
  - 支持下载报告 HTML / 下载 equity_curve CSV

后端/类型改动：
- 文件：`web/src/lib/api.ts`
  - 新增 `api.backtestReport(...)`
- 文件：`web/src/types/api.ts`
  - 增加 `BacktestReportResponse` 类型
  - `BacktestResponse` 补齐 `start_date/end_date/top_k` 可选字段

验收：
- 输入 `600036,000858` 能正常回测并显示完整指标。
- 点击“生成 HTML 报告”能拿到 `filename` 和 HTML 内容。
- CSV 导出包含 `date,equity,return,selected`。
- 参数为空/日期格式错误时前端直接提示，不发起无效请求。

### 2.2 数据页增强

目标：让数据页成为所有页面的数据入口，而不是只能看 A 股表格。

前端改动：
- 文件：`web/src/app/data/page.tsx`
- 新增字段：
  - 市场选择：A 股 / 美股 / 港股 / 商品
  - A 股复权：前复权 qfq / 后复权 hfq / 不复权
  - 日期快捷项：近 3 月 / 近 1 年 / 自定义
- 根据市场调用：
  - A 股：`api.getData(symbol, startDate, endDate)`
  - 非 A 股：`api.getGlobalData(symbol, market, startDate, endDate)`
- 新增展示：
  - K 线/收盘价轻量图表
  - 数据摘要：行数、起止日期、最新收盘、最新成交量
  - 技术指标卡：调用 `api.getIndicators(symbol, market)`，展示 RSI、MACD、布林带、均线等核心字段
- 新增操作：
  - 跳转预测：`/forecast?symbol=...&market=...`
  - 跳转分析：`/analysis?symbol=...&market=...`
  - 加入自选股
  - 导出 CSV

验收：
- A 股和美股/港股至少各能走到不同 API 分支。
- 指标接口失败时只影响指标区，不清空行情表格。
- 表格、图表、导出使用同一份 rows，避免数据不一致。

### 2.3 自选股增强

目标：把自选股从“收藏夹”升级成“研究工作台”。

前端改动：
- 文件：`web/src/app/watchlist/page.tsx`
- 新增字段：
  - 名称/备注/标签
  - 最新价、涨跌幅、更新时间（从 data 或 indicator 接口取最近一条）
  - 指标摘要：RSI、MACD 趋势、波动提示
- 新增操作：
  - 批量预测所选
  - 批量分析所选
  - 用所选标的进入回测页
  - 一键加入批量对比输入
  - 导入/导出 watchlist JSON
- 本地状态继续复用 `useAppStore`，暂不做登录账号体系。

验收：
- 页面刷新后自选股仍保留。
- 单个行情摘要失败不影响整个列表。
- 选择 2 个以上标的时显示“批量对比 / 回测”操作。

---

## 3. P1：体验与研究效率提升

### 3.1 批量对比增强

目标：让批量页从“预测收益排名”变成“股票池快速筛选器”。

新增功能：
- 股票池预设：自选股、常用 A 股组合、手动粘贴。
- 结果表增加：市场、预测耗时、风险标签、失败原因、操作列。
- 操作列：分析、预测、加入自选、加入回测。
- 支持导出排名 CSV。
- 支持按预测收益率、最新价、失败状态排序。
- 支持仅重试失败项，保留成功项。

验收：
- 从自选股跳入批量页时，自动填充 symbols。
- 导出 CSV 包含 rank/symbol/last_close/predicted_close/predicted_return。

### 3.2 仪表盘增强

目标：用户打开首页就知道系统能不能用、最近做了什么、下一步该点哪里。

新增功能：
- 状态面板：API、Kronos 模型、LLM、宏观 provider、数据源可用性。
- 最近结果：最近一次预测、分析、回测、批量对比（来自 sessionStorage / React Query cache）。
- 完整快捷入口：预测、分析、宏观洞察、自选股、批量对比、回测、数据、设置。
- 自选股 mini 行情：显示前 5 个自选股的最新价/涨跌。

验收：
- API 离线时首页能展示离线状态和重试按钮。
- 快捷入口覆盖侧边栏所有主要页面。

### 3.3 设置/诊断页

目标：把当前 redirect 的 `/settings` 做成只读诊断与偏好页，避免用户猜线上配置。

新增功能：
- 运行信息：版本、commit、build source、运行时间、设备、模型 ID。
- LLM 状态：展示“已配置/未配置”和当前 provider/model 的脱敏信息；不展示 API Key。
- 缓存操作：清空本地 session state、清空 React Query cache、导出本地状态。
- UI 偏好：主题、默认市场、默认日期区间、默认 pred_len。
- 诊断工具：复制 health JSON、复制最近 request_id。

安全要求：
- 禁止在前端展示密钥原文。
- 配置修改只做本地偏好，不直接写服务器环境变量。

验收：
- `/settings` 不再 redirect。
- health 信息缺字段时页面不报错。
- 清空本地缓存后预测/回测/数据页恢复默认输入。

---

## 4. P2：新增告警/监控入口

目标：复用现有 `/api/alert/*` 后端，为自选股提供研究告警。

新增页面或入口：
- 建议路径：`/alerts`，也可以先嵌入 `/watchlist`。
- API：
  - `GET /api/alert/rules`
  - `POST /api/alert/rules`
  - `DELETE /api/alert/rules/{rule_id}`
  - `POST /api/alert/check`
- 支持规则类型：
  - price_above / price_below
  - price_change
  - rsi_overbought / rsi_oversold
  - macd_crossover
  - volume_spike
  - prediction_deviation

验收：
- 能创建、查看、删除规则。
- 手动检查能展示 triggered events。
- webhook/email 字段必须默认隐藏，输入后也不在列表明文展示完整值。

---

## 5. 跨页面统一要求

- 统一 symbol/market 传参：所有跳转都保留 `symbol` 与 `market` query。
- 统一日期校验：YYYYMMDD，开始日期不得晚于结束日期。
- 统一错误展示：显示用户可读错误 + request_id。
- 统一导出：CSV 文件名包含页面、symbol(s)、日期。
- 统一免责声明：所有预测/分析/回测结果保留“仅供研究，不构成投资建议”。
- 避免重复请求：继续复用 React Query cache 和 `useSessionState`。

---

## 6. 建议实施顺序

1. 回测页：暴露已有后端能力 + 报告导出，价值最高。
2. 数据页：接入 global data 和 indicators，成为统一数据入口。
3. 自选股：增加行情摘要与批量操作，串联预测/分析/回测。
4. 批量对比：加入导出、排序、跳转和股票池预设。
5. 仪表盘：补总览、最近结果、完整入口。
6. 设置页：做只读诊断和本地偏好。
7. 告警页：复用现有 alert API，作为后续增强。
