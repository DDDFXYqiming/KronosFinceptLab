# KronosFinceptLab v10.9 上游功能集成 Spec

> 基于上游项目 Kronos / FinceptTerminal / Digital Oracle 分析
> 日期: 2026-05-09

---

## 汇总对比

### 上游 Kronos (shiyu-coder/Kronos) — AAAI 2026

| 能力 | 上游状态 | KFL 当前 | 差距 |
|------|---------|---------|------|
| Kronos-base (102.3M, ctx=512, Tokenizer-base) | ✅ 开源 | ✅ 已集成 | - |
| Kronos-mini (4.1M, ctx=2048, Tokenizer-2k) | ✅ 开源 | ❌ 未支持 | **需新增** |
| Kronos-small (24.7M, ctx=512, Tokenizer-base) | ✅ 开源 | ❌ 未支持 | **需新增** |
| Kronos-large (499.2M) | ❌ 闭源 | ❌ 未支持 | 无需处理 |
| CSV fine-tuning pipeline (finetune_csv/) | ✅ 新增 | ❌ 未集成 | 后续迭代 |
| Web UI Live Demo | ✅ 有 | ✅ 有（独立实现） | - |
| predict_batch() | ✅ | ✅ | - |
| predict() with sampling | ✅ | ✅ | - |

### 上游 Digital Oracle (komako-workshop/digital-oracle) v1.0.3

| 能力 | 上游状态 | KFL 当前 | 差距 |
|------|---------|---------|------|
| Polymarket, Kalshi, Yahoo Price, Deribit | ✅ | ✅ | - |
| USTreasury (yield curve) | ✅ | ✅ | - |
| USTreasury (FX exchange rates) | ✅ | ❌ | **需新增** |
| CFTC COT, CoinGecko, EDGAR, BIS, World Bank | ✅ | ✅ | - |
| YFinance (options chain + Greeks) | ✅ | ✅ | - |
| FearGreedProvider (CNN composite) | ✅ | ✅ | - |
| CMEFedWatchProvider | ✅ | ✅ | - |
| WebSearchProvider | ✅ | ✅ | - |
| BIS credit-to-GDP gap | ✅ | ❌ | **需增强** |
| Stooq data provider | ✅ | ❌ | 后续迭代 |
| 6-step methodology (Understand→Select→Route→Fetch→Analyze→Report) | ✅ | ⚠️ 部分 | **需增强** |
| 时间分层结论（S/M/L term） | ✅ | ⚠️ 部分 | **需增强** |

### 上游 FinceptTerminal v4.0.2 (C++20/Qt6 桌面端)

| 能力 | 可移植性 | 建议 |
|------|---------|------|
| DBnomics 经济数据连接器 (100+ 源) | ✅ 高 | **新增 Provider** |
| FICC 模块 | ✅ 中 | 后续迭代 |
| 新闻/舆情分析 | ✅ 中 | 后续迭代 |
| QuantLib Suite (18 模块) | ⚠️ 中 | 已有 5 个，可扩展 |
| 37 AI Agent 角色 | ⚠️ 低 | 参考角色定义 |
| 桌面端独有 (节点编辑器、多券商、海事追踪) | ❌ | 不适用 |

---

## 本次实现范围

### P1 (Tier 1) — 高价值、低风险

1. **Kronos-mini 模型支持**
   - 新增 Tokenizer-2k 自动检测与加载
   - 新增模型 ID 映射 (NeoQuasar/Kronos-mini)
   - 更新 DEFAULT_MODEL_ID 选项
   - 在 predictor.py 中支持 max_context=2048
   - **收益**: Zeabur 上模型内存从 ~400MB 降至 ~16MB，推理速度提升 10x+

2. **Kronos-small 模型支持**
   - 新增模型 ID 映射 (NeoQuasar/Kronos-small)
   - 复用 Tokenizer-base (已支持)
   - **收益**: 中等模型，24.7M 参数，比 base 轻量 4x

3. **USTreasury 汇率数据**
   - 增强现有 treasury provider 支持 FX 汇率
   - 新增 exchange_rates() 方法

4. **BIS credit-to-GDP gap**
   - 增强现有 BIS provider，添加 credit_gap 数据端点

### P2 (Tier 2) — 后续迭代

5. DBnomics 经济数据 Provider
6. 增强宏观报告时间分层结论
7. Stooq 数据兼容 Provider
8. CSV fine-tuning 流水线集成

---

## 实现计划

### S1: Kronos 模型族支持 (schemas.py, predictor.py, config.py)

- 新增 DEFAULT_MODEL_ID 选项: mini/small/base
- Tokenizer 根据模型自动选择: mini→Tokenizer-2k, small/base→Tokenizer-base
- 调整 max_context: mini=2048, small/base=512
- 更新 Dockerfile 环境变量支持 KRONOS_MODEL_ID=NeoQuasar/Kronos-mini

### S2: USTreasury 汇率增强 (macro/providers/)

- 扩展 USTreasury provider FX 数据端点
- 添加汇率数据到 macro 维度映射

### S3: BIS credit gap 增强 (macro/providers/)

- 扩展 BIS provider 支持 credit-to-GDP gap 查询
- 添加 credit gap 到 macro 信号维度
