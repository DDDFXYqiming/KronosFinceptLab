# Kronos 紧凑评测协议

> 文档状态：Current
> 最后核对：2026-08-05
> 当前选模指标与晋级门槛：[`EVALUATION_STANDARD.md`](EVALUATION_STANDARD.md)

## 时间和数据边界

当前 continuation 的统一数据为 `clean_v8_largecap_recent`，评测清单为
`output/evaluation_manifest_largecap_v8_recent.json`。`clean_v7_largecap` 的结果继续作为
父模型历史基准，但不同 manifest 的分数不直接拼接排名。

| 分区 | 日期 | 角色 |
|---|---|---|
| train | 2022-01-01～2026-04-30 | 模型训练 |
| validation | 2026-05-01～2026-07-31 | screen/confirm |
| diagnostic | 2026-08-01 起 | 冻结后近期诊断 |
| strict future OOS | 2026-08-01 起 | 真正前向检验 |

项目已经查看过 2026 结果，因此 2026 只能标记为开发验证/诊断。评测窗口使用 90 日输入、5 日
预测、5 bar embargo，`sample_step=10`，单只股票目标区间不重叠。训练与评测窗口都要求股票在
预测起点属于当时的 CSI300、HSI、HSCEI 或 HSTECH，成员进出日期来自 PIT sidecar。

生产页面的模型输入也遵循同一窗口契约：页面可以展示更长的历史数据，但 Kronos 请求统一截取最近 90 根。
分析页和预测页必须共用该规则；未来模型或微调协议变更时，先完成窗口消融和完整生产路径评测，再同步调整页面。

## 当前选模指标

v1 的 `0.60 × DirectionAccuracy + 0.40 × normalized MeanDailyRankIC` 综合分已降级为历史兼容
指标，不再作为当前排名依据。v2 以 Pooled RankIC 排名，同时强制报告逐期横截面 RankIC、A/H
分市场结果、方向准确率和终点收益 MAE，并使用按 `(market, target_end)` 的配对统计。完整定义、
限制和晋级门槛以 [`EVALUATION_STANDARD.md`](EVALUATION_STANDARD.md)
为准。

## 固定流程

| 模式 | 数据 | 样本 | 推理参数 | Bootstrap |
|---|---|---:|---|---:|
| smoke | validation | 16 | `sample_count=1, T=0.3` | 0 |
| confirm | validation | 固定 600 个市场/日期横截面 | `sample_count=8, T=0.5` | 5,000 次配对分组重采样 |
| final diagnostic | diagnostic | 全部不重叠窗口 | 冻结后的生产参数 | 1,000 |
| analysis audit | validation 固定样本 | 128（并对冠军补跑完整600） | `sample_count=16, T=0.5` | 200 |

Confirm 固定样本为 `configs/evaluation/evaluation_samples_v4.json`，样本哈希
`b54adb619ddcce54b5b0f7b8bac60f50640b5dda1f0d06499add7137cd42e423`。A 股选择 5 个目标日期、
每个日期 80 只，港股选择 5 个目标日期、每个日期 40 只，总计 600。样本按目标日期优先组织，
保证每个 `(market, target_end)` 都是可用的横截面，而不是把每只股票独立抽取的零散日期混在一起。

每轮必须包含官方 `Kronos-small`。150 样本 screen 只保留作历史记录，不再承担模型晋级；候选
数量在运行前人工限制为少量完整 checkpoint。历史模型作为独立候选，不同 manifest 的旧结果
不直接参与当前排名。

当评测 continuation checkpoint 时，Confirm 必须同时加入原父模型和官方基线。验证损失改善
不能替代固定 600 样本预测结果。若新 checkpoint 没有同时超过父模型和官方基线，立即停止该
continuation 路线，不追加 epoch 或参数搜索。

评测器按“有序 batch 的样本键 + 全局 seed”派生每个 batch 的独立随机种子。固定样本、固定
batch size 下，完整运行与断点恢复必须产生相同逐样本预测。评测结果记录 `rng_strategy`，正式
比较不允许改变 batch size。

分析页正式结论不能只依赖 128 样本审计；冠军与官方基线还需要在完整 600 样本上运行
`sample_count=16`。128 样本只用于快速检查概率采样是否退化。

上游 Kronos 的 `qlib_test.py` 使用 Top-K/Dropout、5 日持有和交易成本。当前固定窗口评测增加
Top20% 周期经济诊断，沿用其开仓 `0.1%`、平仓 `0.15%` 成本；由于没有逐日持仓延续、滑点、
涨跌停和市场冲击，该结果必须标记为“上游对齐诊断”，不能称为完整 Qlib 回测。
经济诊断同时报告项目业务使用的预测终点收益率信号，以及上游 `last` 定义对应的
`(pred_close - last_close) / context_close_std` 标准化信号。

## 执行入口

```powershell
.\.venv311\Scripts\python.exe examples\eval_rolling.py `
  --mode confirm `
  --manifest output\evaluation_manifest_largecap_v8_recent.json `
  --samples-file configs\evaluation\evaluation_samples_v4.json `
  --model-path <checkpoint 路径> `
  --tokenizer-path <Kronos-Tokenizer-base 路径> `
  --output output\evaluation_v7_pit\confirm\<model>.json `
  --device directml

.\.venv311\Scripts\python.exe examples\compare_evaluations_v2.py `
  --input-dir output\evaluation_v7_pit\confirm `
  --output output\evaluation_v7_pit\comparison_report.json `
  --bootstrap-replicates 5000
```

DirectML 只允许单进程顺序执行。评测器支持进度文件和中断恢复。诊断阶段只能在确认冠军后
运行；诊断结果不得返回验证阶段继续调参。

## 固定停止规则

- 不用无成本 AER/IR 诊断代替正式回测；
- 不搜索 temperature、sample_count、指标权重或新损失；
- 不无限追加 epoch、continuation 或第四个新模型；
- continuation 最多按预先配置的 epoch 执行一次；固定 Confirm 未超过父模型时停止；
- 没有候选通过时保留官方模型，下一轮只改数据；
- 严格 OOS 只从 2026-08-01 后新产生的数据积累。

相关入口：[当前模型状态](MODEL_STATUS.md) · [数据规范](DATASET_SPEC.md) ·
[评测历史](../history/EVALUATION_RESULTS.md)
