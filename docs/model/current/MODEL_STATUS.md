# Kronos 当前模型状态

> 文档状态：Current
> 最后核对：2026-08-07
> 当前生产权重：`v3_from_ftv1_cont / epoch_2`（最新评测没有产生可晋级替代者）
> 协议版本：pred_len=10（2026-08-07 起；pred_len=5 结果存档）

## 生产权重

```text
external/Kronos-small
  -> external/Kronos/finetune_csv/finetuned_v3_fromFTv1_cont/basemodel/epoch_2
```

`.env` 仍使用 `KRONOS_MODEL_ID=NeoQuasar/Kronos-small`，本地 junction 让预测服务加载上述微调
权重。官方未微调模型在评测时必须使用 HuggingFace 缓存 snapshot，不能把该 junction 误当基线。

预测页和分析页统一使用最近 90 根日线、预测未来 10 日、`temperature=0.5`、`top_p=0.9`；预测页
通常 `sample_count=8`，分析页单资产通常为 16、多资产为 8。

## 2026-08-07 pred_len=10 对齐与 Confirm 结果

按用户决定将 pred_len 统一为 10（对齐上游微调 `predict_window=10`），运行/评测/训练三链路
同步切换；完整证据见 [`ALIGNMENT_REPORT_2026-08.md`](../history/plans/ALIGNMENT_REPORT_2026-08.md)。
新固定 600 样本哈希 `a419b8b9…`（`evaluation_samples_pred10.json`），pred_len=5 的 b54adb…
结果存档不参与排名。

正式 Confirm（pred_len=10、sc8、T=0.5、Bootstrap 5,000）：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 门槛 |
|---|---:|---:|---:|---:|---|
| 生产 v3-cont epoch_2 | **0.1286** | 0.1056 | 53.33% | 0.0715 | 未通过 |
| fullv3_ep3cont_best | 0.0675 | 0.1378 | **56.00%** | 0.0735 | 未通过 |
| fast_recipe_best | 0.0630 | 0.1335 | 56.00% | 0.0736 | 未通过 |
| 官方 Kronos-small | 0.0790 | 0.0550 | 50.50% | 0.1077 | 基线 |

T 决策（G-A）：T=1.0 的样本多样性（区间宽度中位数 1.68×）与 150 样本诊断（RankIC 0.2035 vs
官方 0.0800）通过，但 600 样本配对统计 p=0.67~0.82 未过 v2 门槛 → 协议温度维持 0.5，T=1.0
记录为候选参数待严格 OOS 复评。

复权决策（G-B）：A 股 qfq vs 不复权中位收盘差异 2.4%~3.4% 且方向一致 → 保持 qfq；修复
BaoStock `adjustflag` 映射 bug（1=后复权、2=前复权、3=不复权）。港股 yfinance vs AKShare qfq
对比因 Yahoo 限流待重试。

**结论：无候选通过 v2 门槛，生产 junction 保持 `v3-cont epoch_2`；4x 训练暂停，恢复列为独立
事项；训练模板固化 `predict_window=10`，v8 系（predict 5）候选仅作诊断参考。**

## 最新生产参数同场结果

2026-08-06 使用固定市场/日期横截面重新评测。条件为 `clean_v7_largecap / validation_2026_q1`、
600 样本、`sample_count=8, T=0.5, top_p=0.9`，与预测页实际参数一致；样本哈希：

`7cfa257771d5496fc500eed3ece0b87d43b13b0c5f1cfdc35ac203bba93ee9ec`

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | 结论 |
|---|---:|---:|---:|---:|---|
| **full_small_v3** | **0.0043** | 0.0786 | **50.83%** | **0.0424** | 点估计第一，统计未通过 |
| v3-cont epoch 2（生产） | -0.0250 | 0.0713 | 49.33% | 0.0511 | 不替换、不追加训练 |
| largecap L3 | -0.0251 | **0.0823** | 49.67% | 0.0492 | 未通过 |
| 官方 Kronos-small | -0.0303 | -0.0083 | 49.00% | 0.0572 | 官方基线 |
| largecap L2 | -0.0314 | 0.0741 | 49.50% | 0.0505 | 未通过 |
| v7 epoch 1 | -0.0368 | 0.0731 | 50.33% | 0.0498 | 未通过 |
| v3-cont best_model | -0.0377 | 0.0471 | 49.33% | 0.0517 | 未通过 |

`full_small_v3` 的 MAE 改善具有稳定证据，但 RankIC、方向和成本后 Top-K 增量都没有通过配对
统计。分析页完整600样本 `sample_count=16` 也未晋级：它方向率 `48.83%`，官方为 `49.50%`。
严格按上游标准化 `last` 信号计算 Top20% 后，largecap L3 的成本后超额点估计最高，但相对官方
95% CI 仍跨0；分析页参数下 full_small_v3 的该信号点估计低于官方。
因此当前没有“已证明全面超过官方模型”的微调 checkpoint。

## 历史 clean_v6 同场结果

2026-08-05 在 `clean_v6_largecap / validation_2026_q1` 上重新评测官方模型和五个最强微调
checkpoint。固定 600 样本、`sample_count=1`、`temperature=0.3`、seed 42；样本哈希为
`9e93c4b8b708e0297ca19508bf695c5784cf640df88f981dd7bac548689be593`。

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 |
|---|---:|---:|---:|---:|---|
| **v3-cont epoch 2** | **0.1076** | **0.1544** | **53.00%** | 0.0511 | **通过** |
| largecap L2 | 0.0855 | 0.0173 | 51.33% | 0.0504 | 未通过统计门槛 |
| v3-cont best_model | 0.0796 | 0.0579 | 52.00% | 0.0524 | 未通过统计门槛 |
| largecap L3 best_model | 0.0629 | 0.1271 | 52.00% | 0.0505 | 未通过统计门槛 |
| full_small_v3 | 0.0325 | 0.1269 | 51.50% | **0.0447** | 未通过统计门槛 |
| 官方 Kronos-small | -0.0034 | -0.0696 | 50.33% | 0.0609 | 基线 |

冠军相对官方基线的 MeanDaily RankIC 配对检验 `p=0.0519`；A 股和港股 Pooled RankIC 分别为
`0.1005` 和 `0.1329`。Pooled RankIC 增量的 grouped Bootstrap 95% CI 仍包含 0，因此它是
开发 Confirm 冠军，不是已经完成严格 OOS 的生产收益证明。

## 当前决定

- 保持现有 `epoch_2` junction，不切换到训练时 `best_model`、L2 或 L3；
- `full_small_v3` 保留为低 MAE 研究候选，不因 128 样本约 62%方向率切换生产；
- 不在同一批数据上继续无限 continuation；L3 的验证损失改善没有转化为同场预测优势；
- 下一项模型工作是积累冻结后的前向 OOS；不再重复使用 2026 Q1 调参；
- 在完成持仓、成本、换手和交易限制回测前，不把开发 Top5/IR 称为策略收益。

## 2026-08-06 batch-1 开发 Confirm 结果

第一批执行 fullv3 收尾（`fullv3_ep3cont`：fullv3 epoch 2 续跑 1 epoch）与两个 SFF 平滑微调臂
（α=0.85，起点为 full_small_v3 与 v3-cont epoch 2）。固定 600 样本、`sample_count=8, T=0.5`，
样本哈希 `b54adb…`：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| **fullv3_ep3cont_best** | **0.1193** | **0.1097** | **53.33%** | **0.0463** | **是** |
| fullv3 epoch 2 | 0.1134 | 0.1020 | 53.33% | 0.0465 | 否 |
| full_small_v3 父模型 | 0.1091 | 0.1100 | 53.33% | 0.0467 | 否 |
| sff_fullv3 best | -0.0163 | -0.0042 | 48.33% | 0.0594 | 否 |
| sff_v3cont best | -0.0290 | -0.0476 | 49.17% | 0.0596 | 否 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 基线 |

`fullv3_ep3cont_best` 相对官方基线：Pooled RankIC 增量 `+0.1839`、配对 Bootstrap `p=0.0868`、
MAE 增量 CI `[-0.0232, -0.0055]`；分析页完整 600 样本 sc16 复核同样通过 v2 门槛（DirAcc
53.50% vs 48.17%）。Top20% 周期成本诊断在 sc16 业务收益信号下增量 CI `[0.0040, 0.0476]`
不含 0，其余配置跨 0。

两个 SFF 臂的验证损失（3.3158 / 3.4105）未收敛回父模型水平，Confirm 明显落后，SFF 路线在
本项目固定 LR 5e-7、3 epoch 配方下未复现论文结果，已停止。

## batch-1 决定

- `fullv3_ep3cont_best` 成为 clean_v8 首个通过开发 Confirm 的候选，列为下一轮严格 OOS 的
  首要研究候选；生产 junction 仍保持 `v3-cont epoch_2`，不因开发 Confirm 切换；
- 动量 5 日简单基线 Pooled RankIC（0.1674）高于全部 Kronos 候选，评测报告必须同时展示简单
  基线，排序优势不单独构成策略收益结论；
- 停止 SFF 路线；第二批转向 tokenizer 两阶段微调与 Qlib 正式回测。

## 2026-08-07 batch-2：tokenizer 两阶段结果

tokenizer（LR 2e-4、2 epoch、val 0.0094）+ predictor（父=fullv3_ep3cont_best、LR 5e-7、3 epoch、
best val 3.3037）在 clean_v8 上完成，600 样本 Confirm（sc8/T0.5）：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| fullv3_ep3cont_best | **0.1193** | **0.1097** | 53.33% | **0.0463** | **是** |
| fttok_predictor best | 0.0906 | 0.0667 | 53.33% | 0.0495 | 否（p=0.2687） |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 基线 |

结论：tokenizer 两阶段未超过 predictor-only 路线，生产 junction 保持 `v3-cont epoch_2` 不变；
`fullv3_ep3cont_best` 仍是下一轮严格 OOS 的首要研究候选。训练全程 DirectML GPU
（`Device: privateuseone:0`），DML 不支持 `torch.unique` 的边界已修复并记录
（`external/Kronos/model/module.py`，指标计算落 CPU、训练计算全 GPU）。

## 2026-08-07 batch-3：fast_recipe（更多数据配方）结果

新默认配方：`batch 32 + accum 4（有效 128）+ 窗口预计算 + AdamW foreach=False + 每轮 4096 步`
（13.1 万样本/轮，2 倍数据；实测 0.33s/步、每轮 24 分钟）。固定 600 样本 Confirm（sc8/T0.5）：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| **fast_recipe_best** | **0.1283** | **0.1319** | 52.67% | **0.0461** | **是** |
| fullv3_ep3cont_best（父） | 0.1193 | 0.1097 | 53.33% | 0.0463 | 是 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 基线 |

`fast_recipe_best` 是 clean_v8 当前开发 Confirm 点估计最佳 checkpoint（相对官方 Bootstrap
`p=0.0744`、MAE CI 不含 0），4/5 指标超过父线。决策：
- fast_recipe 配方定为项目新默认训练配方（batch 32 是 DML 实测最优；batch 128 因每步同步
  开销主导而更慢，已否决）；
- `fast_recipe_best` 取代 `fullv3_ep3cont_best` 成为下一轮严格 OOS 的首要研究候选；
- 生产 junction 仍保持 `v3-cont epoch_2`，等待严格 OOS 与 Qlib 回测。

## clean_v7 PIT continuation 结果

2026-08-05～06 从当前冠军 `v3-cont epoch_2` 出发，在 `clean_v7_largecap_pit` 上完成两个
完整 epoch。Epoch 3 运行中断且没有 checkpoint；由于后续 Confirm 未通过，按停止规则不再补跑。

| checkpoint | Train loss | Validation loss | 处理 |
|---|---:|---:|---|
| v7 epoch 1 | 2.7983 | 3.1053 | screen 第一名，进入 Confirm |
| v7 epoch 2 | 2.7807 | **3.0979** | validation loss 更低，但 screen Score/方向低于 epoch 1 |

固定 `clean_v7 / validation_2026_q1` Confirm 实际得到 595 个 PIT 样本，样本哈希为
`45d8b47b66890ab945aa64dcba91a02fc76ac85144050766fad20151a9ce61d2`：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 |
|---|---:|---:|---:|---:|---|
| v7 epoch 1 | -0.0481 | 0.0196 | 48.57% | **0.0504** | 未通过 |
| 当前父模型 v3-cont epoch 2 | -0.0506 | 0.0057 | 48.74% | 0.0518 | 基线/未通过 |
| 官方 Kronos-small | -0.0596 | **0.0893** | **49.08%** | 0.0586 | 官方基线 |

v7 epoch 1 相对父模型 Pooled RankIC 增量仅 `+0.0025`，5,000 次配对 Bootstrap 95% CI
`[-0.0512, 0.0682]`，双侧 `p=0.9358`。新数据训练改善了 MAE 点估计，但没有稳定改善排序或方向，
因此不进入近期诊断，也不替换生产权重。该结果同时再次证明 validation loss 下降不能替代预测评测。

## clean_v8 近期 continuation 结果

本轮使用 `clean_v8_largecap_recent`，训练区间为 2022-01-01～2026-04-30，验证区间为
2026-05-01～2026-07-31。固定600样本、`sample_count=8`、`T=0.5`、seed=42，样本哈希为
`b54adb619ddcce54b5b0f7b8bac60f50640b5dda1f0d06499add7137cd42e423`。

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | 结论 |
|---|---:|---:|---:|---:|---|
| fullv3 epoch 2 | **0.1134** | **0.1020** | **53.33%** | **0.0465** | 新验证集点估计最佳，统计未通过 |
| fullv3 epoch 1 | 0.1104 | 0.0966 | 53.17% | 0.0466 | 未通过统计门槛 |
| full_small_v3 父模型 | 0.1091 | 0.1100 | 53.33% | 0.0467 | 研究父基线 |
| v3-cont epoch 3 | 0.0135 | 0.0622 | 47.83% | 0.0492 | 未通过 |
| v3-cont epoch 2 | 0.0118 | 0.0588 | 47.83% | 0.0492 | 未通过 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 官方基线 |

`fullv3 epoch 2` 相对官方基线的 Pooled RankIC 增量点估计为 `+0.1780`，但配对 Bootstrap
的95% CI 为 `[-0.0289, 0.4058]`，双侧 `p=0.1008`；因此没有通过当前晋级门槛。相对官方的
Endpoint MAE 改善 CI 为 `[-0.0230, -0.0052]`，说明价格误差改善较稳定，但不能单独替代排序
和方向证据。A 股表现明显强于港股，不能把混合平均直接解释为两地市场都同样有效。

结论：`full_small_v3` continuation 是下一轮严格 OOS 的首要研究候选，但不切换生产；当前
生产权重仍为 `v3_from_ftv1_cont / epoch_2`，2026-08-01 后数据继续封存。

## 相关文档和证据

- [评测标准](EVALUATION_STANDARD.md)
- [评测流程](EVALUATION_PROTOCOL.md)
- [数据规范](DATASET_SPEC.md)
- [训练历史](../history/TRAINING_RESULTS.md)
- [评测历史](../history/EVALUATION_RESULTS.md)
- 原始结果：`output/evaluation_v2_unified/`
- v7 PIT 结果：`output/evaluation_v7_pit/`
- v8 recent Confirm：`output/evaluation_v8_recent/`
- 生产参数 v3 结果：`output/evaluation_v3_production/`
- 统一统计脚本：`examples/compare_evaluations_v2.py`
