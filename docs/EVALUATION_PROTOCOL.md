# 当前金融预测评测协议

> 文档状态：Current
> 项目版本：10.9.0
> 最后核对：2026-07-29
> 当前阶段：Phase 1 — 可靠评测集重建

本文档是项目微调模型、预训练模型和后续交易回测的统一评测标准。它优先解决测试集污染、未来信息泄漏、重叠窗口造成的统计虚高和 A/HK 市场混合统计问题。

## 1. 当前结论边界

项目此前的约 150 个样本评测只能作为探索性实验。它使用了有限股票和重叠偏移窗口，并且多个 epoch/推理参数已经在相近数据上比较过，因此不能直接作为最终 OOS 结论。

当前已实现新的评测清单生成器：

```powershell
\.venv311\Scripts\python.exe examples\build_eval_manifest.py `
  --output output\evaluation_manifest.json
```

默认结果：

- 股票池：200 只 A 股 + 当前数据中可用的 84 只港股；
- 历史数据：使用 `external/Kronos/finetune_csv/data_v2` 中已有数据；
- 输入窗口：90 个交易日；
- 预测窗口：5 个交易日；
- 样本间隔：5 个目标 bar 的 embargo，样本步长默认为 10；
- 滚动折：2023、2024、2025、2026；
- 2026 折：标记为 `final_sealed_test`，只允许最终模型评估一次。

重要边界：当前默认 manifest 从 `external/Kronos/finetune_csv/data_v2` 生成，
而当前 V3 微调使用的是 `data_v3`。两者不是同一份训练快照，不能把该 manifest
直接解释为当前 V3 训练脚本的 train/validation/test 切分。`eval_rolling.py`
当前也只是加载一个指定 checkpoint 做推理，不会针对每个 fold 自动重新训练模型。

manifest 只保存文件名、行号、时间区间和划分信息，不复制原始行情文件。评测清单的默认产物为 `output/evaluation_manifest.json`，属于本地实验产物，不作为代码接口契约。

## 2. 三套数据划分

### 2.0 历史微调脚本的实际切分（现状核对）

历史微调配置虽然写有 `train_ratio=0.8`、`val_ratio=0.1`、`test_ratio=0.1`，
但实现是在每个 CSV 清洗后按**行数比例**独立切分，不是按统一日历日期切分。
`lookback_window=90`、`predict_window=10`，窗口步长为 1；训练集采样随机，
验证集按顺序读取。

更重要的是，`finetune_base_model.py::create_dataloaders()` 只创建 train loader
和 validation loader，没有创建 test loader；训练日志也只记录 Training Loss 和
Validation Loss。因此配置中的 `test_ratio` 只是保留在数据集切分逻辑中，历史
微调并没有真正运行最终测试集评估。

按当前文件和清洗逻辑重算的边界如下。这里的行数是切窗前的清洗后行数，不能
直接当作训练样本数：

| 数据版本 | 文件数 | 清洗后 train/val/test 行数 | train 分区最晚日期 | validation 分区最晚日期 |
|---|---:|---:|---|---|
| `data_v2` | 381 | 983,345 / 122,929 / 123,093 | 2025-12-17 | 2026-04-09（30 个标的） |
| `data_v3` | 497 | 775,571 / 96,836 / 97,229 | 2026-03-12（2 个标的） | 2026-05-19（35 个标的） |
| `data` | 385 | 335,624 / 41,920 / 42,202 | 2026-06-10 | 2026-07-02 |

因此，当前报告中的 V3 系列 checkpoint（`data_v3`）已经在训练分区中看到
2026 行情，并且 validation 也覆盖到 2026；`full_small` 系列也一样。V2 的
训练分区本身最晚到 2025-12-17，但有 30 个标的的 validation 延伸到 2026，
而 `best_model` 正是依据 validation loss 选择，所以也不能把 V2 的结果当成
严格未接触 2026 的最终测试结果。

### 2.1 全局训练/验证/最终测试

下面是 Phase 1 规定的目标协议，不是历史微调脚本已经执行过的切分：

默认时间边界如下：

| 分区 | 时间范围 | 用途 | 是否封存 |
|---|---|---|:---:|
| `train` | 2019-01-01 至 2024-12-31 | 微调模型参数 | 否 |
| `validation` | 2025-01-01 至 2025-12-31 | 选择 epoch、学习率、temperature、sample_count 等 | 否 |
| `test` | 2026-01-01 至数据最新日期 | 最终 OOS 评估 | 是 |

最终测试集不能参与模型、epoch、推理参数、股票池、数据清洗规则或回测策略选择。如果 checkpoint 曾经使用过 2026 数据，不能把它在 `test` 分区的结果称为干净的最终测试；必须使用不晚于 2025-12-31 的训练数据重新训练或继续训练，并保存数据截止日期和 manifest hash。

### 2.2 滚动起点评测折

滚动折用于观察不同市场阶段，而不是把所有年份拼成一个平均分：

| 折 | 参考训练截止日 | OOS 区间 | 当前角色 |
|---|---|---|---|
| `fold_2023` | 2019–2022 | 2023 | validation-like OOS |
| `fold_2024` | 2019–2023 | 2024 | validation-like OOS |
| `fold_2025` | 2024-12-31 | 2025 | validation-like OOS |
| `fold_2026` | 2025-12-31 | 2026 最新数据 | final sealed test |

当前 manifest 的具体配置是：90 日输入、5 日预测、5 个 bar embargo、样本步长
10；`fold_2025` 有 6,806 个窗口（A 股 4,787、港股 2,019），未封存；
`fold_2026` 覆盖 2026-01-01 至 2026-07-24，有 3,696 个窗口（A 股 2,599、
港股 1,097），已封存。这里的“参考训练截止日”只是协议标签；只有先用不晚于
该日期的数据重新训练并保存 provenance，才是真正的 rolling retraining。
不能把一次训练的 checkpoint 当成所有折的模型。

## 3. 窗口、间隔和泄漏规则

每个样本包含连续 90 个历史交易日和后续 5 个交易日目标。`target_start` 与 `target_end` 必须完整落在目标评测区间内。

同一股票的相邻评测样本默认满足：

```text
sample_step >= pred_len + embargo_bars
```

当前默认 `pred_len=5`、`embargo_bars=5`、`sample_step=10`。这保证目标区间不重叠，并在相邻标签之间留出间隔。不同股票在同一交易日的样本仍然可以共同评估；这类横截面相关性通过按 `target_end` 日期聚类 Bootstrap 处理。

禁止：随机打乱后切分时间序列；用全量数据计算归一化参数；使用目标区间之后的数据填补缺失值；使用未来的指数成分股或当前成分股回看历史；用最终测试集挑选模型或推理参数；把同一目标日期的重复窗口当作独立样本增加样本量。

## 4. 评测链路

模型评测必须与生产预测相同：

```text
raw CSV/DataFrame
  -> historical context validation
  -> rolling context normalization
  -> tokenizer encode
  -> autoregressive generation
  -> tokenizer decode
  -> inverse normalization
  -> original-price-space metrics
```

新增的 `examples/eval_rolling.py` 使用 `KronosPredictor.predict_batch()`，不允许绕过 tokenizer、生成和反归一化步骤直接在模型内部张量上计算最终指标。

评测执行采用三级流程，避免把昂贵的全量自回归推理用于每一个候选 checkpoint：

| 模式 | 数据规模 | `sample_count` | Bootstrap | 用途 |
|---|---:|---:|---:|---|
| `smoke` | 4 A 股 + 4 港股、共 16 窗口 | 1 | 0 | 检查模型加载和生产推理链路 |
| `screen` | 20 A 股 + 10 港股、每只 5 窗口，约 150 窗口 | 1 | 0 | 快速筛选所有候选模型 |
| `confirm` | 与 screen 相同 | 8 | 200 | 确认前两名和预训练基线 |
| `final` | `fold_2026` 全量，当前 3,696 窗口 | 1 | 1,000 | 冻结后只运行冠军和基线 |

冠军的生产参数复核使用固定的 256 个分层窗口，`sample_count=8`，不替代全量最终测试。
筛选和确认默认使用 `fold_2025`，不得使用封存的 `fold_2026` 选模型或参数。

推荐命令：

```powershell
\.venv311\Scripts\python.exe examples\eval_pipeline.py `
  --phase smoke `
  --manifest output\evaluation_manifest.json `
  --tokenizer-path <tokenizer-path> `
  --model-key v3_cont_epoch_2

\.venv311\Scripts\python.exe examples\eval_pipeline.py `
  --phase screen `
  --manifest output\evaluation_manifest.json `
  --tokenizer-path <tokenizer-path>

\.venv311\Scripts\python.exe examples\eval_pipeline.py `
  --phase confirm `
  --manifest output\evaluation_manifest.json `
  --tokenizer-path <tokenizer-path>

\.venv311\Scripts\python.exe examples\eval_pipeline.py `
  --phase final `
  --manifest output\evaluation_manifest.json `
  --tokenizer-path <tokenizer-path> `
  --model-key v3_cont_epoch_2 `
  --production-audit
```

需要复核全部历史候选模型时，可在 confirm 命令后增加 `--all-models`；日常模型选择
仍只确认 screen 前两名和预训练基线。

`eval_rolling.py` 每个 batch 输出吞吐量和 ETA，并在 `output/evaluation/` 下写入进度文件。
进程中断后默认从进度文件继续；不同评测进程使用全局锁，DirectML 不允许并发运行。
默认 batch size 为 64；若 DirectML 报内存错误，应降到 32，不应通过启动多个进程来提高 GPU 利用率。
Bootstrap 置信区间只在总体和 A/HK 聚合层计算；按股票、fold 和年份仍输出点估计，
但不重复计算与总体等价或样本过少的 Bootstrap。

当前已能从训练配置和日志确认：现有 V3、V3 continuation、V3 cont2 和
`full_small` checkpoint 都不满足 `fold_2026` 的干净 OOS 条件；V2 也因
validation 使用了部分 2026 数据而不满足严格条件。因此现在运行
`fold_2026` 只能作为诊断结果，不得写入最终模型报告。必须先制作数据截止
不晚于 2025-12-31 的新训练快照，重新训练/选择 checkpoint，再运行封存测试。

## 5. 报告指标

每次运行必须保存原始逐窗口结果，并提供：按样本的 Direction Accuracy、IC、RankIC；按股票聚合；A 股和港股分开；按滚动折和年份分组；按 `target_end` 日期聚类 Bootstrap 的 95% 置信区间。

统计量不能只保留冠军模型的点估计。报告必须同时记录样本数、股票数、目标日期数、模型路径、数据 manifest、推理参数和是否 sealed。

Direction Accuracy 不是唯一生产标准。第二阶段完成后还要加入成本后的收益、换手率、最大回撤、Sharpe/IR、滑点、手续费、涨跌停/停牌约束和执行时点。Kronos 官方仓库也将官方微调和简单回测示例定位为演示流程，并提示生产策略还需要组合优化、风险中性化、交易成本、滑点和市场冲击建模。

## 6. A 股/港股股票池规则

当前 manifest 的股票选择是按文件名排序的确定性选择，目的是先保证可复现。它还不是 point-in-time 成分股数据库，因此不能单独支撑“无幸存者偏差的交易回测”结论。

后续数据阶段必须补充：股票上市/退市/停牌历史，历史指数和行业成分股的生效日期，复权因子和除权除息处理记录，A 股与港股交易日历/时区/货币/交易制度，流动性筛选的当时可见信息，以及行业分类覆盖。

当前本地数据池包含 297 个 A 股文件和 84 个港股文件，日期覆盖 2010-01-04 至 2026-07-24。由于新股历史长度不同，manifest 只把能够完整形成窗口的股票计入对应折。

## 7. 后续阶段路线

### Phase 1 — 可靠评测集（当前）

- [x] 三套时间分区和滚动折 manifest；
- [x] A/HK 分组；
- [x] 非重叠目标窗口和 embargo；
- [x] 逐窗口结果、按股票/市场/年份聚合；
- [x] 日期聚类 Bootstrap 置信区间；
- [x] smoke/screen/confirm/final 分阶段评测入口；
- [x] 固定市场分层抽样、进度恢复和原子结果保存；
- [ ] 训练一个严格不包含 2026 数据的新 checkpoint；
- [ ] 在封存的 `fold_2026` 上运行最终评测。

### Phase 2 — 数据质量和 point-in-time 数据集

- 建立原始数据、清洗数据、评测数据三个版本；
- 固定复权和 corporate-action 规则；
- 增加 OHLCV 质量报告、缺失/停牌/异常跳变审计；
- 补齐历史成分股和退市标的；
- 增加行业和流动性分层；
- 对 2018/2020 扩展数据与当前数据做受控比较，暂不默认把 2010 数据全部混入。

### Phase 3 — 训练消融

每次只改变一个主要因素，并只用 validation 选择：数据清洗前后、A/HK 采样比例、历史长度 2022/2020/2018/2010、epoch/学习率/warmup/early stopping、tokenizer 是否重新适配，以及现有 OHLCV+amount 与新增特征的比较。

### Phase 4 — 成本约束回测和纸上交易

加入 A 股 T+1、涨跌停、停牌和卖出约束，港股交易时段、最小手数和流动性，手续费、印花税、滑点、市场冲击、组合规模、换手和容量；先纸上交易，再讨论任何生产默认配置。

## 8. 外部依据

- [Kronos 官方仓库](https://github.com/shiyu-coder/Kronos)：官方微调和简单回测是演示流程，生产还需要组合与交易约束。
- [Kronos AAAI 2026 论文](https://ojs.aaai.org/index.php/AAAI/article/view/39730)：Kronos 的金融 K 线预训练、tokenizer 和多任务评测背景。
- [Kronos 官方 Issue #265](https://github.com/shiyu-coder/Kronos/issues/265)：提醒核对预训练数据截止时间，避免把预训练见过的数据当成 OOS。
- [When Alpha Disappears](https://arxiv.org/html/2605.23959)：即使时间顺序正确，决策时点、归一化和执行语义仍可能造成评测膨胀。
- [Tashman, 2000](https://doi.org/10.1016/S0169-2070(00)00065-0)：滚动起点评测和 out-of-sample 比较的经典依据。
- [Forecast evaluation and leakage review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9718476/)：时间序列预处理、归一化和滚动评测中的泄漏风险。
- [Qlib 论文](https://arxiv.org/abs/2009.11189)：量化投资平台和时间序列研究工作流参考。
