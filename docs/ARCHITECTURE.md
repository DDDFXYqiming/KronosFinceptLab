# KronosFinceptLab 架构文档

> 本文档基于当前代码库（v11 数据源与服务面对齐后）编写，聚焦已实现架构而非历史设计意图。

---

## 导航

- [← 返回 README](../README.md)
- [→ API 接口文档](API.md)
- [→ CLI 命令文档](CLI.md)
- [→ 部署指南](DEPLOYMENT.md)
- [→ 快速启动](START_GUIDE.md)
- [→ FinceptTerminal 集成](FINCEPT_INTEGRATION.md)

---

## 产品形态

KronosFinceptLab 是本地优先的量化金融驾驶舱，提供四种入口：

1. **Web UI** — `web/` 下的 Next.js 应用，包含仪表盘、预测、批量、数据、分析、宏观、回测、预警、新闻、自选、设置等页面
2. **REST API** — `src/kronos_fincept/api/app.py` 中的 FastAPI，Web UI 与外部客户端共用
3. **CLI** — `src/kronos_fincept/cli/commands/` 下的 Click 命令树
4. **MCP 服务** — `kronos_mcp/kronos_mcp_server.py`，向 MCP 客户端暴露预测/数据/分析操作

后端以 Python 为主，前端为 TypeScript/Next.js。Docker 构建组合运行时：Next.js 独立服务对外暴露 3000 端口，内部通过 `127.0.0.1:8000` 访问 FastAPI。

---

## 系统架构全景

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph TB
    subgraph user["[ 用户层 ]"]
        Browser["浏览器"]
        Terminal["终端 CLI"]
        MCPClient["MCP 客户端"]
    end

    subgraph entry["[ 入口层 ]"]
        WebUI["Next.js Web UI\nPort 3000"]
        FastAPI["FastAPI REST API\nPort 8000"]
        CLI["kronos CLI"]
        MCPServer["MCP Server"]
    end

    subgraph core["[ 核心层 ]"]
        Service["service.py\n共享预测服务"]
        Agent["agent.py\nAI 智能体编排"]
        Predictor["predictor.py\nKronos 模型推理"]
    end

    subgraph data["[ 数据层 ]"]
        DataSources["data_sources/\n多源数据适配"]
        Financial["financial/\n财务数据与指标"]
        Macro["macro/\n宏观信号 17+"]
        AlertEngine["alert_engine.py\n预警引擎"]
    end

    subgraph ai["[ AI 层 ]"]
        LLMRouter["LLM 路由\nOpenAI 兼容"]
        WebSearch["web_search.py\n网络搜索增强"]
    end

    subgraph storage["[ 存储层 ]"]
        RuntimeStore["runtime_store.py\n运行时状态"]
        Cache["缓存\n内存 + 文件"]
        Logs["结构化日志\nJSON Lines"]
    end

    Browser --> WebUI
    Terminal --> CLI
    MCPClient --> MCPServer
    WebUI --> FastAPI
    
    FastAPI --> Service
    FastAPI --> Agent
    CLI --> Service
    CLI --> Agent
    MCPServer --> Service
    MCPServer --> Agent
    
    Service --> Predictor
    Service --> DataSources
    Service --> Financial
    
    Agent --> LLMRouter
    Agent --> DataSources
    Agent --> Financial
    Agent --> Macro
    Agent --> WebSearch
    
    Predictor --> Cache
    DataSources --> Cache
    Financial --> Cache
    Macro --> Cache
    AlertEngine --> RuntimeStore
    
    LLMRouter --> WebSearch
```

---

## 后端分层

### FastAPI 应用

`src/kronos_fincept/api/app.py` 构建应用并注册所有路由模块，同时提供：

- API 文档门控：`KRONOS_ENABLE_API_DOCS`
- 请求 ID 与结构化日志
- 请求体大小检查
- API 安全中间件
- CORS 配置
- 启动时 Kronos 模型预热（启用时）
- 路由注册：健康、预测、批量、数据、回测、分析、预警、新闻、建议、任务、管理诊断

### 预测与分析服务

`src/kronos_fincept/service.py` 是预测与相关操作的主共享服务层。

核心职责：

- 从 OHLCV 行进行单资产预测
- 批量预测与收益排名
- 通过 `sample_count` 进行概率预测采样
- 允许时的干运行降级
- 真实 Kronos 模型加载/缓存
- 元数据报告：耗时、后端、缓存键、加载等待、推理等待、模型缓存状态

API、CLI、MCP 层调用此共享服务，而非重复实现预测逻辑。

### 路由模块

已实现的 REST 接口：

| 领域 | 路由 |
|------|------|
| 健康 | `GET /api/health`, `GET /api/health/deep` |
| 预测 | `POST /api/forecast` |
| 批量 | `POST /api/batch` |
| 数据 | `POST /api/data/batch`, `GET /api/data/global/{symbol}`, `GET /api/data/indicator/{symbol}`, `GET /api/data/a-stock/{symbol}`, `GET /api/data/search`, `GET /api/data/money-flow/{symbol}`, `GET /api/data/sector-flow`, `GET /api/data/hsgt-flow`, `GET /api/data/source-market/{artifact}` |
| 回测 | `POST /api/backtest/ranking`, `POST /api/backtest/report`, `POST /api/backtest/strategy`, `POST /api/backtest/strategy/scan`, `POST /api/backtest/strategy/rolling` |
| 分析 | `POST /api/v1/analyze/agent`, `/macro`, `/ai`, `/dcf`, `/risk`, `/portfolio`, `/derivative` |
| 预警 | `POST /api/alert/rules`, `GET /api/alert/rules`, `DELETE /api/alert/rules/{rule_id}`, `POST /api/alert/check`, `POST /api/alert/presets/prediction-deviation` |
| 新闻 | `POST /api/news/rss` |
| 建议 | `GET /api/v1/suggestions` |
| 任务 | `GET /api/jobs`, `POST /api/jobs/forecast`, `POST /api/jobs/analyze`, `POST /api/jobs/batch`, `POST /api/jobs/backtest`, `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/cancel` |
| 自选 | `GET/POST/PUT/DELETE /api/watchlist/lists`, `POST /api/watchlist/research` |
| 管理 | `GET /api/admin/security/summary`, 模型缓存清除/预热/状态路由 |

### 异步任务

`src/kronos_fincept/api/routes/jobs.py` 为耗时预测和分析操作提供进程内任务存储。

- 预测任务调用共享预测路径
- 分析任务调用共享自然语言智能体路径
- 批量和回测任务复用同步 API 路由的相同请求模型
- 任务状态包含：状态、步骤、结果、错误、时间戳、进度相关元数据
- 存储有界且限时，适合单进程本地或小型部署，非分布式队列

### 安全层

`src/kronos_fincept/api/security.py` 与 `src/kronos_fincept/security_utils.py` 实现部署加固：

- `/api/health` 公开；其他 `/api/*` 路径需认证（除非 `KRONOS_AUTH_DISABLED=1`）
- API 密钥通过 `X-Kronos-Api-Key` 或 `Authorization: Bearer <key>` 发送
- 用户密钥来自 `KRONOS_API_KEYS`
- 管理/内部密钥来自 `KRONOS_ADMIN_API_KEYS`、`KRONOS_INTERNAL_API_KEYS` 或 `KRONOS_INTERNAL_API_KEY`
- 预警和管理路由需要管理密钥
- 前端代理（`web/src/app/api/[...path]/route.ts`）在边缘执行相同检查，使用内部密钥向上游转发

---

## 数据流架构

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
sequenceDiagram
    participant User as 用户
    participant Web as Web UI
    participant API as FastAPI
    participant Service as Service 层
    participant DS as 数据源
    participant Pred as Predictor
    participant LLM as LLM 路由
    participant Cache as 缓存

    User->>Web: 请求预测
    Web->>API: POST /api/forecast
    API->>Service: forecast_from_request()
    Service->>Cache: 检查缓存
    alt 缓存命中
        Cache-->>Service: 返回缓存结果
    else 缓存未命中
        Service->>DS: 获取 OHLCV 数据
        DS-->>Service: 返回数据
        Service->>Pred: 模型推理
        Pred-->>Service: 返回预测
        Service->>Cache: 写入缓存
    end
    Service-->>API: 返回结果
    API-->>Web: JSON 响应
    Web-->>User: 渲染图表

    User->>Web: 提问分析
    Web->>API: POST /api/v1/analyze/agent
    API->>Service: analyze_investment_question()
    Service->>DS: 获取行情数据
    DS-->>Service: 返回数据
    Service->>LLM: 结构化查询
    LLM-->>Service: 返回分析
    Service-->>API: 返回报告
    API-->>Web: JSON 响应
    Web-->>User: 渲染报告
```

---

## 模块依赖图

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph LR
    subgraph api_module["[ API 模块 ]"]
        app["app.py"]
        security["security.py"]
        deps["deps.py"]
        models["models.py"]
    end

    subgraph route_module["[ 路由模块 ]"]
        forecast_r["forecast.py"]
        batch_r["batch.py"]
        data_r["data.py"]
        backtest_r["backtest.py"]
        analyze_r["analyze.py"]
        alert_r["alert.py"]
        jobs_r["jobs.py"]
        watchlist_r["watchlist.py"]
    end

    subgraph core_module["[ 核心模块 ]"]
        service["service.py"]
        agent_m["agent.py"]
        predictor_m["predictor.py"]
        schemas["schemas.py"]
    end

    subgraph data_module["[ 数据模块 ]"]
        ds_init["data_sources/init.py"]
        eastmoney["eastmoney_source.py"]
        yahoo["yahoo_source.py"]
        akshare["akshare_source.py"]
        binance["binance_source.py"]
    end

    subgraph fin_module["[ 财务模块 ]"]
        fin_manager["financial/manager.py"]
        indicators["financial/indicators.py"]
        dcf["financial/dcf.py"]
        risk["financial/risk.py"]
        portfolio["financial/portfolio.py"]
    end

    subgraph macro_module["[ 宏观模块 ]"]
        macro_manager["macro/manager.py"]
        macro_providers["macro/providers/"]
    end

    subgraph util_module["[ 工具模块 ]"]
        logging["logging_config.py"]
        config["config.py"]
        security_utils["security_utils.py"]
        web_search["web_search.py"]
    end

    app --> security
    app --> deps
    app --> models
    app --> forecast_r
    app --> batch_r
    app --> data_r
    app --> backtest_r
    app --> analyze_r
    app --> alert_r
    app --> jobs_r
    app --> watchlist_r

    forecast_r --> service
    batch_r --> service
    data_r --> ds_init
    backtest_r --> service
    analyze_r --> agent_m
    alert_r --> alert_engine
    jobs_r --> service
    jobs_r --> agent_m
    watchlist_r --> service

    service --> predictor_m
    service --> ds_init
    service --> schemas
    agent_m --> LLM
    agent_m --> fin_manager
    agent_m --> macro_manager
    agent_m --> web_search

    ds_init --> eastmoney
    ds_init --> yahoo
    ds_init --> akshare
    ds_init --> binance

    fin_manager --> indicators
    fin_manager --> dcf
    fin_manager --> risk
    fin_manager --> portfolio

    macro_manager --> macro_providers
```

---

## 前端架构

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph TB
    subgraph frontend["[ 前端层 ]"]
        subgraph next_app["[ Next.js App Router ]"]
            Dashboard["/dashboard\n仪表盘"]
            ForecastPage["/forecast\n预测"]
            BatchPage["/batch\n批量"]
            DataPage["/data\n数据"]
            AnalysisPage["/analysis\n分析"]
            MacroPage["/macro\n宏观"]
            BacktestPage["/backtest\n回测"]
            AlertsPage["/alerts\n预警"]
            NewsPage["/news\n新闻"]
            WatchlistPage["/watchlist\n自选"]
            SettingsPage["/settings\n设置"]
        end

        subgraph components["[ 组件层 ]"]
            Charts["图表组件\nRecharts/ECharts"]
            Forms["表单组件"]
            Tables["表格组件"]
            Cards["卡片组件"]
        end

        subgraph lib["[ 工具层 ]"]
            APIClient["api.ts\nAPI 客户端"]
            QueryKeys["queryKeys.ts\n缓存键"]
            Markets["markets.ts\n市场配置"]
            Symbols["symbols.ts\n代码标准化"]
        end

        subgraph stores["[ 状态层 ]"]
            Zustand["Zustand Stores"]
        end

        subgraph proxy["[ 代理层 ]"]
            APIRoute["api/[...path]\nNext.js API 路由"]
        end
    end

    Dashboard --> Components
    ForecastPage --> Components
    BatchPage --> Components
    DataPage --> Components
    AnalysisPage --> Components
    MacroPage --> Components
    BacktestPage --> Components
    AlertsPage --> Components
    NewsPage --> Components
    WatchlistPage --> Components
    SettingsPage --> Components

    Components --> Lib
    Lib --> APIClient
    APIClient --> Proxy
    Proxy --> FastAPI
    Stores --> Lib
```

---

## 数据源架构

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph LR
    subgraph dsm["[ 数据源管理器 ]"]
        DSM["data_sources/init.py"]
    end

    subgraph cn_sources["[ A股数据源 ]"]
        EastMoney["eastmoney_source.py\n东方财富"]
        AkShare["akshare_source.py"]
        Tushare["tushare_source.py"]
        Baostock["baostock_source.py"]
        TDX["tdx_source.py"]
        TDXNet["tdx_network_source.py"]
        TickFlow["tickflow_source.py"]
    end

    subgraph global_sources["[ 全球数据源 ]"]
        Yahoo["yahoo_source.py"]
        Stooq["stooq_source.py"]
        Binance["binance_source.py"]
        OKX["okx_source.py"]
    end

    subgraph cache_layer["[ 缓存层 ]"]
        SourceCache["source_market_cache.py\n源项目缓存"]
        MemoryCache["内存缓存"]
        FileCache["文件缓存"]
    end

    DSM --> EastMoney
    DSM --> AkShare
    DSM --> Tushare
    DSM --> Baostock
    DSM --> TDX
    DSM --> TDXNet
    DSM --> TickFlow
    DSM --> Yahoo
    DSM --> Stooq
    DSM --> Binance
    DSM --> OKX
    DSM --> SourceCache

    EastMoney --> MemoryCache
    Yahoo --> MemoryCache
    SourceCache --> FileCache
```

---

## 宏观信号架构

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph TB
    subgraph macro_mgr["[ 宏观管理器 ]"]
        MacroManager["macro/manager.py"]
    end

    subgraph providers["[ 信号提供方 17+ ]"]
        FRED["FRED\n美国宏观"]
        NBS["NBS\n中国统计局"]
        ChinaData["ChinaDataLive"]
        Treasury["Treasury\n美债"]
        BIS["BIS\n国际清算"]
        SEC["SEC/EDGAR"]
        CFTC["CFTC\n期货持仓"]
        DBNomics["DBNomics"]
        WebEnrich["Web 搜索增强"]
        RSS["RSS 订阅"]
        SourceProject["源项目缓存"]
    end

    subgraph signal_proc["[ 信号处理 ]"]
        Gather["信号收集"]
        Router["语义路由"]
        Fusion["信号融合"]
    end

    subgraph output["[ 输出 ]"]
        Report["宏观报告"]
        Evidence["证据链"]
    end

    MacroManager --> FRED
    MacroManager --> NBS
    MacroManager --> ChinaData
    MacroManager --> Treasury
    MacroManager --> BIS
    MacroManager --> SEC
    MacroManager --> CFTC
    MacroManager --> DBNomics
    MacroManager --> WebEnrich
    MacroManager --> RSS
    MacroManager --> SourceProject

    FRED --> Gather
    NBS --> Gather
    ChinaData --> Gather
    Treasury --> Gather
    BIS --> Gather
    SEC --> Gather
    CFTC --> Gather
    DBNomics --> Gather
    WebEnrich --> Gather
    RSS --> Gather
    SourceProject --> Gather

    Gather --> Router
    Router --> Fusion
    Fusion --> Report
    Fusion --> Evidence
```

---

## 回测引擎架构

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph LR
    subgraph bt_entry["[ 回测入口 ]"]
        RankingAPI["POST /api/backtest/ranking"]
        StrategyAPI["POST /api/backtest/strategy"]
        ScanAPI["POST /api/backtest/strategy/scan"]
        RollingAPI["POST /api/backtest/strategy/rolling"]
        ReportAPI["POST /api/backtest/report"]
    end

    subgraph bt_core["[ 回测核心 ]"]
        BacktestEngine["backtest.py\n回测引擎"]
        StrategyRunner["策略运行器"]
        MetricsCalc["指标计算"]
    end

    subgraph strategies["[ 策略库 ]"]
        RankingStrategy["排名策略\nTop-K 选股"]
        MACross["MA 交叉"]
        RSIStrategy["RSI 策略"]
        MACDStrategy["MACD 策略"]
        BollingerStrategy["布林带策略"]
    end

    subgraph report_gen["[ 报告生成 ]"]
        ReportGen["backtest_report.py\nHTML 报告"]
        EquityCurve["权益曲线"]
        Benchmark["基准对比"]
    end

    RankingAPI --> BacktestEngine
    StrategyAPI --> StrategyRunner
    ScanAPI --> StrategyRunner
    RollingAPI --> StrategyRunner
    ReportAPI --> ReportGen

    BacktestEngine --> RankingStrategy
    StrategyRunner --> MACross
    StrategyRunner --> RSIStrategy
    StrategyRunner --> MACDStrategy
    StrategyRunner --> BollingerStrategy

    BacktestEngine --> MetricsCalc
    StrategyRunner --> MetricsCalc
    MetricsCalc --> ReportGen
    ReportGen --> EquityCurve
    ReportGen --> Benchmark
```

---

## 预警引擎架构

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph TB
    subgraph rules["[ 规则定义 ]"]
        PriceChange["价格变化"]
        PriceThreshold["价格阈值"]
        RSIAlert["RSI 超买/超卖"]
        MACDAlert["MACD 交叉"]
        PredictionDev["预测偏差"]
        VolumeSpike["成交量突增"]
    end

    subgraph alert_engine["[ 预警引擎 ]"]
        AlertEngine["alert_engine.py"]
        RuleEvaluator["规则评估器"]
        StateStore["状态存储"]
    end

    subgraph notify["[ 通知渠道 ]"]
        Webhook["Webhook"]
        Email["邮件"]
        Console["控制台"]
    end

    subgraph monitor["[ 监控模式 ]"]
        OneShot["单次检查"]
        Continuous["持续监控"]
    end

    PriceChange --> AlertEngine
    PriceThreshold --> AlertEngine
    RSIAlert --> AlertEngine
    MACDAlert --> AlertEngine
    PredictionDev --> AlertEngine
    VolumeSpike --> AlertEngine

    AlertEngine --> RuleEvaluator
    RuleEvaluator --> StateStore
    RuleEvaluator --> Webhook
    RuleEvaluator --> Email
    RuleEvaluator --> Console

    OneShot --> AlertEngine
    Continuous --> AlertEngine
```

---

## 日志与可观测性

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#e8f4f8', 'primaryTextColor': '#1a1a2e', 'primaryBorderColor': '#2c3e50', 'lineColor': '#5d6d7e', 'secondaryColor': '#f0f3f4', 'tertiaryColor': '#ffffff', 'fontFamily': 'monospace'}}}%%
graph LR
    subgraph log_system["[ 日志系统 ]"]
        StructuredLog["结构化日志\nJSON Lines"]
        RequestID["请求 ID 追踪"]
        PerformanceLog["性能日志"]
        EventLog["事件日志"]
    end

    subgraph observability["[ 可观测性 ]"]
        HealthCheck["健康检查"]
        SecuritySummary["安全摘要"]
        ModelCacheState["模型缓存状态"]
        ProviderStatus["提供方状态"]
    end

    subgraph output_target["[ 输出目标 ]"]
        Console["控制台"]
        File["文件"]
        Docker["Docker 日志"]
    end

    StructuredLog --> Console
    StructuredLog --> File
    StructuredLog --> Docker
    RequestID --> StructuredLog
    PerformanceLog --> StructuredLog
    EventLog --> StructuredLog

    HealthCheck --> StructuredLog
    SecuritySummary --> StructuredLog
    ModelCacheState --> StructuredLog
    ProviderStatus --> StructuredLog
```

---

## 文件清单

```
src/kronos_fincept/
├── api/
│   ├── app.py                 # FastAPI 应用构建与路由注册
│   ├── security.py            # API 密钥认证与角色检查
│   ├── deps.py                  # 依赖注入
│   ├── models.py                # Pydantic 请求/响应模型
│   └── routes/
│       ├── forecast.py          # 单资产预测
│       ├── batch.py             # 批量预测排名
│       ├── data.py              # 行情数据、指标、搜索
│       ├── backtest.py          # 回测引擎（排名/策略/扫描/滚动）
│       ├── analyze.py           # 分析路由（智能体/宏观/AI/DCF/风险/组合/衍生品）
│       ├── alert.py             # 预警规则管理
│       ├── news.py              # RSS/Atom 新闻
│       ├── suggestions.py       # 建议提示
│       ├── jobs.py              # 异步任务
│       ├── watchlist.py         # 自选管理
│       └── admin.py             # 管理诊断
├── cli/
│   ├── main.py                  # CLI 入口
│   ├── output.py                # 输出格式化
│   └── commands/
│       ├── forecast.py          # 预测命令
│       ├── batch.py             # 批量命令
│       ├── data.py              # 数据命令
│       ├── backtest.py          # 回测命令
│       ├── analyze.py           # 分析命令
│       ├── alert.py             # 预警命令
│       ├── news.py              # 新闻命令
│       ├── serve.py             # 服务命令
│       ├── health.py            # 健康命令
│       ├── suggestions.py       # 建议命令
│       ├── model.py             # 模型工具
│       ├── jobs.py              # 任务命令
│       └── watchlist.py         # 自选命令
├── data_sources/
│   ├── __init__.py              # 数据源管理器初始化
│   ├── eastmoney_source.py      # 东方财富（A股资金流/板块）
│   ├── akshare_source.py        # AkShare
│   ├── tushare_source.py        # Tushare Pro
│   ├── baostock_source.py       # BaoStock
│   ├── yahoo_source.py          # Yahoo Finance
│   ├── stooq_source.py          # Stooq
│   ├── binance_source.py        # Binance
│   ├── okx_source.py            # OKX
│   ├── tdx_source.py            # TDX 本地
│   ├── tdx_network_source.py    # TDX 网络
│   ├── tickflow_source.py       # TickFlow
│   └── source_market_cache.py   # 源项目缓存
├── financial/
│   ├── manager.py               # 财务数据管理器（熔断/缓存/降级）
│   ├── indicators.py            # 技术指标（SMA/EMA/RSI/MACD/BB/KDJ/CCI/ATR/OBV）
│   ├── strategies.py            # 策略定义
│   ├── dcf.py                   # DCF 估值
│   ├── risk.py                  # 风险指标
│   ├── portfolio.py             # 组合优化
│   ├── derivatives.py           # 衍生品定价
│   ├── schemas.py               # 财务数据结构
│   ├── financial_source.py      # 财务数据源基类/统一接口
│   ├── global_market.py         # 全球市场数据
│   ├── baostock_financial.py    # BaoStock 财务源
│   └── yahoo_financial.py       # Yahoo 财务源
├── macro/
│   ├── manager.py               # 宏观数据管理器
│   ├── schemas.py               # 宏观信号结构
│   └── providers/               # 宏观信号提供方
│       ├── base.py              # 提供方基类
│       ├── fred.py              # FRED 美国宏观
│       ├── nbs_live.py          # 中国统计局实时
│       ├── chinalive.py         # ChinaDataLive
│       ├── china_macro.py       # 中国宏观聚合
│       ├── dbnomics.py          # DBNomics
│       ├── digital_oracle.py    # Digital Oracle
│       ├── source_project_cache.py # 源项目宏观缓存
│       └── ...
├── agent.py                     # AI 智能体编排（路由/工具调用/报告生成）
├── service.py                   # 共享预测服务
├── predictor.py                 # Kronos 模型推理（加载/缓存/干运行）
├── alert_engine.py              # 预警引擎
├── backtest_report.py           # HTML 回测报告生成
├── config.py                    # 配置管理
├── logging_config.py            # 结构化日志配置
├── security_utils.py            # 安全工具（SSRF/URL 校验）
├── web_search.py                # 网络搜索客户端（Tavily/Brave/Serper/AnySearch）
├── schemas.py                   # 共享数据结构
├── build_info.py                # 构建信息
├── runtime_env.py               # 运行时环境
├── runtime_store.py             # 运行时状态存储
├── data_adapter.py              # 数据适配器
├── akshare_adapter.py           # AkShare 适配器
├── cninfo.py                    # 巨潮资讯
└── cli.py                       # CLI 兼容入口

web/src/
├── app/                         # Next.js App Router 页面
├── components/                  # React 组件
├── lib/                         # 工具库（API 客户端、Query Key、市场配置）
├── stores/                      # Zustand 状态管理
└── types/                       # TypeScript 类型

kronos_mcp/
├── kronos_mcp_server.py         # MCP 服务实现（59 个符号）
└── __init__.py
```

---

## 关键技术决策

### 1. 本地优先设计

所有核心能力在本地运行，无需外部依赖。外部服务（数据源、LLM）为可选增强，失败时自动降级。

### 2. 数据源熔断与降级

- 每个数据源独立熔断（5 次失败 / 5 分钟冷却）
- 自动降级到下一数据源
- 内存 + 文件缓存减少重复请求
- 过时缓存作为最后防线

### 3. 统一 LLM 路由

所有 AI 功能通过单一 OpenAI 兼容接口：`LLM_API_KEY` + `LLM_BASE_URL` + `LLM_MODEL`。支持：

- 结构化 JSON 输出
- 工具调用
- 上下文预算管理
- 降级链（主 -> 备选 -> 本地）

### 4. 前端代理架构

Next.js 前端通过 `api/[...path]` 路由代理到 FastAPI，在边缘执行：

- 认证检查
- 请求体大小限制
- 内部密钥转发
- 超时控制

### 5. 进程内任务队列

异步任务使用内存存储，适合单进程部署。非分布式，但支持：

- 任务提交/取消/查询
- 进度跟踪
- 有界存储（自动清理旧任务）

---

## 性能特征

| 指标 | 数值 | 说明 |
|------|------|------|
| 文件数 | 243 | 后端 185 Python + 前端 44 TS/TSX |
| 符号数 | 4,911 | 函数 1,618 + 方法 827 + 类 326 |
| 依赖边 | 11,460 | 调用关系 |
| 测试模块 | 70+ | 覆盖核心功能 |
| 数据源 | 13+ | A股/全球/宏观 |
| 宏观提供方 | 17+ | 多维度信号 |
| 技术指标 | 10+ | 常用技术分析 |
| 回测策略 | 5+ | 排名/MA/RSI/MACD/布林带 |

---

## 导航

- [← 返回 README](../README.md)
- [→ API 接口文档](API.md)
- [→ CLI 命令文档](CLI.md)
- [→ 部署指南](DEPLOYMENT.md)
- [→ 快速启动](START_GUIDE.md)
- [→ FinceptTerminal 集成](FINCEPT_INTEGRATION.md)
