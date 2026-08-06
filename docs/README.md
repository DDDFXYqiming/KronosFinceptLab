# KronosFinceptLab 文档中心

> 文档状态：Current
> 最后整理：2026-08-05

这是项目文档的唯一总入口。第一次了解项目建议依次阅读“快速开始 → 架构 → 模型与评测”。

## 项目使用

| 文档 | 内容 |
|---|---|
| [快速启动](START_GUIDE.md) | 本地安装、启动和常用流程 |
| [架构](ARCHITECTURE.md) | 前后端、预测服务、数据源和集成结构 |
| [API](API.md) | REST API 接口 |
| [CLI](CLI.md) | 命令行接口 |
| [部署](DEPLOYMENT.md) | 本地与部署配置 |
| [FinceptTerminal 集成](FINCEPT_INTEGRATION.md) | FinceptTerminal 接入 |
| [宏观证据规则](MACRO_EVIDENCE_POLICY.md) | 宏观分析引用和监控信号规则 |

## 模型、训练与评测

所有 Kronos 微调资料集中在 [模型文档中心](model/README.md)：

- [当前模型状态](model/current/MODEL_STATUS.md)：现在实际使用哪个模型，以及最新结论；
- [当前评测标准](model/current/EVALUATION_STANDARD.md)：当前唯一选模指标和晋级门槛；
- [当前评测流程](model/current/EVALUATION_PROTOCOL.md)：数据边界、600 样本 Confirm 和 OOS 纪律；
- [当前数据规范](model/current/DATASET_SPEC.md)：`clean_v8_largecap_recent` 数据版本；
- [训练历史](model/history/TRAINING_RESULTS.md)：所有本机微调目录及其状态；
- [评测历史](model/history/EVALUATION_RESULTS.md)：历代口径、结果和可比性说明。

评测原始产物（JSON、manifest、日志）的当前/归档布局见
[`output/README.md`](../../output/README.md)。

## 历史归档

[archive](archive/README.md) 只保存一次性审计、旧优化计划和其他项目历史。模型训练与评测历史已经
迁移到 [model/history](model/history/README.md)，不再分散在多个 archive 子目录。

## 文档状态约定

- `Current`：当前实施或决策依据；
- `Historical`：保留用于追溯，不参与当前选模；
- `Draft`：尚未采用的提案；
- 原始日志和 JSON 是证据，Markdown 是解释入口；若冲突，以当前标准下的同场原始结果为准。
