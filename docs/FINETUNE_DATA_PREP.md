# Kronos clean_v5_compact 微调数据规范

> 文档状态：Current
> 最后核对：2026-07-30

## 当前数据版本

本轮使用 `external/Kronos/finetune_csv/clean_v5_compact`。原始文件来自 395 只 A 股和
102 只可用港股，不扩大股票池。`data_v3` 保留不变；近期行情刷新写入独立的
`raw_v5_compact`，防止覆盖历史实验快照。

```powershell
\.venv311\Scripts\python.exe examples\refresh_compact_market_data.py --workers 4
\.venv311\Scripts\python.exe examples\prepare_clean_v5_compact.py
```

来源策略：

| 市场 | 获取链路 | 价格口径 |
|---|---|---|
| A 股 | 项目多源链路，BaoStock 优先，失败后 EastMoney、AkShare 等回退 | 前复权 `qfq` |
| 港股 | yfinance | `auto_adjust=True, repair=True` |

yfinance 的官方接口文档说明 `auto_adjust=True` 会自动调整全部 OHLC；`repair=True` 用于修复
100 倍单位错误、缺失和错误股息调整。AKShare 文档也提示复权接口存在数据源风险，因此所有
刷新结果仍必须经过下述本地校验：

- [yfinance history API](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html)
- [AKShare A 股历史行情](https://akshare.akfamily.xyz/data/stock/stock.html)
- [AKShare 数据风险说明](https://akshare.akfamily.xyz/data_tips.html)

## CSV 和清洗契约

必填列：

```text
timestamp, open, high, low, close, volume, amount
```

按顺序执行：

1. 删除无法解析和重复时间戳；
2. 删除 OHLCVA 缺失或非数值行；
3. 删除非正价格、负成交量和负成交额；
4. 删除违反 OHLC 关系的行；
5. 相邻收盘绝对变动超过 20% 只计数，保留原行；
6. 生成逐文件 SHA-256、日期范围、清洗计数和分区计数。

增量刷新会用新行替换同日期旧行。若重叠区间的价格尺度偏移超过 0.5%，该股票从
2021-08-01 重新获取，以降低复权尺度在拼接点不连续的风险。无法刷新的股票保留旧快照，
并记录在 `raw_v5_compact/refresh_report.json`。

## 紧凑共同日历

| 用途 | 日期 | 说明 |
|---|---|---|
| 训练 | 2022-01-01～2025-12-31 | 最近四年，包含 2024-09 后行情和完整 2025 |
| 验证 | 2026-01-01～2026-03-31 | 选模与确认 |
| 诊断 | 2026-04-01～2026-07-31 | 已观察的近期诊断，不称严格 OOS |
| 严格未来 OOS | 2026-08-01 起 | 模型冻结后前向积累 |

训练窗口固定 `lookback=90`、`predict_window=5`。训练窗口首行不得早于 2022-01-01；
验证和诊断窗口允许使用前期 90 日作为输入，但预测尾部必须完整位于自身分区。每个新分区
跳过前 5 个交易日作为 embargo。

CSV 保留早于 2022 的历史，仅用于训练起点附近的审计，不进入训练窗口。禁止恢复按单只股票
行数比例切分。

## 已知边界

当前版本仍不是完整 point-in-time 交易数据库：历史成分股、退市股、公司行动、停牌、
涨跌停状态和 A/H 成交量单位尚未完全统一。因此结果只用于模型预测能力比较，不用于宣称
可实现收益。

## 下一版大盘股数据计划

当前 `clean_v5_compact` 的评测股票池是按文件名确定性截取，并非按历史市值或指数成分筛选。
因此它不能直接代表 A/H 大盘股需求。下一版暂定为 `clean_v6_largecap`，先建立开发版池，
再补齐 point-in-time 成分快照后才允许用于严格 OOS 或生产结论。

开发版股票池优先覆盖沪深 300、上证 50、中证 100，以及恒生、恒生中国企业和恒生科技中的
大市值高流动性股票。历史成分必须记录生效日期和退出日期；若只能取得当前成分，manifest
必须标记 `development_only=true`，不得回填到历史训练或测试期。

候选权威来源：A 股使用中证指数公司的 CSI 300 资料和成分接口；港股使用恒生指数公司的
HSI、HSCEI、HSTECH 指数页面及方法文件。当前 AKShare 可以返回 2026-07-29 的 CSI 300
成分清单，现有数据文件覆盖其中 297/300 只；港股成分接口仍需单独稳定化，不能用当前列表
直接回填 2022～2025。

- [CSI 300 官方 factsheet](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/en/000300factsheeten.pdf)
- [Hang Seng Indexes](https://www.hsi.com.hk/eng/indexes/all-indexes/hsi)
- [Hang Seng China Enterprises Index](https://www.hsi.com.hk/eng/indexes/all-indexes/hscei)
- [Hang Seng TECH Index](https://www.hsi.com.hk/eng/indexes/all-indexes/hstech)

市值、指数成分、停牌和涨跌停状态先用于股票池筛选、窗口过滤和分层抽样，不立即扩展 Kronos
的 OHLCVA 输入维度。训练与评测仍保持 `lookback=90`、`predict_window=5` 和同一时间边界。
下一轮只比较两个模型：官方 `Kronos-small` 起点，以及在明确新增或实质修正窗口上以极低学习率
继续训练的 `v3_from_ftv1_cont`；旧模型仍只是挑战者，不能自动成为生产父模型。
