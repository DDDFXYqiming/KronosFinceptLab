# Kronos 评测结果时间线

> 文档状态：Historical summary
> 当前标准见：[EVALUATION_STANDARD](../current/EVALUATION_STANDARD.md)
> 当前冠军见：[MODEL_STATUS](../current/MODEL_STATUS.md)

## 口径演进

| 时期 | 数据/样本 | 主要指标 | 历史结论 | 当前可用性 |
|---|---|---|---|---|
| 早期裸模型评测 | 4131 个高度重叠窗口 | 归一化空间 loss、方向准确率 | 出现 87.7% | **作废**：未走 tokenizer、自回归和反归一化完整链路 |
| 早期生产链路 | 30～130 股，约 150/650 样本 | DirAcc、混合 IC/RankIC、简化 AER/IR | v3-cont 系列表现较好 | 仅历史诊断，样本与经济口径不完整 |
| legacy 150 排名 | 20 A + 10 HK | 方向、IC、RankIC、AER/IR | v3-cont epoch 2 约 60% 方向率 | 小样本，不用于当前晋级 |
| compact v5 v1 | 600 样本 | 综合 Score + MeanDaily RankIC | v3-cont 点估计领先但 Bootstrap 未通过 | 历史 v1 决策 |
| largecap v1 | 600 样本 | 综合 Score + MeanDaily RankIC | L1/L2 点估计提升，CI 下界未过 0 | 历史 v1 决策 |
| 生产参数诊断 | 固定 150，`sc=8/16,T=0.5` | 项目真实调用参数 | 当前 epoch 2 同场超过 L2 | 支持运行时选择，但不是 Confirm/OOS |
| **统一 v2 Confirm** | **同一 600 样本** | **Pooled RankIC + 逐期 RankIC + 方向 + MAE** | **epoch 2 唯一通过** | **当前开发选模依据** |
| clean_v7 PIT Confirm | 595 个历史成分约束样本 | 同一 v2 指标与配对统计 | v7 epoch 1 未超过父模型，三者 Pooled RankIC 均为负 | 当前停止该 continuation 的依据 |

## 最新统一 v2 结果

| 排名 | 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE |
|---:|---|---:|---:|---:|---:|
| 1 | **v3-cont epoch 2** | **0.1076** | **0.1544** | **53.00%** | 0.0511 |
| 2 | largecap L2 | 0.0855 | 0.0173 | 51.33% | 0.0504 |
| 3 | v3-cont best_model | 0.0796 | 0.0579 | 52.00% | 0.0524 |
| 4 | largecap L3 best_model | 0.0629 | 0.1271 | 52.00% | 0.0505 |
| 5 | full_small_v3 | 0.0325 | 0.1269 | 51.50% | **0.0447** |
| 6 | 官方 Kronos-small | -0.0034 | -0.0696 | 50.33% | 0.0609 |

统一条件：`clean_v6_largecap`、2026 Q1 validation、600 样本、`pred_len=5`、`sample_count=1`、
`temperature=0.3`、`top_p=0.9`、seed 42。样本哈希为
`9e93c4b8b708e0297ca19508bf695c5784cf640df88f981dd7bac548689be593`。

原始预测：`output/evaluation_v2_unified/confirm/`；统一统计：
`output/evaluation_v2_unified/comparison_report.json`。

## clean_v7 PIT 复核

统一条件：`clean_v7_largecap`、2026 Q1 validation、595 样本、`sample_count=1`、`T=0.3`、
`top_p=0.9`、seed 42；样本哈希
`45d8b47b66890ab945aa64dcba91a02fc76ac85144050766fad20151a9ce61d2`。

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE |
|---|---:|---:|---:|---:|
| v7 epoch 1 | -0.0481 | 0.0196 | 48.57% | **0.0504** |
| 父模型 v3-cont epoch 2 | -0.0506 | 0.0057 | 48.74% | 0.0518 |
| 官方 Kronos-small | -0.0596 | **0.0893** | **49.08%** | 0.0586 |

v7 epoch 1 相对父模型的 Pooled RankIC 增量为 `+0.0025`，配对 Bootstrap 95% CI
`[-0.0512, 0.0682]`，`p=0.9358`；没有通过 continuation 晋级门槛。原始预测与统计位于
`output/evaluation_v7_pit/`。

## 2026-08-06 生产参数固定横截面复核

当前标准改为固定 600 个市场/目标日期横截面，预测页参数为 `sample_count=8, T=0.5`。七个模型
同场后，`full_small_v3` 的方向率点估计最高（50.83%）且 MAE 最低（0.0424），但 RankIC 增量
Bootstrap 区间跨 0；其完整600样本 `sample_count=16`方向率为48.83%，也没有超过官方49.50%。

业务收益率信号的成本后周期 Top20% 诊断中，largecap L2 点估计最高；严格上游标准化 `last`
信号下 largecap L3 点估计最高，但所有候选相对官方的配对区间均跨0。没有模型晋级，生产
junction 保持 `v3-cont epoch_2`。详见
[`当前评测标准`](../current/EVALUATION_STANDARD.md) 和 `output/evaluation_v3_production/`。

## clean_v8 近期 Confirm（2026-08-06）

统一条件：`clean_v8_largecap_recent`，训练至 2026-04-30，验证期 2026-05-01～2026-07-31，固定
600 样本，`sample_count=8`、`T=0.5`、`top_p=0.9`、seed 42；样本哈希为
`b54adb619ddcce54b5b0f7b8bac60f50640b5dda1f0d06499add7137cd42e423`。

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | 相对官方结论 |
|---|---:|---:|---:|---:|---|
| fullv3 epoch 2 | **0.1134** | 0.1020 | **53.33%** | **0.0465** | 点估计最佳，未通过统计 |
| fullv3 epoch 1 | 0.1104 | 0.0966 | 53.17% | 0.0466 | 未通过统计 |
| full_small_v3 父模型 | 0.1091 | **0.1100** | 53.33% | 0.0467 | 研究父基线 |
| v3-cont epoch 3 | 0.0135 | 0.0622 | 47.83% | 0.0492 | 未通过 |
| v3-cont epoch 2 | 0.0118 | 0.0588 | 47.83% | 0.0492 | 未通过 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 官方基线 |

`fullv3 epoch 2` 相对官方的 Pooled RankIC 增量为 `+0.1780`，5,000 次配对 Bootstrap 95% CI 为
`[-0.0289, 0.4058]`，`p=0.1008`，因此没有通过当前晋级标准。A 股 Pooled RankIC 为 `0.1477`，
港股为 `0.0314`；结果说明近期提升主要由 A 股贡献，不能直接外推到港股。原始结果和统计报告位于
`output/evaluation_v8_recent/`。

## 阅读历史结果的规则

- 87.7%、58%、60% 和 53% 来自不同管线与样本，不能横向拼表；
- 早期 `58%` 的五日配置实际把第 5 日预测与第 10 日真实收盘比较，且窗口高度重叠、未固定
  随机种子，现明确作废；
- `60%` 是 150 样本 Screen，扩大到 600 样本后为 53.67%，不再作为当前模型能力上限；
- `best_model` 表示最低 validation loss，不自动表示预测指标最佳；
- 150 样本只用于 screen/诊断，600 样本才用于当前 Confirm；
- 2026 Q1 已参与选模，不是严格 OOS；
- 无成本 TopK/AER/IR 不是正式交易回测。

详细旧表见 [2026-07 实验长日志](EXPERIMENT_LOG_2026-07.md) 和
[早期原始报告](LEGACY_REPORT.md)。

## 2026-08-06 batch-1 Confirm（clean_v8，600 样本 sc8）

统一条件：`clean_v8_largecap_recent`、固定 600 样本、`sample_count=8`、`T=0.5`、`top_p=0.9`、
seed 42；样本哈希 `b54adb619ddcce54b5b0f7b8bac60f50640b5dda1f0d06499add7137cd42e423`。
新增候选为 fullv3 epoch 2 续跑 1 epoch（`fullv3_ep3cont_best`）与两个 SFF 平滑微调臂；同时加入
动量 5 日与 90 日低波动率两个无需推理的简单基线作参考。完整结果位于
`output/evaluation_batch1/`。

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| momentum_5d（参考基线） | **0.1674** | 0.0275 | **58.83%** | 0.0592 | 参考 |
| **fullv3_ep3cont_best** | **0.1193** | **0.1097** | 53.33% | **0.0463** | **是** |
| fullv3 epoch 2 | 0.1134 | 0.1020 | 53.33% | 0.0465 | 否 |
| fullv3 epoch 1 | 0.1104 | 0.0966 | 53.17% | 0.0466 | 否 |
| full_small_v3 父模型 | 0.1091 | 0.1100 | 53.33% | 0.0467 | 否 |
| vol_low_90d（参考基线） | 0.1056 | 0.1184 | 48.67% | 0.0478 | 参考 |
| v3-cont epoch 3 | 0.0135 | 0.0622 | 47.83% | 0.0492 | 否 |
| v3-cont epoch 2 | 0.0118 | 0.0588 | 47.83% | 0.0492 | 否 |
| sff_fullv3 best | -0.0163 | -0.0042 | 48.33% | 0.0594 | 否 |
| v3-cont epoch 2 生产父 | -0.0164 | 0.0567 | 47.50% | 0.0497 | 否 |
| sff_v3cont best | -0.0290 | -0.0476 | 49.17% | 0.0596 | 否 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 基线 |

`fullv3_ep3cont_best` 相对官方：Pooled RankIC 增量 `+0.1839`，5,000 次按市场×目标日期配对
Bootstrap 95% CI `[-0.0234, 0.4131]`、`p=0.0868`；逐期配对 t 检验 `p=0.1511`（10 期）；MAE
增量 CI `[-0.0232, -0.0055]`。分市场 A 股 Pooled RankIC `0.1498`、港股 `0.0420`，提升仍以
A 股为主。

结论：`fullv3_ep3cont_best` 是 clean_v8 上第一个通过 v2 开发 Confirm 的 checkpoint；但动量 5 日
简单基线的 Pooled RankIC（0.1674）高于所有 Kronos 候选，说明排序优势必须与简单基线一起解释，
不能单独宣称策略有效。两个 SFF 臂均明显落后各自父模型，SFF 路线在本项目固定低 LR 3 epoch 配方
下未复现论文结果，已按停止规则关闭。

### 分析页 sc16 复核（600 样本）

`sample_count=16, T=0.5`，同一样本哈希：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| fullv3_ep3cont_best | 0.1122 | 0.1016 | **53.50%** | **0.0463** | **是** |
| 官方 Kronos-small | -0.0711 | -0.0466 | 48.17% | 0.0600 | 基线 |

### Top20% 周期成本诊断（开 0.1% / 平 0.15%，10 个非重叠 5 日周期）

| 配置 | fullv3_ep3cont_best 净超额/期 | 官方净超额/期 | 增量 95% CI |
|---|---:|---:|---|
| sc8 业务收益信号 | +0.0137（胜率 70%） | -0.0074 | [-0.0042, 0.0511] |
| sc8 上游 last 信号 | +0.0124 | -0.0046 | [-0.0057, 0.0431] |
| sc16 业务收益信号 | +0.0136（胜率 70%） | -0.0106 | **[0.0040, 0.0476]** |
| sc16 上游 last 信号 | +0.0108 | -0.0071 | [-0.0022, 0.0412] |

仅 sc16 业务收益信号的配对 CI 不含 0；该指标仍是上游对齐诊断，不是含换手/涨跌停/滑点的完整
Qlib 回测。

## 2026-08-07 batch-2 Confirm：tokenizer 两阶段

tokenizer 在 clean_v8 上微调（LR 2e-4、2 epoch、val loss 0.0094），predictor 从
`fullv3_ep3cont_best` 出发使用微调 tokenizer（LR 5e-7、3 epoch、best val 3.3037）。固定 600
样本、`sample_count=8, T=0.5`，样本哈希 `b54adb…`：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| fullv3_ep3cont_best | **0.1193** | **0.1097** | 53.33% | **0.0463** | **是** |
| fttok_predictor best | 0.0906 | 0.0667 | 53.33% | 0.0495 | 否 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 基线 |

`fttok_predictor_best` 相对官方：RankIC 增量 `+0.1552`，配对 Bootstrap 95% CI
`[-0.0966, 0.4263]`、`p=0.2687`；MAE 增量 CI `[-0.0215, -0.0005]` 稳定改善但不足以单独晋级。
分市场同样以 A 股为主。结论：tokenizer 两阶段在 clean_v8 上未超过 predictor-only 的
`fullv3_ep3cont_best`，按决策门不切换生产。原始结果：`output/evaluation_batch2/`。
