# Kronos CSVs微调数据准备规范

> 本文档说明如何准备 CSV 格式的 K 线数据，用于 Kronos 模型的微调（`finetune_csv/` 方案）。

---

## 1. CSV 列名规范（严格大小写敏感）

| 列名 | 类型 | 含义 | 必填 | 说明 |
|------|------|------|:----:|------|
| `timestamps` | 字符串/日期 | 时间戳 | ✅ | `pd.to_datetime()` 能解析的格式均可 |
| `open` | 浮点数 | 开盘价 | ✅ | |
| `close` | 浮点数 | 收盘价 | ✅ | |
| `high` | 浮点数 | 最高价 | ✅ | |
| `low` | 浮点数 | 最低价 | ✅ | |
| `volume` | 浮点数 | 交易量 | ✅ | 无数据可填 `0` |
| `amount` | 浮点数 | 交易金额 | ✅ | 无数据可填 `0` |

> 源码参考：`external/Kronos/finetune_csv/finetune_base_model.py` 第 40 行
> `self.feature_list = ['open', 'high', 'low', 'close', 'volume', 'amount']`

## 2. 示例数据

```
timestamps,open,close,high,low,volume,amount
2019/11/26 9:35,182.45215,184.45215,184.95215,182.45215,15136000,0
2019/11/26 9:40,184.35215,183.85215,184.55215,183.45215,4433300,0
2019/11/26 9:45,183.85215,183.35215,183.95215,182.95215,3070900,0
```

## 3. 脚本自动生成的时间特征（CSV 中无需提供）

源码第 60-64 行自动从 `timestamps` 列衍生：

```python
df['minute']   = df['timestamps'].dt.minute    # 分钟 (0-59)
df['hour']     = df['timestamps'].dt.hour      # 小时 (0-23)
df['weekday']  = df['timestamps'].dt.weekday   # 星期几 (0=周一, 6=周日)
df['day']      = df['timestamps'].dt.day       # 日 (1-31)
df['month']    = df['timestamps'].dt.month     # 月 (1-12)
```

> 所以 CSV 中 **不需要** 包含 `minute` / `hour` / `weekday` / `day` / `month` 列。

## 4. 时间戳格式要求

`pd.to_datetime()` 能解析的任何格式均可：

| 格式 | 示例 |
|------|------|
| `YYYY/M/D H:mm` | `2019/11/26 9:35` |
| `YYYY-MM-DD HH:MM:SS` | `2024-01-15 14:30:00` |
| `YYYY-MM-DD` | `2024-01-15` |
| Unix 时间戳 | 整数（秒/毫秒） |

## 5. 数据量要求

默认配置：
```yaml
lookback_window: 512    # 历史窗口（输入长度）
predict_window: 48      # 预测窗口（输出长度）
```

每条样本需要 `512 + 48 + 1 = 561` 个连续时间点。  
建议 CSV 总行数 **≥ 2000 行**。示例数据有 5030 行。

## 6. 数据拆分方式

按比例顺序切分（按时间排序后）：

```
整个 CSV（按时间排序后）
  ├── 前 train_ratio % → 训练集
  ├── 接下来 val_ratio % → 验证集
  └── 最后 test_ratio % → 测试集
```

YAML 默认：`train_ratio: 0.9, val_ratio: 0.1, test_ratio: 0.0`

## 7. 注意事项

- 列名必须小写英文（`timestamps` 不是 `timestamp` 或 `datetime`）
- `amount` 如果没数据填 `0`，但不能缺列
- 数据按时间升序排列（脚本会在读入后自动排序）
- 不能有缺失值（脚本会用 forward fill 自动填充）
- 单价数据建议使用浮点数，保留足够精度
