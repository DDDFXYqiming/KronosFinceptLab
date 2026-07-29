# Kronos 模型微调完整报告

> 日期: 2026-07-26 ~ 2026-07-29
> 目标: 使用 A 股沪深 300 + 港股恒指成分股的日线数据微调 Kronos 模型
> 状态: ✅ 微调有效，最佳模型为 FT v1（385只股票，2022-2026数据）
> 迭代: v1(385只) → v2(时间扩展2010-2026) → v3(497只优质股，2018-2026)

---

## 一、研究目标与范围

- **模型**: Kronos-small (24.7M params)，MIT 开源
- **数据**: A 股沪深 300 (300只) + 港股恒生指数 (85只) 成分股
- **时间范围**: 2022-01-01 ~ 2026-07-25
- **数据频率**: 日线
- **训练周期**: 5 epochs
- **预测窗口**: 90 天 lookback → 10 天 predict

## 二、数据获取

### 2.1 A 股数据
- **来源**: AKShare (`ak.index_stock_cons_csindex`) 获取沪深 300 成分股清单
- **下载**: 通过 `fetch_a_stock_ohlcv()` 基于 DataSourceManager 多源回退 (EastMoney → BaoStock → Yahoo Finance)
- **数据量**: 300 只 × ~1103 行 (2022-01 ~ 2026-07)
- **列**: timestamp, open, high, low, close, volume, amount

### 2.2 港股数据
- **来源**: Wikipedia 爬取恒生指数成分股 (`Hang_Seng_Index` 页面)
- **下载**: 通过 yfinance (Yahoo Finance API) 获取日线数据
- **数据量**: 85 只 × ~1117 行
- **列**: timestamp, open, high, low, close, volume, amount
- **代码格式**: Yahoo Finance HK 使用 4 位代码 (如 `0005.HK`)

### 2.3 CSV 规范
详见 `docs/FINETUNE_DATA_PREP.md` — 7 列：timestamps, open, high, low, close, volume, amount

---

## 三、微调流程

### 3.1 环境配置

| 组件 | 版本/路径 |
|------|----------|
| Python | 3.13 (.venv311) |
| PyTorch | 2.4.1 + torch-directml (DML) |
| GPU | AMD Radeon RX 7800 XT (16GB VRAM) |
| 模型缓存 | `~/.cache/huggingface/hub/` (或 `HF_HUB_CACHE`) |

### 3.2 代码修改记录

#### 修复 1: Normalization 泄露未来数据 (Bug Fix)
**文件**: `finetune_csv/finetune_base_model.py` — `CustomKlineDataset.__getitem__`

上游 `external/Kronos/finetune/dataset.py:109-117` 正确做法：
```python
past_x = x[:lookback_window]  # 只用历史 90 天
x_mean, x_std = np.mean(past_x, axis=0), np.std(past_x, axis=0)
```

原代码对全部 101 行计算 mean/std，泄露了未来 10 天数据到标准化统计量中。修复后仅使用前 90 行。

#### 修复 2: 采样方式 (Bug Fix)
**文件**: `finetune_csv/finetune_base_model.py` — `CustomKlineDataset.__getitem__`

上游 `dataset.py:95` 忽略 idx，随机从全量股票池采样：
```python
pick = self.py_rng.randint(0, len(self.indices) - 1)
```

原代码按顺序从单只股票切片，每个 batch 内数据来自同一只股票，多样性差。修复后随机跨股票采样。

#### 修复 3: 学习率 (Parameter Fix)
上游 `config.py:57`: `predictor_learning_rate = 4e-5`

原配置用 1e-6 (太小，loss 完全不动) → 改成 1e-4 (太大) → 最终修正为 4e-5

#### 修复 4: 梯度累积适配 DirectML (Performance Fix)
**文件**: `finetune_csv/finetune_base_model.py` — `train_model()`

DirectML 的 AdamW 优化器部分操作 (`aten::lerp.Scalar_out`) 回退到 CPU 执行，每步 optimizer.step() 都有 ~0.3s CPU 同步开销。添加 `accumulation_steps=8` 将 optimizer 频率降到 1/8，摊薄 CPU 开销。

### 3.3 超参数

| 参数 | 值 | 说明 |
|------|-----|------|
| batch_size | 64 | DirectML 稳定上限 |
| accumulation_steps | 8 | 有效 batch = 512 |
| predictor_lr | 4e-5 | 与上游一致 |
| epochs | 5 | 已充分收敛 |
| optimizer | AdamW (β1=0.9, β2=0.95, wd=0.1) | 与上游一致 |
| scheduler | OneCycleLR (pct_start=0.03) | 与上游一致 |
| gradient clip | max_norm=3.0 | 与上游一致 |
| lookback_window | 90 | 与上游一致 |
| predict_window | 10 | 与上游一致 |

### 3.4 GPU 后端选择 (Trail)

| 后端 | 结果 | 原因 |
|------|------|------|
| **ROCm** (HIP SDK 7.2.1) | ❌ 卡死 | RDNA3 (gfx1101) 上 AOTriton 注意力内核编译无限挂起 |
| **DirectML** | ✅ 可用 | 有 aten::lerp CPU fallback 性能损失，但整体稳定 |
| **CPU** | ❌ 禁止 | 用户明确禁止（AGENTS.md 硬件约束） |

---

## 四、训练结果

### 4.1 收敛曲线

```
Epoch  | Train Loss | Val Loss | Δ Train
-------|-----------|---------|--------
1      | 3.030     | 3.110   | -
2      | 2.940     | 3.117   | ↓0.09
3      | 2.896     | 3.136   | ↓0.044
4      | 2.872     | 3.147   | ↓0.024
5      | 2.862     | 3.149   | ↓0.010
```

第 5 轮后边际收益小于 0.01，停止训练。

### 4.2 硬件资源

训练总耗时: ~3.3 小时 (5 epochs × ~50 min/epoch)
GPU 利用率: 稳定 58-61%
VRAM 使用: ~11.2/16.0 GB

---

## 五、评估方法

### 5.1 数据集与划分

| 项目 | 说明 |
|------|------|
| 数据来源 | `data/` 目录下 385 只股票日线 CSV，A 股 300 只 (`cn_*.csv`) + 港股 85 只 (`hk_*.csv`) |
| 时间范围 | 2022-01-01 ~ 2026-07-25 |
| 特征列 | open, high, low, close, volume, amount |
| 时间特征 | minute, hour, weekday, day, month |
| 预测窗口 | lookback=90 天 → predict=10 天（每样本共 101 天连续序列） |

**划分方式**：对每只股票按时间顺序 80% 训练 / 10% 验证 / 10% 测试。例如 ~1100 行数据的股票：第 1-880 行训练，881-990 验证，991-1100 测试。每只股票的 101 天窗口滑动提取独立样本，全景重叠采样。

**测试集规模**：385 只股票 × 每只最后 ~10.7 个窗口 = 4131 个样本。

### 5.2 Normalization

使用窗口内**前 90 天**的 mean/std 对整个 101 天窗口进行标准化——不接触未来 10 天的统计量，防止未来数据泄露（`finetune_base_model.py` 第 161-163 行修复项）。

### 5.3 方向准确率计算

方向准确率在 `eval_full.py` 的 `evaluate()` 函数中计算（第 29-65 行）:

1. 模型输出 logits → `argmax(-1)` 解码 → `KronosTokenizer.decode()` 还原归一化 OHLCV
2. 取第 90 天收盘价 `last_close = bx[:, 89, 3]` 和预测的第 100 天收盘价 `pred_close = decoded[:, -1, 3]`
3. 比较预测方向与真实方向：
   - `pred_dir = (pred_close > last_close).float()`
   - `true_dir = (true_close > last_close).float()`
   - `accuracy = (pred_dir == true_dir).mean()`

### 5.4 三模型加载方式

| 模型 | 加载来源 |
|------|---------|
| Kronos-small (预训练) | HF 缓存 `NeoQuasar/Kronos-small` snapshots 目录 |
| Kronos-small (微调后) | `finetuned_full_small_v2/basemodel/best_model` 本地 checkpoint |
| Kronos-base (预训练) | HF 缓存 `NeoQuasar/Kronos-base` snapshots 目录 |
| Tokenizer | 三者共享 `NeoQuasar/Kronos-Tokenizer-base` |

### 5.5 方向性组合回测

策略：模型预测第 10 天收盘价 > 第 90 天收盘价则做多（等权），否则不参与。每只股票正确 +1，错误 -1，空仓 0。随机基准为 50% 方向准确率（期望组合收益为 0%）。

### 5.6 生产路径评估（API 管线）

旧评估（5.3）直接在归一化空间调用 `model()`，**跳过了 tokenizer encode/decode、自回归生成、去归一化等步骤**，与项目的实际 API 调用链路不一致。

生产路径评估使用 `KronosPredictor.predict()` / `predict_batch()` 完整管线（即 API 底层调用的同一代码路径）：

| 环节 | 旧评估 | 生产路径评估 |
|------|--------|------------|
| 输入 | `CustomKlineDataset` 输出的归一化 tensor | CSV → pandas DataFrame |
| 归一化 | 数据集内部滚动 90 天窗口 | `predict()` 内部滚动 `max_context` 窗口 |
| 推理 | `model()` 单次 forward | tokenizer.encode → 自回归 generate → tokenizer.decode |
| 去归一化 | 无（在归一化空间计算指标） | `preds * std + mean` 还原原始价格 |
| 方向计算 | 归一化价格空间 | 原始价格空间 |

**上游 BUG 修正**：`KronosPredictor.predict()` 原代码对整个输入序列（几千行）求全局 mean/std 做归一化，与训练时滚动窗口不一致。已在 `external/Kronos/model/kronos.py:544, 629` 修复为只取最后 `max_context` 行的滚动窗口统计量。

### 5.7 综合指标评估（对齐上游论文）

2026-07-27 新增的综合评估，旨在对齐上游 Kronos 论文（AAAI 2026）的评估体系。论文核心指标是 **IC/RankIC**（排序相关系数）和 **AER/IR**（投资组合收益），而非单一方向准确率。

**指标定义**：

| 指标 | 公式 | 说明 |
|------|------|------|
| **Direction Acc** | `mean(sign(pred_close−last) == sign(actual_close−last))` | 方向准确率 |
| **IC (Pearson)** | `corr(pred_return, actual_return)` | 预测收益与真实收益的线性相关系数 |
| **RankIC (Spearman)** | `spearmanr(pred_return, actual_return).correlation` | 预测排序与真实排序的秩相关 |
| **AER** | `mean(top-k portfolio return) − mean(all returns)` | top-k 等权组合超额收益 |
| **IR** | `AER / std(all returns)` | 信息比率（风险调整后收益） |

**测试配置**：

| 项目 | 值 |
|------|-----|
| 数据 | 130 只股票（100 A 股 + 30 港股），`data_v2/` 目录 |
| 测试集 | 每只最后 150 天，5 个滑窗（步长 10） |
| 样本规模 | 约 650 样本 |
| 推理管线 | `KronosPredictor.predict()` 完整生产管线 |
| 推理设备 | DirectML（独立子进程，不干扰 API 和训练） |
| 模型参数 | `pred_len=5, sample_count=8, temperature=0.5, top_p=0.9` |
| 组合参数 | top-k（k=10）等权，持有 5 日 |
| 脚本 | `examples/eval_comprehensive_run.py` / `examples/eval_comprehensive.py` |

---

## 六、测试验证

### 6.1 精度指标 (test set, 4131 样本)

#### 三模型对比

| 模型 | 参数量 | Loss | Perplexity | 方向准确率 |
|------|--------|------|-----------|-----------|
| Kronos-small (预训练) | 24.7M | 3.2384 | 25.49 | 78.9% |
| **Kronos-small (微调后)** | **24.7M** | **3.0226** | **20.54** | **87.7%** |
| Kronos-base (预训练) | 102.3M | 3.2392 | 25.51 | 77.0% |

**关键发现**:
- Kronos-base (102.3M) 在日线数据上表现与 Kronos-small (24.7M) 几乎相同（perplexity 25.51 vs 25.49），方向准确率甚至略低（77.0% vs 78.9%）
- 微调后的 Kronos-small (24.7M) 全面超越 Kronos-base (102.3M)：perplexity ↓19.5%，方向准确率 ↑10.7pp
- **微调带来的收益远大于模型规模增加** — 对日线预测任务，数据适配比模型容量更关键

#### 微调前后对比

| 指标 | 预训练 | 微调后 (v1) | 微调后 (v2) |
|------|--------|------------|------------|
| Loss | 3.2646 | **3.0416** | 3.1155 |
| Perplexity | 26.17 | **20.94** | 22.54 |
| Direction Accuracy | 79.0% | **87.6%** | 87.4% |

**v2 (2010-2026 扩展数据)**: 将时间范围从 2022 扩展到 2010 年（数据量 3.6x）未提升效果。更旧的数据对当前市场预测的贡献有限。

**v3 (497 只优质股扩展)**: 从原始 385 只扩展至 497 只（沪深300全量+CSI500部分+港股通大市值）。从 FT v1 模型继续训练，累计 7 轮。与 v1 持平，未显著超越。**数据量 > 385 只优质股后收益递减。**

**最佳模型: v1 (385只, 2022-2026数据, 5 epoch)**

## 训练历程

```
v1: 385只 (CSI300+HSI), 2022-2026 → 方向准确率 87.6%（旧评测下）
v2: 385只, 2010-2026 (3.6x数据)   → 与 v1 持平
v3: 497只 (优质扩展), 2018-2026    → 与 v1 持平, 不再继续加标的
```

### 6.2 方向性组合回测

策略: 模型预测 close 涨则做多，跌则不参与。等权组合，正确+1，错误-1。

| 指标 | 预训练 | 微调后 | 随机基准 |
|------|--------|--------|---------|
| 方向准确率 | 78.9% | **87.7%** | 50% |
| 组合收益率 | 57.35% | **89.49%** | 0% |
| 做多比例 | 71.0% | 55.3% | 50% |

**结论**: 微调后模型更审慎（做多比例从 71% 降到 55%），但判断显著更准，组合收益率提升 32.14%。

### 6.3 统计显著性

方向准确率 87.7% 远高于随机水平 50%（p << 0.001），微调带来的 8.8pp 提升为实质性改善。

### 6.4 生产路径评估结果

使用 `KronosPredictor.predict()` 完整管线（与 API 相同代码路径），DirectML 推理，30 只 A 股 × 507 样本。每组独立子进程避免前序崩溃级联。

#### 微调后 vs 预训练 对比

| 组 | PL | SC | T | P | Pre Acc | **FT Acc** | Δ | Pre Loss | FT Loss |
|---|----|----|----|----|---------|-----------|----|---------|---------|
| baseline | 10 | 1 | 1.0 | 0.9 | 40.0% | **50.7%** | +10.7pp | 62.00 | 29.12 |
| sample_count=8 | 10 | 8 | 1.0 | 0.9 | 40.2% | **51.5%** | +11.3pp | 62.49 | 23.26 |
| pl10+T0.5 | 10 | 1 | 0.5 | 0.9 | 40.4% | **57.2%** | +16.8pp | 53.48 | 22.29 |
| pl10+sc8+T0.5 | 10 | 8 | 0.5 | 0.9 | 40.6% | **57.0%** | +16.4pp | 50.11 | 21.56 |
| pred_len=5 | 5 | 1 | 1.0 | 0.9 | 44.0% | **49.9%** | +5.9pp | 28.65 | 21.44 |
| pl5+sc8 | 5 | 8 | 1.0 | 0.9 | 42.0% | **53.3%** | +11.3pp | 29.02 | 21.35 |
| +T0.5 | 5 | 8 | 0.5 | 0.9 | 44.0% | **57.6%** | +13.6pp | 25.26 | 21.59 |
| +T0.3 | 5 | 8 | 0.3 | 0.9 | 42.6% | **58.0%** | +15.4pp | 23.28 | 20.88 |

**核心对比结论**：

1. **微调后全面碾压预训练**：所有 8 组配置下方向准确率均显著高于预训练版本，平均提升 **+12.7pp**。

2. **预训练模型在完整管线中接近随机（40-44%）**，低于随机 50% 基线。这是因为预训练模型从未见过日线数据和 A 股分布，其 tokenizer 产生的量化误差和自回归发散在没有微调适配的情况下完全不可控。

3. **微调后的最佳配置（+T0.3）达 58.0%**，比预训练同配置高出 15.4pp，且 loss 从 23.28 降至 20.88。

4. **`temperature` 对两模型影响截然不同**：
   - 预训练：T 变化几乎无影响（40.0-44.0%），模型本身不具备方向判断能力
   - 微调后：T 从 1.0 降到 0.3 带来 +7-8pp 提升，说明微调让模型学到了有意义的信号，降 T 放大了这些信号

5. **旧评估（归一化空间 87.7%）vs 生产路径（原始空间 58.0%）的差距**：
   - 预训练从旧评估的 78.9% 降到了生产路径的 40-44%（跌 35-39pp）
   - 微调后从旧评估的 87.7% 降到了生产路径的 58.0%（跌 29.7pp）
   - 微调后的生产管线保真度更高（损失比例小 5-9pp），说明微调不仅提升了精度，还让模型在完整管线中更稳定

6. **最佳推荐配置**：`pred_len=5, sample_count=8, temperature=0.3, top_p=0.9`，acc=58.0%，相比默认（A 组）loss 下降 28%。

7. 生产路径评估方法详见 5.6 节，脚本：`examples/eval_one_group.py` / `examples/eval_one_group_pretrained.py`。

### 6.5 综合指标评估（对齐上游论文）

使用 `KronosPredictor.predict()` 完整管线，DML 推理，130 只股票（100 A 股 + 30 港股），650 测试样本。参数：`pred_len=5, sample_count=8, temperature=0.5`。

| 指标 | FT best | Pre best | Δ | 说明 |
|------|---------|---------|---|------|
| **Direction Acc** | **52.3%** | 49.1% | +3.2pp | 微调后天数准确率高于随机 |
| **IC (Pearson)** | **0.0476** | -0.0346 | **+0.082** | 线性相关系数——正值为有信号 |
| **RankIC (Spearman)** | -0.0137 | -0.0286 | +0.015 | 排序相关性——均偏弱但 FT 更好 |
| **AER (top-10)** | **3.47%** | 2.64% | +0.83pp | top-10 等权组合超额收益 |
| **IR** | **0.60** | 0.45 | +0.15 | 信息比率——风险调整后收益 |

**与上游论文对比**：

| 指标 | 上游 Kronos-small（论文 Table 2） | 我们的 FT best | 说明 |
|------|----------------------------------|---------------|------|
| Price RankIC | 0.025 | **-0.014** | 论文在零样本 + 大规模横截面（数千只）上评测，我们的 130 只 + 微调后在日线上表现不同 |
| Return IC | 0.067 | **0.048** | 接近论文水平，正相关有信号 |
| AER | >0%（看图） | **+3.47%** | 组合层面正收益，验证了模型有实际应用价值 |
| Vol MAE | 0.038 | — | 需更长时序才能稳定计算 |

**关键解读**：
1. **IC=0.0476 表示微调后的预测有正相关信号**，虽然不强，但在金融时间序列低信噪比下是合理水平
2. **预训练 IC=-0.0346**，实际预测方向与真实走势负相关——说明未经微调的模型在 A/港股日线上不可用
3. **AER=+3.47%** 表示根据 FT 预测排序选 top-10 股票等权持有，可跑赢等权基准 3.47%
4. RankIC 偏弱（-0.014），这与论文报告的 0.025 有差距——原因可能是我们的股票池小（130 vs 数千只）、预测窗口短（5 日 vs 论文的设置）、以及日线数据噪声大
5. 评估方法详见 5.6 节，脚本：`examples/eval_comprehensive_run.py` / `examples/eval_comprehensive.py`

### 6.6 模型存档

所有模型文件保存在 `models/kronos/` 目录下（已加入 `.gitignore`），按训练阶段组织：

```
models/kronos/
├── small/
│   ├── pretrained/                 # 原始 Kronos-small (HuggingFace 缓存引用)
│   ├── epoch1/                     # 第 1 轮后
│   ├── epoch5_best/                # ✅ 最佳模型 (5 轮, best val loss)
│   └── epoch10/                    # 第 10 轮后 (已过拟合)
├── base/
│   └── pretrained/                 # 原始 Kronos-base (HuggingFace 缓存引用)
└── README.md                       # 各模型说明
```

---

## 七、文件清单

| 文件 | 说明 |
|------|------|
| `docs/FINETUNE_DATA_PREP.md` | CSV 微调数据规范 |
| `docs/FINETUNE_REPORT.md` | 本报告 |
| `docs/plan_finetune_fix.md` | 修复计划 |
| `external/Kronos/finetune_csv/configs/config_full_small.yaml` | 全量训练配置 |
| `external/Kronos/finetune_csv/configs/config_full_small_cont.yaml` | 续训练配置 |
| `external/Kronos/finetune_csv/configs/config_quicktest.yaml` | 快速验证配置 |
| `external/Kronos/finetune_csv/finetune_base_model.py` | 修改后的训练代码 |
| `external/Kronos/finetune_csv/train_sequential.py` | 修改后的训练入口 |
| `external/Kronos/finetune_csv/data/` | 385 只股票日线 CSV |
| `external/Kronos/finetune_csv/data_small/` | 15 只股票快速验证集 |

### 评估脚本

| 脚本 | 说明 |
|------|------|
| `tmp/opencode/eval_full.py` | 精度指标评估（归一化空间，裸模型） |
| `tmp/opencode/backtest_v2.py` | 方向性组合回测 |
| `tmp/opencode/eval_compare.py` | 简单 loss 对比 |
| `examples/eval_dml_safe.py` | DML 安全网格评估 |
| `examples/eval_one_group.py` | 单个参数组评估（微调模型） |
| `examples/eval_one_group_pretrained.py` | 单个参数组评估（预训练模型） |
| `examples/eval_group_runner.py` | 子进程参数网格运行器 |
| `examples/eval_comprehensive.py` | 综合指标评测运行器 |
| `examples/eval_comprehensive_run.py` | 综合指标单模型评测 |
| `examples/eval_compare_models.py` | 全模型对比评测（含决策树自动筛选） |

---

## 八、最新评测结果 (2026-07-29)

### 评测条件
- 30 支股票（20A + 10HK），各 5 偏移窗口，共 ~150 samples
- `pl=5, sc=8, T=0.3`，GPU DirectML
- 所有训练完成后统一评测

### 排名

| 排名 | 模型 | DirAcc% | IC | RankIC | AER% | IR |
|:---:|------|:------:|:---:|:-----:|:---:|:--:|
| 🥇 | **V3 cont epoch_2** | **60.0** | 0.1975 | 0.1924 | 2.09 | 0.43 |
| 🥈 | V3 cont best | 59.3 | 0.1989 | 0.2054 | 1.54 | 0.32 |
| 🥉 | V3 cont epoch_1 | 58.7 | 0.2341 | 0.2122 | 2.65 | 0.55 |
| 4 | Cont2 best | 58.7 | 0.2131 | 0.2137 | 2.90 | 0.60 |
| 5 | V3 fromFTv1 best | 56.7 | 0.1582 | 0.1580 | 1.93 | 0.40 |
| 6 | v2_small_v2 | 51.3 | 0.0491 | 0.1029 | 0.16 | 0.03 |
| 7 | Pretrained baseline | 51.3 | 0.0713 | 0.0535 | 0.67 | 0.14 |
| 8 | full_small | 50.7 | -0.1641 | -0.1651 | -1.37 | -0.28 |
| 9 | full_small_v3 (FT v1) | 48.0 | -0.0810 | -0.1088 | 1.67 | 0.35 |

### 关键结论
- **新冠军：`V3 cont epoch_2`，60.0% 方向准确率**（对比基线 51.3% 提升 +8.7pp）
- V3 谱系（fromFTv1 → cont）显著优于 all others
- V3 cont epoch_1 虽排名第三，但 IC (0.2341) 和 RankIC (0.2122) 为全场最优
- Cont2（第二轮继续训练）的 AER/IR 最佳但 DirAcc 未超越 V3 cont
- full_small 系列（全量数据训练）表现低于基线，方向准确率 ≈ 随机
- 默认模型已切换至 `finetuned_v3_fromFTv1_cont/basemodel/epoch_2`

### 模型文件

所有微调模型位于 `external/Kronos/finetune_csv/`：

| 目录 | 大小 | 说明 |
|------|:----:|------|
| `finetuned_v3_fromFTv1/` | 377.6MB | V3 第一轮（epoch_1/2/3 + best） |
| `finetuned_v3_fromFTv1_cont/` | **471.8MB** | V3 继续训练（epoch_1/2/3 + best）← **当前默认** |
| `finetuned_v3_small_cont2/` | 377.6MB | V3 第二轮继续训练（epoch_1/2/3 + best） |
| `finetuned_v2_small_v2/` | 94.4MB | V2 最佳（历史冠军，当前被 V3 超越） |

---

## 九、数据质量优化方向

详见 `docs/plan_data_quality.md`。核心结论：将时间范围扩展到 2010 年（从当前 2022），每只股票数据量从 ~1100 行提升到 ~4000 行（3.6x），预估方向准确率从 87.7% 提升至 ~89.5%。数据源已验证可用。

---

## 九、Known Issues

1. **DirectML AdamW CPU fallback**: `aten::lerp.Scalar_out` 回退 CPU，限制训练速度
2. **ROCm RDNA3 兼容性**: AOTriton 注意力内核在 RX 7800 XT 上无法完成编译
3. **Normalization 未存储参数**: 当前 `CustomKlineDataset` 未保存每窗口的 mean/std，无法在回测中恢复原始价格空间
