# Kronos 微调模型评估标准 v3

> 文档状态：Current（生产参数开发选模标准；沿用 v2 指标门槛）
> 最后核对：2026-08-07
> 协议版本：pred_len=10（2026-08-07 起；pred_len=5 结果存档，见第 9 节）
> 数据边界与 OOS 纪律继续沿用 [`EVALUATION_PROTOCOL.md`](EVALUATION_PROTOCOL.md)

## 1. 适用目标

本标准用于比较 Kronos-small 与 A/H 股微调 checkpoint，服务项目当前两类调用：

- 预测页：90 日回看、未来 10 日 OHLC 预测，关注终点收益、方向和展示质量；
- 分析页：批量预测多只股票，关注跨资产排序能力。

开发评测不能替代真实交易回测，也不能把已经参与选模的 2026 数据称为严格 OOS。

## 2. 固定评测层级

| 层级 | 样本 | 推理参数 | 用途 |
|---|---:|---|---|
| Smoke | 固定 16 | `sample_count=1, T=0.3, top_p=0.9` | 只检查模型链路 |
| Confirm | 固定 600 | `pred_len=10, sample_count=8, T=0.5, top_p=0.9` | 唯一同场选模与配对统计 |
| Analysis check | 冠军固定 128，并与官方补跑完整600 | `pred_len=10, sample_count=16, T=0.5, top_p=0.9` | 核对分析页实际参数 |
| Strict OOS | 模型冻结后的新数据 | 参数冻结 | 最终泛化证据 |

同一轮比较必须满足：相同 manifest、fold、样本哈希、tokenizer、随机种子和推理参数。不同评测集的
历史结果不能拼接成统一排名。

当前 Confirm 使用 `configs/evaluation/evaluation_samples_pred10.json`（哈希
`a419b8b9…`）：pred_len=10 下两个市场各只有 4 个大横截面目标日期，因此 A 股 4 个日期 × 100 只，
港股 4 个日期 × 50 只。每个市场/日期形成完整横截面，总计 600 样本。150 样本 Screen 已退出晋级
流程，避免小样本点估计主导模型选择。

protocol 版本纪律：pred_len=5 的 `evaluation_samples_v4.json`（哈希 b54adb…）与第 9 节结果
仅存档，不参与 pred_len=10 排名。

随机性按固定有序 batch 派生，结果必须记录 `ordered_batch_key_v1`。同一 fixture、seed、batch
size 重跑和断点恢复时逐样本预测必须一致。

当前紧凑时间划分：

- 训练：2022-01-01～2026-04-30；
- 验证与 Confirm：2026-05-01～2026-07-31；
- 诊断测试：2026-08-01 起；
- 严格未来 OOS：模型及参数冻结后的新增数据。

## 3. 指标

每行由 `symbol, market, target_end, last_close, pred_close, true_close` 构成，并计算：

```text
pred_ret = pred_close / last_close - 1
true_ret = true_close / last_close - 1
```

| 维度 | 指标 | 角色 |
|---|---|---|
| 排序 | `RankIC_pooled`：全部固定样本 Spearman | v2 排名主指标 |
| 排序 | `MeanDailyRankIC`：按市场×目标日期计算截面 RankIC 后平均 | 稳健性与配对检验 |
| 线性相关 | `IC_pooled` | 报告 |
| 方向 | `DirectionAccuracy` | 展示质量护栏 |
| 误差 | `EndpointReturnMAE` | 第 10 日终点收益误差；不是完整 OHLC 路径 MAE |
| 简化经济诊断 | 分组 Top5 等权实际收益减组内平均收益 | 参考，不作为正式回测 |

`RankIC_pooled` 会受到跨日期收益尺度和市场状态影响，因此必须同时报告 A 股、港股和逐期
`MeanDailyRankIC`，不能单独据此宣称策略有效。

Top5 诊断不包含持仓延续、换手、交易成本、涨跌停、停牌和撮合，其 `diagnostic_ir` 也不是严格
年化 IR。正式经济结论仍需 Qlib 或等价事件回测。

## 4. 显著性与晋级规则

候选和基线共享相同真实收益，不能使用“两个独立相关系数”的 Fisher-z 近似。本项目使用：

1. 按 `(market, target_end)` 整组配对 Bootstrap，重采样时同时抽取候选和基线；
2. 对共同日期的截面 RankIC 使用配对 t 检验；
3. 报告 pooled RankIC 增量的 95% CI 和双侧 p 值。

候选相对官方 `Kronos-small` 同时满足以下条件才通过 v2 开发 Confirm：

```text
1. RankIC_pooled >= baseline + 0.02
2. 配对 grouped Bootstrap 或逐期 RankIC 配对检验 p < 0.10
3. DirectionAccuracy >= baseline - 0.02
4. EndpointReturnMAE <= baseline
5. Top5 分组平均超额 > 0
```

多候选通过时按 `RankIC_pooled` 排序。通过开发 Confirm 只代表可以继续进行生产参数复核和未来
OOS，不代表已经通过生产收益验证。

## 5. 2026-08-06 生产参数固定横截面结果

历史 v3 Confirm 使用 `clean_v7_largecap / validation_2026_q1`、固定 600 样本、
`sample_count=8, T=0.5, top_p=0.9`、batch size 32 和 `ordered_batch_key_v1` 随机流。样本哈希：

`7cfa257771d5496fc500eed3ece0b87d43b13b0c5f1cfdc35ac203bba93ee9ec`

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 门槛 |
|---|---:|---:|---:|---:|---|
| **full_small_v3** | **0.0043** | 0.0786 | **50.83%** | **0.0424** | 未通过统计门槛 |
| v3-cont epoch 2（当前生产） | -0.0250 | 0.0713 | 49.33% | 0.0511 | 未通过 |
| largecap L3 | -0.0251 | **0.0823** | 49.67% | 0.0492 | 未通过 |
| 官方 Kronos-small | -0.0303 | -0.0083 | 49.00% | 0.0572 | 基线 |
| largecap L2 | -0.0314 | 0.0741 | 49.50% | 0.0505 | 未通过 |
| v7 epoch 1 | -0.0368 | 0.0731 | 50.33% | 0.0498 | 未通过 |
| v3-cont best_model | -0.0377 | 0.0471 | 49.33% | 0.0517 | 未通过 |

`full_small_v3` 相对官方的 Pooled RankIC 增量为 `+0.0347`，但 5,000 次配对 Bootstrap 95% CI
为 `[-0.1021, 0.2027]`，双侧 `p=0.5887`；方向增量 CI 也跨 0。其 Endpoint MAE 增量为
`-0.0148`，95% CI `[-0.0173, -0.0119]`，说明终点误差改善稳定，但排序和方向没有稳定晋级证据。

分析页完整 600 样本 `sample_count=16` 复核只比较 `full_small_v3` 与官方模型：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE |
|---|---:|---:|---:|---:|
| full_small_v3 | -0.0288 | 0.0562 | 48.83% | **0.0424** |
| 官方 Kronos-small | -0.0310 | -0.0160 | **49.50%** | 0.0568 |

RankIC 增量仅 `+0.0022`，95% CI `[-0.1240, 0.1619]`。固定 128 样本曾出现约 62%方向率，
但同一子集在 `sample_count=8` 下也同样偏高，证明这是子集效应；当前结论必须以完整 600 样本为准。

按照上游 `qlib_test.py` 的 Top-K、持有期和成本思想，本项目额外计算非重叠 5 日周期 Top20%：
开仓成本 `0.1%`、平仓成本 `0.15%`，与当期股票池等权收益比较。业务收益率信号下，largecap L2
成本后平均超额点估计最高，为 `+0.754%/期`，相对官方的95% CI `[-0.293%, +1.778%]`；严格按
上游标准化 `last` 信号重算后，largecap L3 点估计最高，为 `+0.719%/期`，相对官方95% CI
`[-0.301%, +1.553%]`。全部候选区间均跨0；`sample_count=16` 下 full_small_v3 的上游信号点估计
还低于官方。该指标没有 TopkDropout 的跨期持仓、涨跌停撮合、滑点和市场冲击，因此是上游对齐
经济诊断，不是完整 Qlib 回测。

原始预测及统计：`output/evaluation_v3_production/`。本轮没有 checkpoint 通过晋级，不切换生产
junction；`full_small_v3` 只作为低 MAE 研究候选保留。

## 6. 2026-08-05 统一 Confirm 结果（历史 v2 口径）

本轮重新使用 DirectML 顺序推理，所有模型在 `clean_v6_largecap` 的 `validation_2026_q1` 上同场
评测。固定 600 个样本，样本哈希：

`9e93c4b8b708e0297ca19508bf695c5784cf640df88f981dd7bac548689be593`

该批结果使用旧的“按股票抽取窗口、`sample_count=1, T=0.3`”口径，只作为迁移前历史基准，
不与新的 v3 固定横截面 Confirm 拼表排名。

评测明细位于 `output/evaluation_v2_unified/confirm/`，统一统计结果位于
`output/evaluation_v2_unified/comparison_report.json`。

| 排名 | 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | Top5 超额 | 开发 IR | v2 通过 |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | **v3_cont_epoch2** | **0.1076** | **0.1544** | **53.00%** | 0.0511 | **0.00311** | **2.21** | **是** |
| 2 | largecap_l2 | 0.0855 | 0.0173 | 51.33% | 0.0504 | 0.00240 | 1.69 | 否 |
| 3 | v3_cont_best | 0.0796 | 0.0579 | 52.00% | 0.0524 | 0.00242 | 2.01 | 否 |
| 4 | largecap_l3_best（epoch 4） | 0.0629 | 0.1271 | 52.00% | 0.0505 | 0.00181 | 1.35 | 否 |
| 5 | full_small_v3 | 0.0325 | 0.1269 | 51.50% | **0.0447** | 0.00191 | 0.97 | 否 |
| 6 | 官方 Kronos-small | -0.0034 | -0.0696 | 50.33% | 0.0609 | 0.00024 | 0.21 | 基线 |

分市场 Pooled RankIC：

| 模型 | A 股 | 港股 |
|---|---:|---:|
| **v3_cont_epoch2** | **0.1005** | **0.1329** |
| largecap_l2 | 0.0872 | 0.0981 |
| v3_cont_best | 0.0672 | 0.1216 |
| largecap_l3_best | 0.0544 | 0.0911 |
| full_small_v3 | 0.0138 | 0.0990 |
| 官方 Kronos-small | 0.0244 | -0.0792 |

`v3_cont_epoch2` 相对官方基线：

- Pooled RankIC 增量 `+0.1110`；按日期整组 Bootstrap 的 95% CI 为 `[-0.0493, 0.2794]`，
  双侧 `p=0.1692`；
- MeanDaily RankIC 增量约 `+0.2240`，40 个共同日期的配对检验 `p=0.0519`；
- 方向准确率增加 `2.67pp`；
- EndpointReturnMAE 降低 `0.00987`，配对 Bootstrap 95% CI `[-0.01811, -0.00081]`；
- A 股和港股的 Pooled RankIC 均为正。

因此，`v3_cont_epoch2` 是本轮唯一通过 v2 开发 Confirm 的模型，也是当前统一评测冠军。统计证据
主要来自逐期 RankIC，pooled RankIC 的 grouped Bootstrap 仍包含 0，所以结论是“值得继续验证”，
不是“已经严格证明生产收益更高”。

## 7. clean_v6 统一 Confirm 决定

1. 当前生产 junction 已指向 `v3_fromFTv1_cont/basemodel/epoch_2`，与本轮冠军一致，无需切换；
2. 不继续使用同一数据无限 continuation；L2/L3 的更多训练没有超过该 checkpoint；
3. 当时的后续项是冠军和官方基线的 `sample_count=8/16, T=0.5` 生产参数复核；新一轮 PIT
   continuation 的判定见下一节；
4. 严格 OOS 必须等待模型冻结后的新数据；
5. 在宣称经济有效前，另行完成含成本、换手和交易约束的正式回测。

## 8. clean_v7 PIT continuation 判定

`clean_v7_largecap` 引入历史时点指数成员资格后，父模型续训两轮。Screen 第一名 v7 epoch 1
与父模型、官方基线进入同一 595 样本 Confirm，样本哈希：

`45d8b47b66890ab945aa64dcba91a02fc76ac85144050766fad20151a9ce61d2`

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| v7 epoch 1 | -0.0481 | 0.0196 | 48.57% | **0.0504** | 否 |
| 父模型 v3-cont epoch 2 | -0.0506 | 0.0057 | 48.74% | 0.0518 | 父基线 |
| 官方 Kronos-small | -0.0596 | **0.0893** | **49.08%** | 0.0586 | 官方基线 |

v7 epoch 1 相对父模型的 Pooled RankIC 增量为 `+0.0025`，5,000 次按市场×目标日期配对
Bootstrap 95% CI 为 `[-0.0512, 0.0682]`，双侧 `p=0.9358`。它没有达到 `+0.02` 门槛，也
没有统计证据。按停止规则，不补跑被中断且无 checkpoint 的第三轮，不进入 2026-04～07 诊断，
生产 junction 保持不变。

统一重算工具：`examples/compare_evaluations_v2.py`。

## 9. clean_v8 近期验证判定

本轮 `clean_v8_largecap_recent` 将验证期收紧为 2026-05-01～2026-07-31，固定600样本，样本哈希为
`b54adb619ddcce54b5b0f7b8bac60f50640b5dda1f0d06499add7137cd42e423`。评测包含官方基线、两个父模型
和全部已保存 continuation checkpoint，推理参数统一为 `sample_count=8, T=0.5, top_p=0.9`。

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | 晋级 |
|---|---:|---:|---:|---:|---|
| fullv3 epoch 2 | 0.1134 | 0.1020 | 53.33% | 0.0465 | 否，Bootstrap CI跨0 |
| fullv3 epoch 1 | 0.1104 | 0.0966 | 53.17% | 0.0466 | 否 |
| full_small_v3 父模型 | 0.1091 | 0.1100 | 53.33% | 0.0467 | 父基线 |
| v3-cont epoch 3 | 0.0135 | 0.0622 | 47.83% | 0.0492 | 否 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 官方基线 |

`fullv3 epoch 2` 是本轮候选中最值得进入未来 OOS 的模型，但相对官方基线的 RankIC 配对统计
仍未通过，因此只能标记为“近期开发验证候选”，不能切换生产或称为严格 OOS 胜者。v3-cont
路线在近期验证期明显落后，停止继续训练。

## 10. 2026-08-06 batch-1 Confirm 判定

第一批新增候选：`fullv3_ep3cont_best`（fullv3 epoch 2 续跑 1 epoch）与两个 SFF 平滑微调臂
（α=0.85）。固定 600 样本、`sample_count=8, T=0.5`，样本哈希 `b54adb…`。

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | 晋级 |
|---|---:|---:|---:|---:|---|
| **fullv3_ep3cont_best** | **0.1193** | **0.1097** | **53.33%** | **0.0463** | **是** |
| fullv3 epoch 2 | 0.1134 | 0.1020 | 53.33% | 0.0465 | 否 |
| full_small_v3 父模型 | 0.1091 | 0.1100 | 53.33% | 0.0467 | 父基线 |
| sff_fullv3 best | -0.0163 | -0.0042 | 48.33% | 0.0594 | 否 |
| sff_v3cont best | -0.0290 | -0.0476 | 49.17% | 0.0596 | 否 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 官方基线 |

`fullv3_ep3cont_best` 同时满足五项 v2 门槛：RankIC 增量 `+0.1839`（≥0.02）、配对 Bootstrap
`p=0.0868`（<0.10）、方向率不低于官方-0.02、MAE 更低、Top5 超额为正。分析页完整 600 样本
sc16 复核同样通过（DirAcc 53.50% vs 48.17%，Pooled RankIC 0.1122 vs -0.0711）。

参考基线警示：动量 5 日简单基线 Pooled RankIC 为 `0.1674`、方向率 `58.83%`，高于所有 Kronos
候选；因此“通过开发 Confirm”只代表相对官方基线有统计改善，不代表相对简单策略已证明经济有效。
经济结论仍需含成本、换手和交易约束的 Qlib 回测与严格 OOS。

SFF 两个臂验证损失未收敛回父模型（3.3158/3.4105 vs 3.05/2.96），Confirm 明显落后，按停止
规则关闭该路线；后续不再对该起点追加 epoch。

## 11. 2026-08-07 batch-2 tokenizer 两阶段判定

tokenizer（LR 2e-4、2 epoch）与 predictor（父=fullv3_ep3cont_best + 微调 tokenizer、LR 5e-7、
3 epoch）均全程 DirectML GPU 完成。600 样本 Confirm（sc8/T0.5）：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | 晋级 |
|---|---:|---:|---:|---:|---|
| fullv3_ep3cont_best | **0.1193** | **0.1097** | 53.33% | **0.0463** | **是** |
| fttok_predictor best | 0.0906 | 0.0667 | 53.33% | 0.0495 | 否 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 基线 |

`fttok_predictor_best` 相对官方 RankIC 增量 `+0.1552`，但配对 Bootstrap `p=0.2687` 未过
`p<0.10` 门槛；MAE 改善 CI `[-0.0215, -0.0005]` 稳定但不单独晋级。结论：tokenizer 两阶段
未超过 predictor-only 路线，不切换生产；生产 junction 保持 `v3-cont epoch_2`。

## 12. 2026-08-07 batch-3 fast_recipe 判定

新配方（batch 32 + accum 4 + 窗口预计算 + AdamW foreach=False + 4096 步/轮 = 2 倍数据）训练的
`fast_recipe_best` 通过五项 v2 门槛（相对官方 Bootstrap `p=0.0744`、MAE CI 不含 0），
Pooled RankIC 0.1283 超过父线 fullv3_ep3cont_best（0.1193）。该配方定为新默认训练配方；
`fast_recipe_best` 列为下一轮严格 OOS 首要候选；生产 junction 保持 `v3-cont epoch_2`。
注意：DML 实测 batch 128 因每步同步开销主导而更慢（2.5s/步，51 samples/s），不采用大 batch。

相关入口：[当前模型状态](MODEL_STATUS.md) · [数据规范](DATASET_SPEC.md) ·
[评测历史](../history/EVALUATION_RESULTS.md)

## 13. 2026-08-07 pred_len=10 对齐判定

按用户决定，运行/评测/训练三链路统一为 `pred_len=10`（对齐上游微调 `predict_window=10`）。
新 manifest `evaluation_manifest_largecap_v8_recent_pred10.json`、新固定 600 样本
`evaluation_samples_pred10.json`（哈希 `a419b8b9…`）；pred_len=5 结果（第 9~12 节）存档。
完整证据见 [`ALIGNMENT_REPORT_2026-08.md`](../history/plans/ALIGNMENT_REPORT_2026-08.md)。

### 13.1 正式 Confirm（pred_len=10、sc8、T=0.5、Bootstrap 5,000）

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | Top5 超额 | v2 门槛 |
|---|---:|---:|---:|---:|---:|---|
| 生产 v3-cont epoch_2 | **0.1286** | 0.1056 | 53.33% | 0.0715 | −0.0030 | 未通过（p=0.736，Top5<0） |
| fullv3_ep3cont_best | 0.0675 | 0.1378 | **56.00%** | 0.0735 | +0.0303 | 未通过（RankIC 增量<+0.02） |
| fast_recipe_best | 0.0630 | 0.1335 | 56.00% | 0.0736 | +0.0011 | 未通过（RankIC 增量<+0.02） |
| 官方 Kronos-small | 0.0790 | 0.0550 | 50.50% | 0.1077 | −0.0016 | 基线 |

### 13.2 T 决策（G-A）

T=1.0 在 5 标的同日对比中区间宽度中位数 1.68×（≥1.5）、上行概率更分散，150 样本诊断
（pred_len=10）生产模型 RankIC 0.2035 vs 官方 0.0800、DirAcc 53.3% vs 50.0%，满足 (a)(b)；
但 600 样本 T=1.0 Confirm 三个候选配对 Bootstrap p=0.67~0.82 未达 p<0.10，v2 门槛未通过 →
**协议温度维持 0.5**。T=1.0 记录为概率语义更优的候选参数，待严格 OOS 周期积累后复评。

### 13.3 复权决策（G-B）

A 股 qfq vs 不复权中位收盘差异 2.4%~3.4%（除息量级）、预测方向一致 → 保持 qfq；同时修复
BaoStock `adjustflag` 映射 bug（1=后复权、2=前复权、3=不复权）。港股 yfinance vs AKShare qfq
对比因 Yahoo 限流待重试。

### 13.4 结论

pred_len=10 协议下无候选通过 v2 门槛；生产 junction 保持 `v3-cont epoch_2`；训练模板固化
`predict_window=10`，v8 系（predict 5）候选仅作诊断参考；4x 训练暂停，恢复列为独立事项。
评测明细：`output/eval_pred10_600/`、`output/eval_pred10_600_t05/`。
