# Kronos 模型文档中心

> 文档状态：Current

## 现在应该看什么

1. [当前模型状态](current/MODEL_STATUS.md)：冠军、生产路径和仍未完成的验证；
2. [评测标准](current/EVALUATION_STANDARD.md)：指标、统计检验和晋级条件；
3. [评测流程](current/EVALUATION_PROTOCOL.md)：固定样本、时间划分和执行命令；
4. [数据规范](current/DATASET_SPEC.md)：训练/验证/诊断数据来源与限制。

以上四份文档是当前模型工作的唯一决策入口。历史文件中的“最佳”“当前默认”和高准确率仅表示
当时口径，不得覆盖当前结论。

## 历史追溯

| 入口 | 内容 |
|---|---|
| [训练历史](history/TRAINING_RESULTS.md) | 从环境试跑到 L4 的所有训练产物 |
| [评测历史](history/EVALUATION_RESULTS.md) | 旧归一化评测、生产路径评测、v1 和 v2 |
| [2026-07 实验长日志](history/EXPERIMENT_LOG_2026-07.md) | compact、largecap、L1/L2/L3 过程明细 |
| [2026-08 实验长日志](history/EXPERIMENT_LOG_2026-08.md) | batch-1：fullv3 收尾与 SFF 双臂 |
| [早期原始报告](history/LEGACY_REPORT.md) | 最早 full/v2/v3 过程，保留原文 |
| [历史计划](history/plans/README.md) | 已结束的数据质量和微调修复计划 |

## 当前结论

截至 2026-08-06，统一 600 样本 v2 Confirm 的冠军仍是
`finetuned_v3_fromFTv1_cont/basemodel/epoch_2`。当前 `external/Kronos-small` junction 已指向
该权重。最新 clean_v8 近期验证中，`full_small_v3` continuation 的 epoch2 点估计优于官方基线和
当前 v3-cont，但配对 Bootstrap 尚未通过晋级门槛，因此没有切换权重。当前生产权重尚未完成严格
未来 OOS 和含交易成本回测。

batch-1（2026-08-06 下午）后，`fullv3_ep3cont_best` 成为 clean_v8 首个通过开发 Confirm 的
checkpoint，列为下一轮严格 OOS 的首要研究候选；生产 junction 仍保持 `v3-cont epoch_2`，等待
tokenizer 两阶段、Qlib 回测与严格 OOS 后再决定是否切换。
