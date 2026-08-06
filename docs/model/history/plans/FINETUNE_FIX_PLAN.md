# Kronos-Small 微调历史修复计划

> 状态：Historical / Archived
> 用途：已完成问题的历史执行记录，不代表当前待办。
> 当前标准：以 [当前模型状态](../../current/MODEL_STATUS.md) 为准。

## 诊断结论

对比上游 `external/Kronos/finetune/` 官方微调代码，发现 3 个关键 bug：

### Bug 1: Normalization 泄露未来数据（最严重）
**文件**: `finetune_csv/finetune_base_model.py` — `CustomKlineDataset.__getitem__`

上游 `dataset.py:109-117`:
```python
past_x = x[:lookback_window]        # 只用历史90天
x_mean, x_std = np.mean(past_x, axis=0), np.std(past_x, axis=0)
x = (x - x_mean) / (x_std + 1e-5)
```

当前代码：
```python
x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)  # 包含了未来10天！
```

**影响**: 每个样本的 mean/std 包含了预测窗口的数据 → 训练 loss 虚低 → 模型过拟合到每个样本自身的统计量 → val loss 不下降

### Bug 2: 采样方式错误
**文件**: `finetune_csv/finetune_base_model.py` — `CustomKlineDataset.__getitem__`

上游 `dataset.py:95`:
```python
# __getitem__ 忽略 idx，完全随机采
idx = self.py_rng.randint(0, len(self.indices) - 1)
symbol, start = self.indices[idx]
```

当前代码：
```python
# 顺序访问，每个batch内数据来自同一只股票的连续片段
start_idx = (idx * 9973 + ...) % max_start
```

**影响**: 每个 batch 内样本来自少数几只股票 → 多样性差 → 收敛慢

### Bug 3: 学习率不对
上游 `config.py:57`: `predictor_learning_rate = 4e-5`
我们当前配置: `predictor_learning_rate = 0.0001` (1e-4)

## 修复计划

### Step 1: 修复 Normalization
在 `CustomKlineDataset.__getitem__` 中：
- 将 mean/std 计算限制在 `x[:lookback_window, :]`（前90行）
- 应用到全部 101 行

### Step 2: 修复采样方式
在 `CustomKlineDataset` 中：
- `__getitem__` 随机从所有股票的合法窗口中选一个
- 维护 `(stock_idx, start_idx)` 索引池
- 每个 idx 都随机采，不依赖传入的 idx

### Step 3: 修复学习率
配置文件：`predictor_learning_rate: 0.00004`

### Step 4: 更新数据划分（日期分片）
上游用 `train_time_range/val_time_range/test_time_range` 绝对日期：
- Train: 2022-01-01 ~ 2025-06-30
- Val: 2025-06-30 ~ 2026-03-31
- Test: 2026-03-31 ~ 2026-07-25

当前用比例 80/10/10。改为日期分片。

### Step 5: 全量训练
- 模型: Kronos-small
- 数据: 全部 385 只股票
- Batch: 64
- Accum: 8
- Epochs: 5
- LR: 4e-5
- GPU: DirectML (7800 XT)

### Step 6: 微调前后对比
加载 pretrained 和 finetuned 模型，在 test 集上计算 loss 对比。

## 预计时间
修复代码: ~15 分钟
全量训练 5 epoch: ~4 小时
对比测试: ~10 分钟
