# Kronos clean_v8_largecap_recent PIT 数据规范

> 文档状态：Current
> 数据版本：`clean_v8_largecap_recent`
> 最后核对：2026-08-06

## 当前数据版本

| 项目 | 值 |
|---|---|
| 清洗目录 | `external/Kronos/finetune_csv/clean_v8_largecap_recent` |
| 原始目录 | `external/Kronos/finetune_csv/raw_v7_largecap` |
| 数据文件 | 581（687,557 行） |
| A 股 | 439（历史 CSI 300 并集） |
| 港股 | 142（历史 HSI/HSCEI/HSTECH 并集） |
| 评测 manifest | `output/evaluation_manifest_largecap_v8_recent.json` |
| 数据状态 | `development_only=true, point_in_time_constituents=true` |

A 股股票池由 BaoStock 历史 CSI 300 快照构建，共识别 13 个实际变更快照；港股股票池来自恒生
指数公司 2021-02 至 2026-05 的 22 期官方季度评审 PDF。训练和评测窗口均以预测起点日期判断
当时成员资格，不再使用当前成分股倒推历史。A/H 目标代码文件覆盖率均为 100%。

行情统一采用前复权：A 股为 BaoStock qfq，港股为 AKShare/Sina qfq。独立复权因子序列受当前
免费数据源限制尚未纳入，因此公司行动只能通过前复权价格吸收，不能作为单独事件特征使用。

## CSV 与清洗契约

必填列：

```text
timestamp, open, high, low, close, volume, amount
```

本版共输入 687,682 行，清洗顺序：

1. 删除无法解析和重复时间戳；
2. 删除 OHLCVA 缺失或非数值行；
3. 删除非正价格、负成交量和负成交额；
4. 删除违反 OHLC 关系的行；
5. 相邻收盘绝对变动超过 20% 只标记，不自动删除；
6. 记录市场、日期范围、清洗计数和文件校验值。

实际删除 12 条非正价格和 113 条 OHLC 关系错误记录；没有重复、缺失、负成交量或负成交额；
358 个超过 20% 的收盘跳变仅标记保留。

数据源和复权口径必须在 manifest 中记录。A/H 股成交量、成交额单位不得在同一模型输入中静默混用；
公司行动、停牌和涨跌停状态仍属于待补生产数据治理项目。

## 时间划分

| 用途 | 日期 | 角色 |
|---|---|---|
| 训练 | 2022-01-01～2026-04-30 | 模型拟合 |
| 验证 | 2026-05-01～2026-07-31 | screen/confirm 和选模 |
| 诊断 | 2026-08-01 起（当前为空） | 模型冻结后的近期诊断 |
| 严格未来 OOS | 2026-08-01 起且未参与调参的新数据 | 冻结后前向检验 |

窗口固定为 `lookback=90`、`predict_window=5`。验证和诊断窗口可使用前一分区的 90 日历史作为
输入，但目标区间必须完整位于自身分区。评测窗口按 manifest 采用固定间隔，避免同一股票目标区间
高度重叠。

## 评测池

`evaluation_manifest_largecap_v8_recent.json` 包含：

- `validation_2026_05_07`：2,447 个 PIT 候选窗口、432 只股票；用于本轮 screen/confirm；
- `diagnostic_2026_08_forward`：当前为空，等模型冻结后补充新行情；
- `sample_step=10`、`pred_len=5`、`embargo_bars=5`，同一股票目标窗口不重叠。

固定 Confirm 样本文件为 `configs/evaluation/evaluation_samples_v4.json`，共600个样本，哈希为
`b54adb619ddcce54b5b0f7b8bac60f50640b5dda1f0d06499add7137cd42e423`。

数据重建入口按阶段执行并支持行情断点续传：

```powershell
.\.venv311\Scripts\python.exe examples\build_clean_v7_largecap.py --stage universe
.\.venv311\Scripts\python.exe examples\build_clean_v7_largecap.py --stage fetch --resume --hk-workers 4
.\.venv311\Scripts\python.exe examples\build_clean_v7_largecap.py --stage clean
.\.venv311\Scripts\python.exe examples\build_clean_v7_largecap.py --stage manifest
```

本轮 clean_v8 由同一构建器从已获取的 `raw_v7_largecap` 重建，未修改 raw_v7，也未使用
2026-08-01 之后的数据。

## 已知边界与下一版要求

当前版本已解决历史指数成员的 PIT 选择，但还不是完整 point-in-time 交易数据库。后续数据工作只
解决以下生产性问题，不围绕相同数据继续搜索局部训练参数：

- 独立复权因子及公司行动事件；
- 停牌、涨跌停和不可交易状态；
- 退市日至最后可交易日的状态确认；
- 模型冻结后新增数据的严格 OOS 标记。

## 相关文档

- [当前模型状态](MODEL_STATUS.md)
- [当前评测标准](EVALUATION_STANDARD.md)
- [当前评测流程](EVALUATION_PROTOCOL.md)
- [训练历史](../history/TRAINING_RESULTS.md)
- [历史数据质量计划](../history/plans/DATA_QUALITY_PLAN.md)
