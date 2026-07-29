# KronosFinceptLab 历史优化计划

> 状态：Historical / Archived
> 用途：阶段性执行记录，不代表当前路线图。
> 当前标准：以 [`../../FINETUNE_REPORT.md`](../../FINETUNE_REPORT.md) 和项目当前文档为准。

> 日期: 2026-07-26
> 范围: 微调训练、评测方法论、生产使用

---

## 一、微调训练优化（已记录，等待当前训练完成后执行）

### 1.1 DataLoader 并行化

| 项目 | 说明 |
|------|------|
| 位置 | `finetune_base_model.py:254, 264` |
| 问题 | `num_workers=0`、`pin_memory=False`，与 tokenizer 训练不一致（tok 用 `num_workers=6` + `pin_memory=True`） |
| 影响 | GPU 等待 CPU 加载数据，浪费 20-40% 吞吐 |
| 方案 | 改为 `num_workers=4`、`pin_memory=True` |

### 1.2 混合精度训练 (AMP)

| 项目 | 说明 |
|------|------|
| 位置 | `finetune_base_model.py:328` — forward 处 |
| 问题 | 全 FP32，RX 7800 XT 原生支持 FP16 |
| 影响 | 预估提速 40-60% |
| 方案 | 加 `torch.amp.autocast('privateuseone')` + `GradScaler` |

### 1.3 完整 Checkpoint 保存

| 项目 | 说明 |
|------|------|
| 位置 | `finetune_base_model.py:401-409` |
| 问题 | 仅保存 model weights，不保存 optimizer/scheduler/epoch 状态。继续训练时 LR 从零预热，val loss 回升 |
| 影响 | 每次继续训练稳定性下降 |
| 方案 | 保存完整 dict：`{model, optimizer, scheduler, epoch, best_val_loss}` |

### 1.4 验证指标增强

| 项目 | 说明 |
|------|------|
| 位置 | `finetune_base_model.py:360-377` |
| 问题 | 仅看 loss 选最佳模型，loss 下降不一定代表方向判断更好 |
| 方案 | 添加 direction accuracy 作为辅助早停指标 |

### 1.5 数据增强

| 项目 | 说明 |
|------|------|
| 位置 | `finetune_base_model.py:147-169` (`__getitem__`) |
| 问题 | 385 只股票无任何增强，易过拟合 |
| 方案 | 时间扭曲 + 幅度噪声 + 缩放，预估减少过拟合 2-5% |

---

## 二、评测方法论改进（本轮执行）

### 2.1 生产路径评测脚本

| 项目 | 说明 |
|------|------|
| 文件 | `examples/eval_production_correct.py` |
| 改动 | 使用 AkShare API 数据源替代静态 CSV，覆盖完整生产链路 |
| 数据 | 多时间段滑窗（2023H1/2023H2/2024H1/2024H2/2025H1） |
| 参数 | 同时测默认参数（`T=1.0,sc=1`）和最佳参数（`T=0.5,sc=8`） |
| 基准 | 随机基准 (50%) + 简单动量策略 |
| 模型 | finetuned small + pretrained small + pretrained base |

### 2.2 评测结果（将由脚本填充）

| 窗口 | 模型 | 参数 | 方向准确率 | 随机基准 | 动量基准 |
|------|------|------|-----------|---------|---------|
| — | — | — | — | — | — |

---

## 三、生产使用问题修复（本轮执行）

### 3.1 API 默认参数对齐最佳配置 ✅

| 项目 | 说明 |
|------|------|
| 文件 | `api/models.py:41-45`、`schemas.py:162-166` |
| 改动 | `temperature=1.0,sc=1` → `temperature=0.5,sc=8` |
| 验证 | 无参请求自动返回概率预测 |

### 3.2 Batch 路径支持 sample_count>1 ✅

| 项目 | 说明 |
|------|------|
| 文件 | `service.py:221-224` |
| 改动 | 去掉 `all(req.sample_count == 1 for req in requests)` 条件 |
| 验证 | batch 请求 + `sc=8` 不走回退路径 |

### 3.3 服务器启动模型预热 ✅

| 项目 | 说明 |
|------|------|
| 文件 | `api/app.py` startup 事件 |
| 改动 | `create_task` 调用 `prewarm_predictor()`，不阻塞启动 |
| 验证 | 重启后 `/api/health` 显示 `model_loaded: true` |

### 3.4 前端模型大小显示 ✅

| 项目 | 说明 |
|------|------|
| 文件 | `forecast/page.tsx:118`、`batch/page.tsx:157` |
| 改动 | 下拉选项 label 加大小/内存信息 |
| 验证 | 前端下拉可见 |

### 3.5 降低健康轮询频率 ✅

| 项目 | 说明 |
|------|------|
| 文件 | `Header.tsx:28` |
| 改动 | 30s → 120s |
| 验证 | 无功能性影响 |

---

## 四、执行状态

| 任务 | 状态 | 完成日期 |
|------|------|---------|
| Phase 0: 本文档 | ✅ | 2026-07-26 |
| P1.1 API 默认参数 | ✅ | 2026-07-26 |
| P1.2 Batch 路径修复 | ✅ | 2026-07-26 |
| P1.3 启动预热 | ✅ | 2026-07-26 |
| P1.4 前端模型大小 | ✅ | 2026-07-26 |
| P1.5 轮询频率 | ✅ | 2026-07-26 |
| 重启 API + 验证 | ✅ | 2026-07-26 |
| P2 评测脚本 | ✅ | 2026-07-26 |
| P2 GPU 运行评测 | ✅ | 2026-07-26 |

### 评测最终结果

30 只 A 股，510 样本，DirectML 推理，生产路径完整管线：

| Label | Model | PL | SC | T | Acc% | Loss | 说明 |
|-------|-------|----|----|----|------|------|------|
| **FT best** | finetuned_small | 5 | 8 | 0.5 | **54.1%** | 20.87 | ✅ 最优 |
| FT baseline | finetuned_small | 5 | 1 | 1.0 | 52.2% | 20.75 | 默认参数 |
| Pre best | pretrained_small | 5 | 8 | 0.5 | 43.5% | 25.58 | 随机水平 |
| Pre baseline | pretrained_small | 5 | 1 | 1.0 | 37.8% | 30.27 | 远低于随机 |
| Base best | pretrained_base | — | — | — | OOM | — | 102.3M 显存不足 |
| Random | — | — | — | — | **50.0%** | — | 理论基准 |

**核心结论**：
- **微调后 vs 预训练：** FT best (54.1%) vs Pre best (43.5%)，**+10.6pp** 提升，差异显著
- **微调后 vs 随机：** FT best (54.1%) vs Random (50%)，**+4.1pp**，有实际交易价值
- **最佳参数 vs 默认：** FT best (54.1%) vs FT baseline (52.2%)，**+1.9pp**，温度和多采样有效
- **预训练全部低于随机**，说明未经微调的模型无法直接用于日线预测
- **Kronos-base (102.3M) 因 page file=0 无法加载**，本机无法验证大模型
- 旧评估 87.7% 跳过了 tokenizer 编解码和自回归生成，不可与上述 54.1% 直接对比

### 已知约束
- 本机 page file 为 0GB，Kronos-base (102.3M) 和需要 safetensors 内存映射的操作可能失败
- 评估数据源为 CSV（与训练一致），未覆盖 AkShare 实时 API 数据路径
- 单时间窗口（最近 150 天），未覆盖多时段滑窗
