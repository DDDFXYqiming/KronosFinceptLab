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

## 2026-08-07 batch-3：GPU 吞吐配方设计（fast_recipe）

### 背景与目标

对照 L4（全量 ~10828 步/轮、80-90 分钟）与 v8 系列（max_train_batches 2048、14-16 分钟/轮），
时间差异来自每轮步数上限，不是显存或模型。目标是“尽可能利用 GPU、更快更有效地微调”，
并把候选配方作为独立实验线与 `fullv3_ep3cont_best` 同场对比（Confirm 评测固定 batch 32 不变）。

### 实测与迭代（DirectML，AMD Radeon 7800 XT）

1. **batch 128 无预计算**：每步 ~2s（CPU 逐窗 DataFrame 切片 + numpy 归一化成为瓶颈），
   2985 步/轮（全量 38.2 万窗口）→ 单轮约 2 小时，否决。
2. **窗口预计算**（`finetune_base_model.py`）：启动时一次性归一化全部 382200 个训练窗口并缓存
   （耗时 249.5s，约 1.6GB 内存），采样逻辑（py_rng）不变；正确性测试：同一 seed 下 300 个
   采样张量与原始路径逐位一致。这一步消除了 CPU 数据准备。
3. **batch 128 + 预计算**：实测仍 2.5s/步（51 samples/s）。原因：每步固定开销
   （loss.item 同步、clip_grad_norm、DML 调度）主导，batch 加大不能摊薄；DML 不随 batch 扩展。
4. **AdamW foreach=False**：DML 把 `aten::lerp.Scalar_out`（foreach 的 `_foreach_lerp_`）回退
   CPU；关闭 foreach 后 batch 32 从 0.83s/步降到 0.51s/步（38→63 samples/s）。

基准表（本机当前负载下，含 tokenizer encode + forward + backward + optimizer）：

| batch | optimizer foreach | 每步耗时 | 吞吐 |
|---|---:|---:|---:|
| 32 | True | 0.833s | 38 samples/s |
| 32 | False | 0.508s | 63 samples/s |
| 128 | True | 2.391s | 54 samples/s |
| 128 | False | 1.613s | 79 samples/s |

真实训练循环（含 loss.item / clip_grad_norm / DataLoader 传输）batch 128 为 2.5s/步
（51 samples/s），仍低于 batch 32。

### 最终配方（fast_recipe v3）

`batch 32 + accumulation 4（有效 batch 128）+ precompute_windows + optimizer_foreach=false +
max_train_batches 4096`：每轮 13.1 万样本（当前 v8 线 6.5 万的 2 倍），预期单轮 ~28-34 分钟，
3 轮。父模型 `fullv3_ep3cont_best`，LR 5e-7、seed 42、早停 patience=1/min_delta=0.001。

### 训练与 Confirm 结果

实测步速 0.33s/步（比原 v8 线 0.4s 更快），每轮 24.1 分钟；Epoch 验证损失 3.0454 / 3.0439 /
（epoch 3 未改善，早停），best = epoch 2（3.0439，父模型 3.0506）。

固定 600 样本 Confirm（sc8/T0.5，样本哈希 b54adb…）：

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | Endpoint MAE | Top5 超额 | v2 通过 |
|---|---:|---:|---:|---:|---:|---|
| **fast_recipe_best** | **0.1283** | **0.1319** | 52.67% | **0.0461** | **0.0369** | **是** |
| fast_recipe_epoch3 | 0.1285 | 0.1310 | 52.67% | 0.0461 | 0.0369 | 是 |
| fullv3_ep3cont_best（父） | 0.1193 | 0.1097 | 53.33% | 0.0463 | 0.0332 | 是 |
| 官方 Kronos-small | -0.0646 | -0.0374 | 47.83% | 0.0604 | -0.0064 | 基线 |

`fast_recipe_best` 相对官方：Pooled RankIC 增量 `+0.1929`、配对 Bootstrap `p=0.0744`；MAE 增量
CI `[-0.0234, -0.0057]`；逐期配对 t `p=0.1024`（10 期）。分市场 A 股 Pooled RankIC `0.1558`
（Top5 胜率 80%）、港股 `0.0594`。

### 结论：配方调整生效

"更多数据（2 倍/轮）+ AdamW foreach=False + 窗口预计算"的配方在 4/5 指标上超过父线
`fullv3_ep3cont_best`（Pooled RankIC +0.009、MeanDaily +0.022、MAE 更低、Top5 更高），成为
clean_v8 当前开发 Confirm 点估计最佳 checkpoint，且是首个在"更多数据"配方下超过原冠军的新线。
该配方定为项目新默认训练配方（记录于本日志与 MODEL_STATUS）；生产 junction 仍保持
`v3-cont epoch_2`，待严格 OOS 与 Qlib 回测。batch 32 是 DML 最优（batch 128 每步同步开销
主导，实测 2.5s/步 51 samples/s，低于 batch 32 的 64 samples/s），不再尝试大 batch。

## 2026-08-07 对齐批次：pred_len=10 全链路对齐 + T/复权对比

背景：按用户决定将 pred_len 统一为 10（与上游微调 `predict_window=10` 对齐），并基于官方
用法核查结果做运行/评测/训练三链路对齐。4x 训练暂停，恢复列为独立事项。完整证据见
[`ALIGNMENT_REPORT_2026-08.md`](plans/ALIGNMENT_REPORT_2026-08.md)。

### 1. 运行时参数集中化

- 新增 `config.py::KronosRuntimeConfig`（lookback=90、pred_len=10、T=0.5、top_p=0.9、
  sample_count=8、agent 16/8，env 可覆盖）；`schemas.py` 温度默认统一（消除 0.5/1.0 不一致）；
  `api/models.py` 请求默认读配置；新增 `GET /api/forecast/config`；预测页改从端点取值。
- 验证：CLI/API 不带参数取 pred_len=10、T=0.5；config 端点与 health 的 model_id 一致
  （NeoQuasar/Kronos-small junction）；web `tsc --noEmit` 通过。

### 2. 数据链路

- `data_adapter.rows_to_dataframe`：amount 全 0 时按官方规则回填 close×volume 并告警。
- `make_future_timestamps`：AkShare 交易日历（缓存 `output/calendars/`），周五→周一验证通过，
  失败回退步长外推。
- `service.forecast_from_request`：新增结构化审计日志（symbol/model_id/bar 数/时间范围/参数）。
- amount 审计（`examples/audit_amount_inputs.py`）：美股/yfinance 路径代码保证 amount=close×
  volume，本次 Yahoo 限流未能联网复核；港股 AKShare 存在约 0.1% 停牌日 0 量额行，记录为已知
  边界。

### 3. 评测协议切换 pred_len=10

- 新 manifest `evaluation_manifest_largecap_v8_recent_pred10.json`（pred_len=10、sample_step=15，
  validation 折叠 1603 样本）；新固定 600 样本 `evaluation_samples_pred10.json`（4 日期 ×
  A100/HK50 = 600，哈希 `a419b8b9…`）；150 样本诊断 `evaluation_samples_pred10_150.json`
  （哈希 `807f4411…`）。pred_len=5 的 b54adb… 样本存档不参与排名。

### 4. T 对比与决策门 G-A

- 5 标的同日对比：T=1.0 区间宽度中位数 1.68×（≥1.5）、平均上行概率 0.037→0.138（更分散）；
  150 样本诊断 T=1.0 下生产模型 RankIC 0.2035 vs 官方 0.0800、DirAcc 53.3% vs 50.0% → G-A
  (a)(b) 通过。
- 600 样本 T=1.0 Confirm：三个候选点估计全部超过官方（RankIC +0.021~0.034、DirAcc +3.7~
  4.5pp、MAE 约为官方一半），但配对 Bootstrap p=0.67~0.82 未达 p<0.10 → v2 门槛未通过 →
  **协议温度维持 0.5**；T=1.0 证据记录在案，待严格 OOS 周期积累后再评估。

### 5. 复权对比与决策门 G-B（含 Bug 修复）

- A 股 qfq vs 不复权中位收盘差异 2.4%~3.4%（除息量级），方向一致 → 保持 qfq。
- **修复 BaoStock adjustflag 映射 bug**（`baostock_source.py`）：官方语义 1=后复权、2=前复权、
  3=不复权；原映射 `none→1` 实际返回后复权价格，已改为 `{"qfq":"2","hfq":"1","none":"3"}`。
- 港股 yfinance vs AKShare qfq 对比因 Yahoo 限流未完成，待重试。

### 6. pred_len=10 正式 Confirm（T=0.5、sc8、Bootstrap 5,000）

| 模型 | Pooled RankIC | MeanDaily RankIC | DirAcc | MAE | Top5 超额 | v2 门槛 |
|---|---:|---:|---:|---:|---:|---|
| 生产 v3-cont epoch_2 | **0.1286** | 0.1056 | 53.33% | 0.0715 | −0.0030 | 未通过 |
| fullv3_ep3cont_best | 0.0675 | 0.1378 | **56.00%** | 0.0735 | +0.0303 | 未通过 |
| fast_recipe_best | 0.0630 | 0.1335 | 56.00% | 0.0736 | +0.0011 | 未通过 |
| 官方 Kronos-small | 0.0790 | 0.0550 | 50.50% | 0.1077 | −0.0016 | 基线 |

结论：无候选通过 v2 门槛；生产 junction 保持 `v3-cont epoch_2`；训练模板固化
predict_window=10，v8 系（predict 5）候选在 pred_len=10 协议下仅作诊断参考。
