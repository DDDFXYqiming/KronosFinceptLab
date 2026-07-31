# Kronos 紧凑评测协议

> 文档状态：Current
> 最后核对：2026-07-31

## 时间和数据边界

当前数据为 `clean_v5_compact`，评测清单为
`output/evaluation_manifest_compact_v5.json`：

```powershell
\.venv311\Scripts\python.exe examples\prepare_clean_v5_compact.py
\.venv311\Scripts\python.exe examples\build_compact_eval_manifest.py
```

| 分区 | 日期 | 角色 |
|---|---|---|
| train | 2022-01-01～2025-12-31 | 模型训练 |
| validation | 2026-01-01～2026-03-31 | screen/confirm |
| diagnostic | 2026-04-01～2026-07-31 | 冻结后近期诊断 |
| strict future OOS | 2026-08-01 起 | 真正前向检验 |

项目已经查看过 2026 结果，因此 2026 只能标记为诊断。评测窗口使用 90 日输入、5 日预测、
5 bar 间隔，单只股票目标区间不重叠。

生产页面的模型输入也遵循同一窗口契约：页面可以展示更长的历史数据，但 Kronos 请求统一截取最近 90 根。
分析页和预测页必须共用该规则；未来模型或微调协议变更时，先完成窗口消融和完整生产路径评测，再同步调整页面。

## 唯一选模指标

```text
Score = 0.60 × DirectionAccuracy
      + 0.40 × ((MeanDailyRankIC + 1) / 2)
```

`MeanDailyRankIC` 按“市场 × 目标日期”计算横截面 Spearman RankIC，再取平均。禁止使用
混合日期的 pooled RankIC 选模。AER/IR 继续输出仅作历史兼容。

## 固定流程

| 模式 | 数据 | 样本 | sample_count | Bootstrap |
|---|---|---:|---:|---:|
| smoke | validation | 16 | 1 | 0 |
| screen | validation | 20 A + 10 HK，各 5 窗口，共 150 | 1 | 0 |
| confirm | validation | 80 A + 40 HK，各 5 窗口，共 600 | 1 | 500 |
| final diagnostic | diagnostic | 全部不重叠窗口 | 1 | 1,000 |
| production audit | diagnostic 固定样本 | 128 | 8 | 200 |

screen 同时比较：

- 官方 `Kronos-small`；
- 新的 `compact_m1/m2/m3`；
- 历史 `full_small_v3`、`v3_from_ftv1`、`v3_from_ftv1_cont`、
  `v3_small_cont2`。

历史模型只作为独立候选，不作为新模型父权重。候选必须同时满足 Score 更高、
DirectionAccuracy 不低于基线、MeanDailyRankIC 不低于基线。confirm 中配对日期 Bootstrap
的 Score 增量 95% CI 下界还必须大于 0；否则保留官方基线并停止。

当评测 continuation checkpoint 时，固定 screen 还必须加入原父模型作为比较对象。
只有新 checkpoint 同时超过父模型和官方基线，才允许进入 600 样本 confirm；验证损失改善
不能替代预测 screen 的晋级条件。若所有 checkpoint 都未超过父模型，立即停止该 continuation
路线，不追加 epoch 或参数搜索。

## 执行入口

```powershell
\.venv311\Scripts\python.exe examples\eval_pipeline.py `
  --phase screen `
  --manifest output\evaluation_manifest_compact_v5.json `
  --tokenizer-path <Kronos-Tokenizer-base 路径>

\.venv311\Scripts\python.exe examples\eval_pipeline.py `
  --phase confirm `
  --manifest output\evaluation_manifest_compact_v5.json `
  --tokenizer-path <Kronos-Tokenizer-base 路径>
```

DirectML 只允许单进程顺序执行。评测器支持进度文件和中断恢复。诊断阶段只能在确认冠军后
运行；诊断结果不得返回验证阶段继续调参。

## 固定停止规则

- 不用 AER/IR 选模；
- 不搜索 temperature、sample_count、指标权重或新损失；
- 不无限追加 epoch、continuation 或第四个新模型；
- continuation 最多按预先配置的 epoch 执行一次；checkpoint screen 未超过父模型时停止；
- 没有候选通过时保留官方模型，下一轮只改数据；
- 严格 OOS 只从 2026-08-01 后新产生的数据积累。
