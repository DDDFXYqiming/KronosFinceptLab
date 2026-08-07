# Kronos 运行/训练口径对齐报告（pred_len=10）2026-08-07

> 文档状态：Current（对齐工作主报告）
> 关联计划：[对齐修订计划 v2]（本轮实施）
> 数据版本：`clean_v8_largecap_recent`，评测 manifest `evaluation_manifest_largecap_v8_recent_pred10.json`

## 1. 结论摘要

- **对齐基准**：本项目微调配置（lookback=90、**pred_len=10**、日线、六列、A/H 前复权），不是官方
  示例的 400/120/T=1.0/不复权；官方参数只作为 base 模型边界记录。
- **pred_len 统一为 10**：运行时（预测页/分析页/API/CLI）、评测协议、训练模板三链路全部切换；
  pred_len=5 历史结果存档、不横向比较。
- **T 决策（G-A）**：T=1.0 在样本多样性（区间宽度中位数 1.68 倍、上行概率更分散）和 150 样本
  诊断（RankIC 0.2035 vs 官方 0.0800）上均通过，但 600 样本 Confirm 所有候选配对统计未通过
  （p=0.67~0.82），按计划规则**协议温度维持 0.5**；论文（arXiv 2508.02739）低温约 0.6 的依据
  一并记录。
- **复权决策（G-B）**：A 股 qfq vs 不复权中位收盘差异 2.4%~3.4%（除息量级），预测方向一致，
  保持 qfq（训练/服务同口径）；港股 yfinance vs AKShare qfq 对比因 Yahoo 限流未能完成，待重试。
- **修复真实 Bug**：BaoStock `adjustflag` 映射写反（1=后复权、2=前复权、3=不复权），已修正
  `baostock_source.py`；此前 `adjust="none"` 实际返回的是后复权价格。
- **无晋级候选**：pred_len=10 协议下官方/生产/既有候选均未通过 v2 门槛，生产 junction 保持
  `v3-cont epoch_2` 不变；4x 训练保持暂停，恢复作为独立事项。

## 2. 官方用法核查（结论与修正）

核查 `external/Kronos` README 与示例脚本、`finetune/config.py`，并结合本仓库运行时链路：

| 项 | 官方示例 | 上游微调配置 | 本项目（对齐后） | 判断 |
|---|---|---|---|---|
| lookback | 400 | 90 | 90 | ✅ 一致 |
| pred_len | 120 | 10 | **10** | ✅ 对齐训练窗口 |
| T | 1.0 | — | 0.5（协议维持） | ⚠️ 见 G-A |
| sample_count | 1 | — | 8（页面可调）/16（agent 单标的） | ✅ 官方支持多次采样 |
| 归一化 | 模型内部 z-score | 同 | 同 | ✅ |
| 数据口径 | 不复权 | A/H qfq | A/H qfq | ✅ 训练/服务同口径 |

两处修正此前对话中的说法：

1. **美股 amount 不是恒 0**：分析页数据链路 `GlobalMarketSource._standardize_history_frame`
   无条件把 amount 填为 `close × volume`；`yahoo_source` 同样处理。真实风险仅是边界不统一
   （API/CLI 不传 amount 时默认为 0），已在模型入口统一兜底。
2. **A 股口径已对齐**：训练 `clean_v8`（BaoStock qfq）与服务端（BaoStock qfq 优先）同口径；
   真正需要核对的是港股（服务 yfinance auto_adjust vs 训练 AKShare qfq），因 Yahoo 限流待补。

## 3. 参数集中化落地

新增 `src/kronos_fincept/config.py::KronosRuntimeConfig`（env 可覆盖，`.env.example` 已同步）：

| 键 | 默认 | 用途 |
|---|---|---|
| `KRONOS_RUNTIME_LOOKBACK` | 90 | 页面/agent 截取 K 线根数 |
| `KRONOS_PRED_LEN` | 10 | 预测长度（全链路） |
| `KRONOS_TEMPERATURE` | 0.5 | 采样温度（G-A 后维持） |
| `KRONOS_TOP_P` | 0.9 | 核采样 |
| `KRONOS_SAMPLE_COUNT` | 8 | 预测页默认采样数 |
| `KRONOS_AGENT_SAMPLE_COUNT_SINGLE/MULTI` | 16 / 8 | 分析页单/多标的采样数 |

- `schemas.py`：`ForecastRequest` 默认与 `from_dict`/`from_batch_item` 的温度兜底统一为配置值
  （消除原先 0.5 vs 1.0 的不一致）。
- `api/models.py`：请求默认（pred_len/temperature/top_p/sample_count）读配置。
- 新增只读端点 `GET /api/forecast/config`，返回上述参数与生效 `model_id`（与 `/api/health`
  一致，当前 `NeoQuasar/Kronos-small` junction）。
- 预测页 `forecast/page.tsx` 删除硬编码常量，改从配置端点取值（sample_count 仍可用户调整）；
  `web` 类型检查通过。
- 验证：CLI/API 不带参数时 `pred_len=10、T=0.5`；`/api/forecast/config` 与 health 模型 ID 一致。

## 4. T 对比（G-A 证据）

脚本：`examples/compare_runtime_params.py`，固定 seed=42、生产权重（junction v3-cont epoch_2）、
同日（2026-08-06）、pred_len=10、lookback=90、sc16（T 对比）/ sc8（复权对比）。

| 标的 | 市场 | T0.5 上行概率 | T1.0 上行概率 | T0.5 区间宽 | T1.0 区间宽 | 宽度比 | 方向 |
|---|---|---:|---:|---:|---:|---:|---|
| 600519 | A | 0.000 | 0.062 | 31.34 | 115.80 | 3.70 | down/down |
| 601318 | A | 0.000 | 0.125 | 2.36 | 3.26 | 1.38 | down/down |
| 000001 | A | 0.000 | 0.250 | 0.28 | 0.70 | 2.53 | down/down |
| 00700 | HK | 0.062 | 0.125 | 44.97 | 73.01 | 1.62 | down/down |
| 09988 | HK | 0.125 | 0.125 | 18.51 | 31.10 | 1.68 | down/down |

聚合：区间宽度中位数比 **1.68**（≥1.5 阈值）；平均上行概率 T0.5=0.037、T1.0=0.138（T=1.0
明显偏离 0/1 边界）。G-A(a) 通过。

150 样本诊断（pred_len=10、sc8、T=1.0、seed=42，样本哈希 `807f4411…`）：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc |
|---|---:|---:|---:|
| 生产 v3-cont epoch_2 | 0.2035 | 0.1224 | 53.33% |
| 官方 Kronos-small | 0.0800 | 0.0333 | 50.00% |

RankIC 增量 +0.1235（≥+0.02）、DirAcc −0.033（未跌破 −0.02），G-A(b) 通过 → 升级 600 样本。

600 样本 Confirm（pred_len=10、sc8、T=1.0、Bootstrap 5,000，样本哈希 `a419b8b9…`）：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | MAE | Top5 超额 | 配对 p |
|---|---:|---:|---:|---:|---:|---:|
| 生产 v3-cont epoch_2 | 0.1347 | 0.0950 | 54.83% | 0.0712 | +0.0176 | 0.822 |
| fullv3_ep3cont_best | 0.1345 | 0.1286 | 55.00% | 0.0712 | +0.0271 | 0.665 |
| fast_recipe_best | 0.1226 | 0.1094 | 54.17% | 0.0711 | +0.0297 | 0.764 |
| 官方 Kronos-small | 0.1013 | 0.0583 | 50.50% | 0.1149 | −0.0058 | 基线 |

点估计上所有候选均超过官方（RankIC +0.021~0.034、DirAcc +3.7~4.5pp、MAE 约为官方一半），但配对
Bootstrap 与逐期配对 t 检验均未达到 p<0.10 → **v2 门槛未通过 → 协议温度维持 0.5**。

**G-A 结论**：T=1.0 作为概率语义更优的候选参数记录在案；切换协议需要严格 OOS 周期积累后再次
验证统计显著性。论文（arXiv 2508.02739）在精度/收益敏感任务建议低温约 0.6，当前 0.5 与之一致。

## 5. 复权对比（G-B 证据）

| 标的 | 市场 | 中位收盘差异（qfq vs raw） | raw 方向 | qfq 方向 |
|---|---:|---|---|---|
| 600519 | A | 2.37% | down | down |
| 601318 | A | 3.35% | down | down |
| 000001 | A | 3.29% | down | down |

差异为除权除息调整量级（2026-05~07 分红事件在窗口内），预测方向未变 → 保持 qfq。

**发现并修复 Bug**：`baostock_source.py` 中 `adjustflag` 映射写反。BaoStock 官方语义为
`1=后复权、2=前复权、3=不复权`，原代码 `{"qfq":"2","hfq":"3","none":"1"}` 导致
`adjust="none"` 实际返回后复权价格（000001 收盘 1407.75 vs 真实 11.27）。已修正为
`{"qfq":"2","hfq":"1","none":"3"}`。生产与训练链路均只用 qfq，未受影响；任何未来
raw/hfq 取数必须使用修正后的映射。

港股 yfinance vs AKShare qfq 对比因 Yahoo 限流未完成，待限流解除后重跑
`compare_runtime_params.py` 补录。

## 6. amount 审计

脚本：`examples/audit_amount_inputs.py`（输出 `output/amount_audit.json`）。

| 标的 | 市场 | 路径 | 行数 | 0 amount | 0 volume |
|---|---|---|---:|---:|---:|
| AAPL/MSFT/NVDA | US | GlobalMarketSource(yfinance) | 0（Yahoo 限流） | — | — |
| 00700 | HK | AKShare qfq | 5442 | 5 | 4 |
| 09988 | HK | AKShare qfq | 1645 | 0 | 0 |
| 00005 | HK | AKShare qfq | 6943 | 7 | 6 |

- 美股/港股 yfinance 路径由代码保证 `amount = close × volume`（`_standardize_history_frame`
  无条件赋值），本次未能联网复核（Yahoo 限流），待重试。
- 港股 AKShare 存在极少量停牌交易日（约 0.1%）量额同时为 0，价格平盘；该行为与价格语义一致，
  记录为已知边界（训练清洗会剔除 0 量额行，服务端保留停牌日，二者口径差约 0.1%）。
- 模型边界兜底：`data_adapter.rows_to_dataframe` 在 amount 全 0 时回填 `close × volume` 并告警；
  真实 A/H 数据不触发。

## 7. 交易日历

`make_future_timestamps` 增加 AkShare 交易日历（缓存 `output/calendars/trade_dates.csv`）：
2026-07-31（周五）最后 K 线 → 未来 3 个交易日为 08-03/08-04/08-05（跳过周末）；日历不可用时
回退原步长外推。验证通过。

## 8. 评测协议切换（pred_len=10）

- 新 manifest：`output/evaluation_manifest_largecap_v8_recent_pred10.json`
  （`protocol: lookback=90, pred_len=10, sample_step=15, embargo_bars=5`；validation 折叠 1603 样本）。
- 新固定 600 样本：`configs/evaluation/evaluation_samples_pred10.json`，哈希
  `a419b8b97ec3c604f5b0140d82edd0f34394230b8474d630219118abcd57d024`
  （pred_len=10 下两个市场各只有 4 个大横截面日期，改为 4 日期 × A100 + HK50 = 600）。
- 150 样本诊断：`configs/evaluation/evaluation_samples_pred10_150.json`，哈希 `807f4411…`。
- pred_len=5 的 `b54adb…` 样本与全部历史结果为存档，不参与 pred_len=10 排名。
- 构建入口：`build_clean_v7_largecap.py --stage manifest --pred-len 10`（新增参数）。

## 9. 600 样本正式结果（pred_len=10、T=0.5、sc8）

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | MAE | Top5 超额 | v2 门槛 |
|---|---:|---:|---:|---:|---:|---|
| 生产 v3-cont epoch_2 | **0.1286** | 0.1056 | 53.33% | 0.0715 | −0.0030 | 未通过（统计 p=0.736，Top5<0） |
| fullv3_ep3cont_best | 0.0675 | 0.1378 | **56.00%** | 0.0735 | +0.0303 | 未通过（RankIC 增量<+0.02，p=0.996） |
| fast_recipe_best | 0.0630 | 0.1335 | 56.00% | 0.0736 | +0.0011 | 未通过（RankIC 增量<+0.02，p=0.949） |
| 官方 Kronos-small | 0.0790 | 0.0550 | 50.50% | 0.1077 | −0.0016 | 基线 |

结论：pred_len=10 协议下无候选通过 v2 门槛；生产 junction 保持 `v3-cont epoch_2`。

## 10. 训练对齐与后续

- 训练模板固化为上游标准：lookback=90、**predict_window=10**、六列、A/H qfq、max_context=512、
  clip=5（`external/Kronos/finetune/config.py` 与 `config_full_small.yaml` 同款）。
- v8 系列候选（predict_window=5 训练）在 pred_len=10 协议下只作诊断参考；正式晋级需用
  predict_window=10 重新训练——列入下一轮训练计划（含是否恢复 4x、是否按新 T 重跑基线）。
- 4x 训练保持暂停；Qlib 回测与 v9 全量拉取不在本轮。
- 严格 OOS 每周快照照常积累，pred_len=10 冻结参数。
