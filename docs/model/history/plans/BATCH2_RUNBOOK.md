# 第二批（batch-2）执行清单

> 状态：Ready to run（G1 已通过：`fullv3_ep3cont_best` 为开发 Confirm 冠军）
> 前置：qlib 未安装，需先安装；tokenizer 配置已写入
> `external/Kronos/finetune_csv/configs/config_largecap_v8_tokenizer.yaml`（git 忽略）。

## 1. tokenizer 两阶段微调

阶段 A（tokenizer，重建 MSE + BSQ，LR 2e-4，2 epoch）：

```powershell
cd external\Kronos\finetune_csv
..\..\..\..\.venv311\Scripts\python.exe train_sequential.py `
  --config configs\config_largecap_v8_tokenizer.yaml
```

阶段 B（predictor，父模型 = `finetuned_largecap_v8_fullv3_ep3cont/basemodel/best_model`，
`finetuned_tokenizer` 指向 `finetuned_largecap_v8_tokenizer/tokenizer/best_model`，LR 5e-7、
3 epoch）：复制 `config_largecap_v8_fullv3_ep3cont.yaml` 并修改
`pretrained_predictor`、`finetuned_tokenizer`、`exp_name/base_path` 为
`largecap_v8_fttok_predictor` / `finetuned_largecap_v8_fttok_predictor`。

阶段 C：600 样本 Confirm（`eval_batch1_models.py` 追加两个 checkpoint：tokenizer-predictor
的 best 与 epoch_3），与官方、fullv3_ep3cont_best 同场比较；通过 v2 门槛才进入运行时切换。

## 2. 运行时 tokenizer 切换（仅当阶段 C 通过）

```powershell
New-Item -ItemType Junction -Path external\NeoQuasar\Kronos-Tokenizer-base `
  -Target external\Kronos\finetune_csv\finetuned_largecap_v8_tokenizer\tokenizer\best_model
```

切换前先跑完整生产路径评测（90 日/5 日、sc8 与 sc16）；旧 tokenizer 用 HF 快照
`0e0117387f39004a9016484a186a908917e22426` 回滚。

## 3. Qlib 正式回测

qlib 未安装。步骤：

```powershell
\.venv311\Scripts\pip.exe install pyqlib
```

然后新建 `examples/backtest_qlib_ah.py`：把上游 `external/Kronos/finetune/qlib_test.py` 的
TopkDropoutStrategy 适配到 clean_v8/v9 A/H 数据（5 日持有、Top20%、开仓 0.1%/平仓 0.15%、
换手/停牌/涨跌停约束、周调仓），输出年化收益/IR/最大回撤 vs 等权池与官方基线。回测通过后才
允许把开发 TopK 诊断称为经济证据。

## 4. 决策门

- tokenizer 候选通过 Confirm 且生产路径评测通过 → 切 junction，更新 DATASET_SPEC/MODEL_STATUS；
- 未通过 → 保持 `fullv3_ep3cont_best` 为研究候选、生产 junction 不变，以 Qlib 回测与严格 OOS
  作为最终证据。
