# Kronos 当前微调数据规范

> 文档状态：Current
> 项目版本：10.9.0
> 最后核对：2026-07-29

本文档定义 KronosFinceptLab 当前日线微调数据标准。`external/Kronos/` 中的 `512/48` 配置属于上游通用示例，不是本项目当前训练标准。

---

## CSV 列规范

列名严格区分大小写：

| 列名 | 类型 | 必填 | 说明 |
|---|---|:---:|---|
| `timestamps` | 日期时间 | 是 | 必须能被 `pandas.to_datetime()` 解析 |
| `open` | 浮点数 | 是 | 开盘价 |
| `high` | 浮点数 | 是 | 最高价 |
| `low` | 浮点数 | 是 | 最低价 |
| `close` | 浮点数 | 是 | 收盘价 |
| `volume` | 浮点数 | 是 | 无数据时填 `0` |
| `amount` | 浮点数 | 是 | 无数据时填 `0` |

示例：

```csv
timestamps,open,high,low,close,volume,amount
2026-07-27,42.10,42.85,41.92,42.66,12833000,546200000
2026-07-28,42.72,43.20,42.31,42.98,14302000,614900000
```

---

## 当前窗口参数

| 参数 | 当前值 | 含义 |
|---|---:|---|
| `lookback_window` | 90 | 输入的历史交易日 |
| `predict_window` | 10 | 训练目标的未来交易日 |
| `max_context` | 512 | 模型最大上下文 |

单个训练窗口至少需要连续的历史和预测数据。实际数据文件应包含远多于单个窗口的记录，以支持训练、验证和测试切分。

---

## 时间特征

训练代码从 `timestamps` 自动生成：

- minute
- hour
- weekday
- day
- month

CSV 不需要包含这些派生列。

---

## 数据质量要求

- 按时间升序排列。
- 不允许重复时间戳。
- OHLC 价格必须为有限的非负数，并满足 `high >= max(open, close)`、`low <= min(open, close)`。
- `volume` 和 `amount` 不得为负数。
- 缺失值应在生成训练文件前处理；不能把未来数据用于填充历史记录。
- 停牌、除权、异常价格跳变和上市时间不足的标的，应在训练前明确处理或排除。
- 训练、验证和测试必须按时间顺序切分，禁止随机打乱后跨时间切分。

---

## 当前评测约束

训练数据准备和模型评测必须保持相同的特征顺序、窗口定义和归一化边界。模型效果必须使用完整生产推理链路验证，详见 [`FINETUNE_REPORT.md`](FINETUNE_REPORT.md)。

## 训练/验证/封存测试切分

当前项目禁止随机切分时间序列。Phase 1 的统一切分和滚动评测规则见 [`EVALUATION_PROTOCOL.md`](EVALUATION_PROTOCOL.md)，执行入口为：

```powershell
\.venv311\Scripts\python.exe examples\build_eval_manifest.py `
  --output output\evaluation_manifest.json
```

注意：上面是 Phase 1 评测协议，不是历史微调脚本已经执行过的切分。历史配置
中的 `train_ratio=0.8`、`val_ratio=0.1`、`test_ratio=0.1` 是每个 CSV 清洗后
按行数比例切分；`finetune_base_model.py` 实际只创建 train/validation loader，
没有在训练日志中运行 test loader。新模型必须按日期生成独立的 train、validation
和封存 test manifest，不能继续把这个历史比例切分当成最终评测集。

Phase 1 默认时间边界为：训练 2019-01-01 至 2024-12-31；验证 2025-01-01 至
2025-12-31；最终封存测试 2026-01-01 至数据最新日期。

默认评测窗口为 90 日输入、5 日预测、5 个 bar embargo。同一股票的相邻目标区间不能重叠；同一日期的多只股票样本允许共同评测，但聚合置信区间必须按目标日期聚类 Bootstrap。

数据清单必须记录数据目录和文件名、市场与标的代码、文件起止日期和行数、时间边界、lookback、pred_len、sample_step、embargo、数据版本、清洗规则和 manifest hash。

如果某个模型 checkpoint 看过封存测试区间，即使推理时没有直接读取测试 CSV，也不能把该结果标记为最终 OOS。

## A 股/港股数据池注意事项

当前本地数据池包含 297 个 A 股文件和 84 个港股文件。manifest 默认选择 200 个 A 股和全部可用港股，选择是确定性的文件名排序，方便复现，但不是完整的 point-in-time 股票池。

在用于交易结论前，必须补充历史成分股、退市标的、上市/停牌状态、复权因子、行业分类、流动性和交易日历。当前数据池尚未单独证明不存在幸存者偏差，因此本阶段结果限定为预测模型评测。
