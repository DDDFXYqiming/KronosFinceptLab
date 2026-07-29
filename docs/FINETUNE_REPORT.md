# Kronos 当前微调与评测报告

> 文档状态：Current
> 项目版本：10.9.0
> 最后核对：2026-07-29
> 评测口径：完整生产推理链路

---

## 当前结论

KronosFinceptLab 的历史探索性实验曾把 **V3 cont epoch 2** 评为最佳模型；
2026-07-29 按当前固定时间折重新评测后，`fold_2025` 的最佳变体改为
**full_small_v3**。该变化说明旧排名对测试窗口很敏感，当前仍没有满足严格
OOS 条件的 checkpoint。

该名称仅表示评测实验，不是 REST API、CLI、MCP 或 Docker 的默认模型配置。运行时模型通过 `KRONOS_MODEL_ID` 配置，公开支持：

- `NeoQuasar/Kronos-mini`
- `NeoQuasar/Kronos-small`
- `NeoQuasar/Kronos-base`

---

## 当前评测标准

当前评测必须走与生产预测一致的完整链路：

1. 原始 CSV / DataFrame 输入
2. 滚动上下文归一化
3. tokenizer 编码
4. 自回归生成
5. tokenizer 解码
6. 反归一化到原始价格空间
7. 在原始价格空间计算方向准确率、IC、RankIC、AER 和 IR

跳过 tokenizer、自回归生成或反归一化的裸模型评测，不再作为当前项目指标。

可靠评测集的完整规则见 [`EVALUATION_PROTOCOL.md`](EVALUATION_PROTOCOL.md)。Phase 1 已实现 manifest 生成器和滚动评测工具；根据当前微调配置和训练日志，现有 checkpoint 均不能被称为 `fold_2026` 的干净最终 OOS 结果。

---

## 历史最后一次评测结果（旧口径）

历史结果仅用于追踪模型变化。当前统一执行流程已经改为 `smoke -> screen -> confirm -> final`，不再对所有 checkpoint 直接运行 `fold_2026` 全量 `sample_count=8`。

评测条件：

| 项目 | 当前标准 |
|---|---|
| 股票池 | 30 只股票（20 只 A 股 + 10 只港股） |
| 采样 | screen/confirm 使用 20 A 股 + 10 港股、每只 5 个固定窗口，约 150 个样本 |
| 预测长度 | `pred_len=5` |
| 采样次数 | screen=`1`；confirm=`8`；final 主指标=`1` |
| 温度 | `temperature=0.3` |
| Top-p | `top_p=0.9` |
| 推理设备 | DirectML |

最新结果：

| 实验 | Direction Acc | IC | RankIC | AER | IR |
|---|---:|---:|---:|---:|---:|
| **V3 cont epoch 2** | **60.0%** | 0.1975 | 0.1924 | 2.09% | 0.43 |
| 预训练基线 | 51.3% | 0.0713 | 0.0535 | 0.67% | 0.14 |

相较预训练基线，当前探索性实验的方向准确率提高 8.7 个百分点，并在 IC、RankIC、AER 和 IR 上均表现更好。该提升是同一评测协议下的实验差异，不是经过封存测试集验证的生产保证。

---

## 2026-07-29 GPU 重跑结果（当前口径）

本次使用 DirectML、固定随机种子 42、`fold_2025` 固定分层样本（20 A 股 +
10 港股，每只 5 个时间分散窗口，共 150 个样本），统一
`pred_len=5, sample_count=8, temperature=0.3, top_p=0.9`。旧结果使用的是
数据尾部偏移窗口，因此新旧结果用于检验稳健性，不是同一测试集上的重复测量。

| 当前排名 | 模型 | 新 DirAcc | 旧 DirAcc | 变化 | IC | RankIC | AER | IR |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | **full_small_v3** | **54.00%** | 48.00% | +6.00pp | -0.0330 | 0.0738 | 0.54% | 0.17 |
| 2 | full_small | 52.00% | 50.70% | +1.30pp | -0.0838 | -0.0723 | -0.93% | -0.30 |
| 3 | 预训练基线 | 49.33% | 51.30% | -1.97pp | -0.0553 | -0.0976 | 0.63% | 0.20 |
| 4 | Cont2 best | 48.67% | 58.70% | -10.03pp | -0.1330 | -0.0628 | -1.33% | -0.43 |
| 5 | V3 cont epoch 1 | 48.67% | 58.70% | -10.03pp | -0.1444 | -0.1062 | 0.03% | 0.01 |
| 6 | V3 cont epoch 2 | 48.67% | 60.00% | -11.33pp | -0.1651 | -0.1082 | -1.99% | -0.64 |
| 7 | V3 cont best | 48.00% | 59.30% | -11.30pp | -0.1419 | -0.0897 | -0.86% | -0.27 |
| 8 | V3 fromFTv1 best | 46.67% | 56.70% | -10.03pp | -0.1645 | -0.1255 | -0.60% | -0.19 |
| 9 | v2_small_v2 | 44.00% | 51.30% | -7.30pp | -0.0944 | -0.0770 | -0.45% | -0.15 |

`full_small_v3` 的 A/HK 方向准确率均为 54.0%，总体日期聚类 Bootstrap 95% CI
约为 45.52%–63.02%。该区间包含 50%，不能据此声称方向准确率显著超过随机。
旧冠军 V3 continuation 谱系在新窗口上的 IC、RankIC 和多数收益指标转负，旧排名
没有通过时间窗口稳健性复核。

### fold_2026 全量诊断

当前 checkpoint 都接触过 2026 数据，因此以下结果必须标记为 `diagnostic`，
不得写成严格 OOS：

| 模型/模式 | 样本 | sample_count | DirAcc (95% CI) | A / HK DirAcc | IC | RankIC | AER | IR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **full_small_v3 全量** | 3,696 | 1 | **52.87%** (50.88%–54.82%) | 53.10% / 52.32% | -0.0015 | 0.0166 | -2.04% | -0.32 |
| 预训练基线全量 | 3,696 | 1 | 50.51% (48.29%–52.83%) | 50.13% / 51.41% | -0.0136 | -0.0059 | -0.95% | -0.15 |
| full_small_v3 生产参数审计 | 256 | 8 | 51.17% (46.28%–56.59%) | 52.22% / 48.68% | -0.0990 | -0.0368 | -0.10% | -0.02 |

全量诊断中 `full_small_v3` 的方向准确率高于 50%，但与预训练基线的置信区间
重叠，且 IC 接近零、AER/IR 为负。当前证据不支持把它提升为生产交易模型；
下一步仍应训练一个完全不接触 2026 数据的 checkpoint，再执行一次严格封存测试。

---

## 解读边界

- 约 150 个样本仍属于小规模评测，结果需要更多时间窗口和滚动样本复核。
- 旧评测使用重叠偏移窗口，不能把窗口数量直接当作独立样本数。
- AER 和 IR 是本次离线评测结果，不代表实盘收益。
- 当前结论只说明该微调实验优于本次预训练基线，不等于对所有市场和时间段都有效。
- `V3 cont epoch 2` 的训练数据截止日期和预训练 checkpoint 的数据截止日期必须在最终 OOS 报告中单独记录。
- 模型输出仅用于研究，不构成投资建议。

## Phase 1 执行状态

已实现：

- `examples/build_eval_manifest.py`：生成训练/验证/封存测试分区和 2023–2026 滚动折；
- `src/kronos_fincept/evaluation/rolling.py`：窗口、embargo、按市场/股票/年份聚合和日期聚类 Bootstrap；
- `examples/eval_rolling.py`：使用 `KronosPredictor.predict_batch()` 的完整生产推理评测。
- `examples/eval_pipeline.py`：顺序编排 smoke、screen、confirm、final，避免 DirectML 并发。
- `eval_rolling.py`：支持固定分层抽样、ETA、断点恢复、全局锁和原子保存。

默认 manifest 产物：`output/evaluation_manifest.json`。当前数据生成了 284 个评测标的（200 A 股 + 84 港股），2026 封存折包含 3,696 个非重叠/带间隔窗口。最终测试运行前必须先冻结模型、推理参数和数据清单 hash。

当前已有 checkpoint 曾接触 2026 数据，因此任何现有 `fold_2026` 运行都必须标记为
`diagnostic`，不能写成严格 OOS 结论。严格 OOS 只适用于训练与验证数据截止不晚于
2025-12-31 的新 checkpoint。

---

## 当前训练数据规范

项目当前日线微调标准：

| 参数 | 值 |
|---|---:|
| `lookback_window` | 90 |
| `predict_window` | 10 |
| `max_context` | 512 |
| 特征 | open、high、low、close、volume、amount |
| 时间列 | timestamps |

完整格式见 [`FINETUNE_DATA_PREP.md`](FINETUNE_DATA_PREP.md)。

## 历史微调切分核对

当前训练记录对应的实际逻辑不是统一日期切分，而是每个股票 CSV 清洗后按
80% / 10% / 10% 的行数比例切分。训练代码只创建 train 和 validation
loader，没有 test loader；所以历史日志中的“Validation Loss”不是最终测试
结果。

| 模型系列 | 数据目录 | 文件数 | 2026 数据是否进入训练/验证流程 | 日志中的模型选择情况 |
|---|---|---:|---|---|
| V2 / V2 continuation | `data_v2` | 381 | train 最晚 2025-12-17；30 个标的的 validation 延伸至 2026-04-09 | `v2_small_v2` 在第 3/3 轮达到最佳 Validation Loss 2.9513 |
| V3 / V3 continuation / cont2 | `data_v3` | 497 | 训练分区已有 2 个标的延伸至 2026-03-12；validation 最晚至 2026-05-19 | `v3_fromFTv1_cont` 日志第 3 轮为 2.9507；`v3_small_cont2` 已记录到第 3 轮 2.9493 |
| full_small 系列 | `data` | 385 | train 最晚 2026-06-10；validation 最晚 2026-07-02 | `full_small_v2/v3` 的最佳验证损失都出现在第 1 轮，后续变差 |

因此，当前探索性评测中的 **V3 cont epoch 2** 明确使用过 2026 行情，不能
作为 `fold_2026` 的最终测试模型。`fold_2025` 和 `fold_2026` 是 Phase 1
新定义的滚动 OOS 评测区间；它们不等于上述历史微调脚本的 train/val/test，
当前评测 manifest 也来自 `data_v2`，需要与新 checkpoint 的训练快照分别记录。

历史训练过程、旧模型排名和旧评测口径见 [`archive/`](archive/README.md)，不得作为当前项目指标引用。
