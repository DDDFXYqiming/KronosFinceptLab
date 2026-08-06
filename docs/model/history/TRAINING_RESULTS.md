# Kronos 微调训练结果时间线

> 文档状态：Historical summary
> 盘点时间：2026-08-05
> 当前冠军见：[MODEL_STATUS](../current/MODEL_STATUS.md)

本表覆盖 `external/Kronos/finetune_csv/` 下所有 `finetuned*` 目录。训练 loss 和 validation loss
只用于判断优化过程，不能代替生产路径预测评测。

## 训练阶段汇总

| 产物目录 | 阶段/起点 | checkpoint 状态 | 结论 |
|---|---|---|---|
| `finetuned` | 最早环境试跑 | 无 safetensors checkpoint | 未形成可用模型 |
| `finetuned_rocm` | ROCm 兼容性尝试 | 无 checkpoint | RDNA3 路线失败，转 DirectML |
| `finetuned_small` | 小样本试跑 | 无 checkpoint | 仅环境验证 |
| `finetuned_quicktest` | DirectML quick test | `best_model` | 链路验证，不参与当前排名 |
| `finetuned_full_small` | 官方 small，早期 385 股 | `best_model` | 早期 full 系列 |
| `finetuned_full_small_v2` | full continuation | `best_model` | 旧评测曾显示高准确率，口径已作废 |
| `finetuned_full_small_v3` | full 系列继续训练 | `best_model` | 旧系列最强候选之一，最新排名第 5 |
| `finetuned_v2_small` | 2010～2026 扩展数据 | `best_model` | 旧数据扩展未带来稳定提升 |
| `finetuned_v2_small_v2` | v2 继续训练 | `best_model` | 历史候选，不再继续 |
| `finetuned_v3_small` | v3 数据试跑 | 无 checkpoint | 被 fromFTv1 路线取代 |
| `finetuned_v3_fromFTv1` | 从旧 FT v1 迁移到 v3 数据 | best + epoch 1～3 | 形成后续 v3 主线 |
| `finetuned_v3_fromFTv1_cont` | v3 主线 continuation | best + epoch 1～3 | **epoch 2 为当前冠军** |
| `finetuned_v3_small_cont2` | v3 第二次 continuation | best + epoch 1～3 | 没有稳定超过 epoch 2 |
| `finetuned_simple_m1` | 简化实验预跑 | 无 checkpoint | 被 compact 三模型实验取代 |
| `finetuned_compact_m1` | 官方 small，`lr=1e-6` | best + epoch 1 | 未超过官方基线 |
| `finetuned_compact_m2` | 官方 small，`lr=5e-6` | best + epoch 1 | 未超过官方基线 |
| `finetuned_compact_m3` | 官方 small，均衡采样 | best + epoch 1 | 未超过官方基线 |
| `finetuned_largecap_l1` | 官方 small + largecap | best + epoch 1 | Confirm 有点估计提升，旧 v1 门槛未通过 |
| `finetuned_largecap_l2_v3cont` | v3-cont best + largecap | best + epoch 1 | 最新统一评测排名第 2，统计门槛未通过 |
| `finetuned_largecap_l3_l2cont` | L2 继续训练最多 5 epoch | best + epoch 1～5 | best=epoch 4；验证损失下降但预测未胜冠军 |
| `finetuned_largecap_l4_v3cont` | 当前冠军 epoch 2 + largecap | 无 checkpoint | 第一次 CPU OOM、第二次中止，无模型产物 |
| `finetuned_largecap_v7_v3cont` | 当前冠军 epoch 2 + `clean_v7` PIT largecap | epoch 1～2；epoch 3 中断无 checkpoint | epoch 2 validation loss 更低，但 epoch 1 的 screen 更好；Confirm 未超过父模型 |
| `finetuned_largecap_v8_fullv3_cont` | `full_small_v3` + `clean_v8` 近期数据 | epoch 1～2；epoch 3 未完成 | epoch 2 验证损失最佳，近期 Confirm 点估计第一但未通过统计门槛 |
| `finetuned_largecap_v8_v3cont` | 当前 v3-cont epoch 2 + `clean_v8` 近期数据 | epoch 1～3 | epoch 2 验证损失最佳，但近期 Confirm 明显落后 full 路线 |
| `finetuned_largecap_v8_fullv3_ep3cont` | fullv3 epoch 2 + `clean_v8` 续跑 1 epoch（种子与原始 epoch 3 不同，按新 continuation 记录） | best_model（= epoch_1） | 验证损失 3.0506（父 3.0529），600 样本 Confirm 通过 v2 门槛，成为新开发冠军候选 |
| `finetuned_largecap_sff_fullv3` | SFF 平滑起点（α=0.85，full_small_v3 + 随机孪生）+ `clean_v8` | epoch 1～3 + best | 验证损失 3.3158 收敛缓慢，Confirm 明显落后父模型，路线停止 |
| `finetuned_largecap_sff_v3cont` | SFF 平滑起点（α=0.85，v3-cont epoch 2 + 随机孪生）+ `clean_v8` | epoch 1～3 + best | 验证损失 3.4105 收敛缓慢，Confirm 明显落后父模型，路线停止 |

## 关键训练结论

1. 官方预训练权重上的独立低学习率 M1/M2/M3 没有稳定超过官方基线；
2. 旧 `v3_fromFTv1_cont` 谱系保留了最强预测能力，最新冠军是其中的 epoch 2；
3. L2/L3 说明 validation loss 继续下降不等于实际 RankIC 继续提高；
4. L4 没有保存 checkpoint，不能列入可用模型；
5. 同一数据上的 continuation 已达到停止条件，后续应依赖新数据或严格 OOS，而不是继续堆 epoch。
6. `clean_v7` 修复了历史成分股偏差并扩大到 581 只，但两轮 continuation 仍未在 595 样本 Confirm
   中稳定超过父模型；按协议停止第三轮，不再沿相同数据追加训练。
7. `clean_v8` 将训练/验证切分收紧到 2026 年近期市场。`full_small_v3` continuation 在近期验证集
   上显著优于官方基线，v3-cont continuation 则没有复现旧验证期优势；两者都尚未通过配对统计晋级。
8. 2026-08-06 第一批（batch-1）：`fullv3_ep3cont`（fullv3 epoch 2 续跑 1 epoch）成为首个在
   clean_v8 600 样本 Confirm 通过 v2 门槛的 checkpoint；两个 SFF 平滑微调臂（α=0.85）验证损失
   未收敛回父模型水平，600 样本 Confirm 明显落后，按停止规则关闭该路线。

## 详细记录

- [2026-07 实验长日志](EXPERIMENT_LOG_2026-07.md)
- [早期 full/v2/v3 原始报告](LEGACY_REPORT.md)
- [历史微调修复计划](plans/FINETUNE_FIX_PLAN.md)
- [历史数据质量计划](plans/DATA_QUALITY_PLAN.md)
- 当前训练数据：[DATASET_SPEC](../current/DATASET_SPEC.md)
