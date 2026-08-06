# 2026-08 实验日志

> 状态：Historical log（结论以 [`docs/model/current`](../current/) 为准）

## 2026-08-06 batch-1：fullv3 收尾 + SFF 双臂 + 600 样本 Confirm

背景：clean_v8 近期验证中 `fullv3_epoch2` 点估计最佳但未过统计（p=0.1008）；生产 junction 仍为
`v3-cont epoch_2`。第一批决定不再堆 epoch，改为收尾被中断的 fullv3 线并测试 SFF 平滑微调。

### 1. SFF 起点生成

`examples/make_sff_checkpoint.py` 按 ICLR 2026 SFF 方法生成 `θ3 = 0.85·θ父 + 0.15·θ随机`
（随机孪生使用模型默认初始化，seed=42）：

| 臂 | 父模型 | 输出 | L2 距离 |
|---|---|---|---|
| sff_fullv3 | `finetuned_full_small_v3/basemodel/best_model` | `finetuned_largecap_sff_fullv3/sff_init` | 147.88 |
| sff_v3cont | `finetuned_v3_fromFTv1_cont/basemodel/epoch_2` | `finetuned_largecap_sff_v3cont/sff_init` | 137.87 |

验收：save/load 往返一致、与父模型 L2 距离 > 0、权重哈希写入 SFF_README.json。

### 2. 训练（单进程 DirectML，LR 5e-7、batch 32、accum 4、max_train_batches 2048、seed 42）

配置（位于 `external/Kronos/finetune_csv/configs/`，git 忽略）：
`config_largecap_v8_fullv3_ep3cont.yaml`（1 epoch）、`config_largecap_v8_sff_fullv3.yaml`（3 epoch）、
`config_largecap_v8_sff_v3cont.yaml`（3 epoch）。

| 运行 | 父验证损失参考 | Epoch 验证损失 | 耗时 |
|---|---|---|---|
| fullv3_ep3cont | 3.0529 | **3.0506** | 15.5 min |
| sff_fullv3 | 3.0529 | 3.3767 / 3.3186 / 3.3158 | 44.4 min |
| sff_v3cont | 2.9560 | 3.5098 / 3.4151 / 3.4105 | 43.1 min |

日志：`finetuned_*/logs/basemodel_training_rank_0.log`；stdout/stderr 归档在
`output/training_batch1/`。

### 3. 评测（600 样本 Confirm，sc8/T0.5/seed42）

`examples/eval_batch1_models.py` + `examples/compare_evaluations_v2.py`（5,000 次配对 Bootstrap），
结果见 [`EVALUATION_RESULTS.md`](EVALUATION_RESULTS.md) 与 `output/evaluation_batch1/`。

关键结论：
- `fullv3_ep3cont_best` 通过 v2 门槛（Pooled RankIC 0.1193，Bootstrap p=0.0868），为 clean_v8
  首个通过开发 Confirm 的 checkpoint；
- sc16 完整 600 复核同样通过；Top20% 成本诊断 sc16 业务信号 CI 不含 0；
- 两个 SFF 臂均落后父模型，路线关闭；
- 动量 5 日简单基线（0.1674）高于全部 Kronos 候选，报告必须并排展示。

### 4. 决策门 G1

冠军 `fullv3_ep3cont_best` 进入第二批（tokenizer 两阶段 + Qlib 回测）；生产 junction 保持
`v3-cont epoch_2` 不变；SFF 路线停止。2026-08-01 后数据仍封存，未参与任何调参。
