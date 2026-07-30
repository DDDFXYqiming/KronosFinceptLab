# Kronos 紧凑微调与评测报告

> 文档状态：Current
> 最后核对：2026-07-30
> 当前状态：紧凑数据、三模型训练和验证集 screen/confirm 均已完成；本轮停止并保留官方预训练基线

## 当前实验问题

本轮只回答：

> A/H 股近四年数据上的简单低学习率微调，能否稳定超过官方预训练 `Kronos-small`？

旧的“训练截至 2024、2025 验证、2026 诊断”实验在 M1 约完成 5.2% 时停止。该日志保留，
但部分权重不进入候选列表。

## 固定三模型

三个模型互相独立，均从官方预训练 `Kronos-small` 开始，不继承 full/V2/V3/cont。
tokenizer 固定为官方 `Kronos-Tokenizer-base`。

| 模型 | 学习率 | 采样 | epoch | 输出目录 |
|---|---:|---|---:|---|
| M1 / `compact_m1` | 1e-6 | window uniform | 1 | `finetuned_compact_m1` |
| M2 / `compact_m2` | 5e-6 | window uniform | 1 | `finetuned_compact_m2` |
| M3 / `compact_m3` | 5e-6 | market/stock balanced | 1 | `finetuned_compact_m3` |

共同设置：`clean_v5_compact`、seed 42、lookback 90、predict 5、训练日期
2022-01-01～2025-12-31、验证日期 2026 Q1。

训练结果：

| 模型 | Training Loss | Validation Loss | 耗时 |
|---|---:|---:|---:|
| `compact_m1` | 3.0850 | 3.1122 | 91.58 分钟 |
| `compact_m2` | 3.0281 | 3.0486 | 82.98 分钟 |
| `compact_m3` | 3.0854 | 3.0502 | 84.29 分钟 |

Validation Loss 只用于确认训练正常，不作为金融预测模型排名依据。

## 运行时输入窗口（开发记录：2026-07-30）

分析页和预测页统一使用最近 90 根日线作为 Kronos 模型输入。预测页可以继续获取并展示完整的近一年历史数据，
但发送给模型的 `rows` 只取末尾 90 根；分析页同样只构造末尾 90 根的预测请求。这样可以与当前紧凑微调的
`lookback=90` 训练窗口、滚动评测窗口保持一致，也避免把页面展示区间误当成模型上下文。

这是一项运行时契约，不是永久固定的模型参数。后续若新的微调模型采用不同的 lookback 或经过新的评测协议确认，
必须同步更新两个页面，并以同一套生产路径评测结果重新确认输入窗口；在此之前不得仅根据上游通用示例的 240/400 根
历史数据调整默认值。

```powershell
\.venv311\Scripts\python.exe examples\run_simple_training.py
```

## 数据与评测清单

初始 `clean_v5_compact`：

| 项目 | 数量 |
|---|---:|
| 文件 | 497 |
| A 股 / 港股 | 395 / 102 |
| 训练区间行 | 478,368 |
| 验证区间行 | 28,176 |
| 诊断区间行 | 39,969 |
| 严格未来 OOS 行 | 0 |

评测固定选择 200 A 股和 100 港股：

| fold | 样本数 | A / HK | 角色 |
|---|---:|---:|---|
| `validation_2026_q1` | 1,749 | 1,172 / 577 | screen/confirm |
| `diagnostic_2026_04_07` | 2,366 | 1,595 / 771 | 近期诊断 |

当前实际数据截止 2026-07-29。2026-07-31 尚未发生，
manifest 会记录实际 `observed_data_end`，不会伪造未来数据。

## 历史模型处理

以下旧模型进入同一 150 样本 screen，但只作独立候选：

- `full_small_v3`
- `v3_from_ftv1`
- `v3_from_ftv1_cont`
- `v3_small_cont2`

它们不与新模型接续训练。只有在相同协议下通过 600 样本确认的模型，才可能成为后续
continuation 父模型；继续训练必须使用新增或明显改善的数据，并同时超过继续训练前的冠军。

## 2026 Q1 验证集结果

本轮结果写入 `output/evaluation_compact_v5`，与旧版 `output/evaluation` 隔离。
Screen 使用固定 150 个不重叠样本、`sample_count=1`。

| 模型 | Screen DirAcc | Screen MeanDailyRankIC | Score | Confirm |
|---|---:|---:|---:|---|
| pretrained_small | 50.00% | 0.0135 | 0.5027 | 基线，已确认 |
| compact_m1 | 43.33% | -0.1299 | 0.4340 | 未通过 screen |
| compact_m2 | 46.67% | -0.1356 | 0.4529 | 未通过 screen |
| compact_m3 | 45.33% | -0.1039 | 0.4512 | 未通过 screen |
| full_small_v3 | 49.33% | 0.0098 | 0.4980 | 未通过 screen |
| v3_from_ftv1 | 57.33% | 0.1081 | 0.5656 | 通过 screen，非第一名 |
| v3_from_ftv1_cont | 60.00% | 0.1795 | 0.5959 | Screen 第一名，已确认 |
| v3_small_cont2 | 59.33% | 0.1740 | 0.5908 | 通过 screen，非第一名 |

600 样本确认结果：

| 模型 | Confirm DirAcc | Confirm MeanDailyRankIC | Score |
|---|---:|---:|---:|
| pretrained_small | 48.83% | -0.1336 | 0.4663 |
| v3_from_ftv1_cont | 53.67% | 0.0300 | 0.5280 |

确认阶段分市场结果：

| 模型 | 市场 | 样本 | DirAcc | MeanDailyRankIC | Score |
|---|---|---:|---:|---:|---:|
| pretrained_small | A 股 | 400 | 49.50% | 0.0449 | 0.5060 |
| pretrained_small | 港股 | 200 | 47.50% | -0.2408 | 0.4368 |
| v3_from_ftv1_cont | A 股 | 400 | 55.50% | 0.1872 | 0.5704 |
| v3_from_ftv1_cont | 港股 | 200 | 50.00% | -0.0643 | 0.4871 |

候选 Score 增量为 `+0.0617`，按目标结束日期配对的 500 次 Bootstrap 95% CI 为
`[-0.0174, 0.1548]`。虽然点估计同时超过基线，但置信区间下界不大于 0，没有满足冻结的
晋级规则。

## 本轮结论与停止决定

当前证据不能证明 A/H 股简单低学习率微调能够**稳定**超过官方预训练基线：

- M1/M2/M3 在 150 样本 screen 中全部低于基线；
- 历史 `v3_from_ftv1_cont` 在 600 样本点估计中领先，但优势未通过配对 Bootstrap；
- 按协议保留官方 `Kronos-small`，不运行 2026-04～07 诊断评测；
- 不追加 epoch、学习率、temperature 或 continuation 搜索；
- 下一轮只允许改善数据质量，然后原样重复同一实验；在此之前不选择新的 continuation 父模型。

## 大盘股开发实验（已完成）

上一节规划的 A/H 大盘股开发实验已经执行完成。两条训练线使用同一份
`clean_v6_largecap`、同一 tokenizer、`lookback=90`、`predict_window=5`、1 epoch 和
`learning_rate=1e-6`，只改变 predictor 的初始化权重。结果写入
`output/evaluation_largecap_v1`。

- `largecap_l1`：从官方 `Kronos-small` 起点训练 1 epoch；
- `largecap_l2_v3cont`：从 `v3_from_ftv1_cont` 起点训练 1 epoch；
- 两者使用相同的 2022～2025 训练窗口、2026 Q1 验证折和 A/H 大盘股评测样本；
- 没有模型通过配对 Bootstrap 晋级时，停止当前 small 微调路线，不继续搜索局部参数。

| 模型 | 初始化 | 训练状态 | Screen Score | Confirm Score |
|---|---|---|---:|---:|
| `pretrained_small` | 官方 Kronos-small | 基线 | 0.5156 | 0.4731 |
| `largecap_l1` | 官方 Kronos-small | 已完成 | 0.5219 | 0.5066 |
| `largecap_l2_v3cont` | `v3_from_ftv1_cont/best_model` | 已完成 | 0.5627 | 0.5115 |

L1 在 600 样本确认中相对官方基线的综合分增量为 `+0.0335`，500 次配对 Bootstrap
95% 置信区间为 `[-0.0007, 0.0747]`。L2 在 150 样本 screen 中明显领先，但在 600 样本确认中
相对官方基线的综合分增量为 `+0.0383`，置信区间为 `[-0.0560, 0.1416]`。两者的区间下界都不
大于 0，因此均没有通过冻结晋级规则。

当前决定：保留官方 `Kronos-small`，不运行本轮 2026-04～07 诊断测试，不追加 epoch、学习率、
temperature 或新的 continuation 模型。后续若继续推进，只允许改善股票池和数据质量后原样重跑
这两条训练线。

当前结果说明：将训练对象收敛到大盘股后，旧微调权重可以带来局部提升，但目前仍不能证明微调
模型稳定优于官方模型。

当前已准备好下一轮开发训练输入：

| 项目 | 值 |
|---|---:|
| 数据集 | `clean_v6_largecap_dev` |
| 股票文件 | 399（A 股 297、港股 102） |
| 训练窗口 | 346,503 |
| 验证窗口 | 18,708 |
| L1 训练配置 | `external/Kronos/finetune_csv/configs/config_largecap_l1.yaml` |
| L2 训练配置 | `external/Kronos/finetune_csv/configs/config_largecap_l2_v3cont.yaml` |
| 评测 manifest | `output/evaluation_manifest_largecap_v6_dev.json` |

该数据集已经通过训练器读取验收，但仍标记为 `development_only`：A 股是当前 CSI300
快照，港股是已有高流动性候选，尚未具备完整历史时点成分。因此它可以开始开发训练，不能
用于严格 OOS 或生产收益宣称。

完整晋级和停止规则见 [`EVALUATION_PROTOCOL.md`](EVALUATION_PROTOCOL.md)。
