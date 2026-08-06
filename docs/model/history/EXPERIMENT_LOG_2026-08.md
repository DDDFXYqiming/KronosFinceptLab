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

## 2026-08-07 batch-2：tokenizer 两阶段微调（GPU-only）

### DML 修复

tokenizer 训练在 DirectML 上崩溃的根因：验证阶段 eval 模式下 `BSQuantizer.forward` 执行
`torch.unique(indices)`，DML 无该算子（fatal `dml_tensor_desc.cc:76 broadcast_sizes.size() >=
sizes.size()`）。探针确认 train 模式（batch 8/32、真实数据 61 批）前后向全部通过、eval 模式必崩。
修复：`external/Kronos/model/module.py` 将 `used_codes`（仅报告指标、不参与 loss/早停）改到
CPU 计算，训练/验证计算全部留在 DML GPU。回归：原崩溃探针通过，train loss 与修复前完全一致。

### tokenizer 阶段（DML，LR 2e-4，2 epoch，2048 batch cap）

每 epoch 约 14 分钟；epoch1 val loss 0.0096、epoch2 0.0094；
`finetuned_largecap_v8_tokenizer/tokenizer/best_model` 已保存。另修复 tokenizer 训练循环
未应用 `max_train_batches` 的问题（`finetune_tokenizer.py`）。

### predictor 阶段（DML，父=fullv3_ep3cont_best + 微调 tokenizer，LR 5e-7，3 epoch）

| Epoch | Validation Loss |
|---|---:|
| 1 | 3.3551 |
| 2 | 3.3062 |
| 3 | 3.3037 |

输出 `finetuned_largecap_v8_fttok_predictor/basemodel/`（best_model = epoch_3）。

### 600 样本 Confirm（sc8/T0.5，样本哈希 b54adb…）

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | v2 通过 |
|---|---:|---:|---:|---:|---|
| fullv3_ep3cont_best | **0.1193** | **0.1097** | 53.33% | **0.0463** | **是** |
| fttok_predictor best | 0.0906 | 0.0667 | 53.33% | 0.0495 | 否（p=0.2687） |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | 基线 |

结论：tokenizer 两阶段在 clean_v8 上未带来排序增益——fttok_predictor 的 Pooled RankIC 与 MAE
均落后父线 `fullv3_ep3cont_best`，配对 Bootstrap p=0.2687 未过门槛。按决策门：tokenizer 候选
不切换生产，生产 junction 保持 `v3-cont epoch_2`，`fullv3_ep3cont_best` 仍为下一轮严格 OOS
首要研究候选。MAE 改善（CI [-0.0215, -0.0005]）稳定但不足以单独晋级。
