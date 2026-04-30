# KronosFinceptLab SPEC

> 当前版本: v3.0 (已完成)
> 目标: 独立的 Python + Web 金融量化分析平台

**上游项目**：
- Kronos: https://github.com/shiyu-coder/Kronos
- FinceptTerminal: https://github.com/Fincept-Corporation/FinceptTerminal

---

## 已完成功能 (v0.1 ~ v3.0)

### 核心引擎
- ✅ Schema 验证、数据适配器、服务层
- ✅ Kronos 推理封装（dry-run + real 模式）
- ✅ 采样参数：temperature, top_k, top_p, sample_count
- ✅ 多模型支持：Kronos-mini/small/base

### 数据源
- ✅ 多数据源自动降级架构（AkShare → BaoStock → Yahoo Finance）
- ✅ 统一数据源管理器（DataSourceManager）
- ✅ 指数退避重试 + 熔断机制 + 内存/文件缓存
- ✅ 加密货币数据源：Binance + OKX

### 服务层
- ✅ CLI 命令行（Click）
- ✅ API 服务（FastAPI）
- ✅ Web 前端（Next.js）
- ✅ MCP 服务器

### 量化功能
- ✅ 批量预测 + 排序
- ✅ 概率预测（Monte Carlo 采样）
- ✅ 策略回测

---

## 将来版本规划

### v4.0 — CFA 级别分析 (高优先级)

**目标**: 添加专业金融分析能力

**功能**:
1. DCF 模型（现金流折现）
2. 风险指标（VaR, Sharpe, Sortino）
3. 投资组合优化
4. 衍生品定价

**技术方案**:
- 纯代码实现，不需要大模型
- 使用 NumPy/Pandas 计算
- 参考 QuantLib 实现

**工作量**: 2-3 周

---

### v5.0 — QuantLib 套件 + 更多数据源 (中优先级)

**目标**: 扩展量化分析能力

**功能**:
1. 18 个量化分析模块（定价、风险、波动率）
2. 更多数据源连接器（扩展到 10+）
3. 全球市场数据（美股、港股、加密货币）

**技术方案**:
- 集成 QuantLib Python 绑定
- 扩展 DataSourceManager
- 添加 Yahoo Finance 全球数据

**工作量**: 3-4 周

---

### v6.0 — AI Agents + AI 量化实验室 (中优先级)

**目标**: 添加智能化分析能力

**功能**:
1. AI 投资顾问代理
2. 自然语言分析报告
3. ML 模型（因子发现、HFT）
4. 强化学习交易

**技术方案**:
- 接入大模型（DeepSeek/GPT-4/Claude）
- 使用 LangChain/LlamaIndex
- 集成 Scikit-learn/PyTorch

**工作量**: 4-6 周

**需要大模型的功能**:
- 用户问题："601398 现在可以买入吗？"
- 大模型输出：分析报告 + 投资建议
- 需要：自然语言理解 + 文本生成 + 推理能力

**不需要大模型的功能**:
- 传统 ML 模型（RandomForest, XGBoost）
- 因子分析
- 回测优化

---

### v7.0 — 实时交易 + 可视化工作流 (低优先级)

**目标**: 添加交易执行能力

**功能**:
1. 模拟交易引擎
2. 实时行情推送
3. 可视化工作流（节点编辑器）
4. 16 个经纪商集成

**技术方案**:
- WebSocket 实时推送
- React Flow 节点编辑器
- 券商 API 集成

**工作量**: 6-8 周

**注意**: 这个版本优先级较低，因为：
- 实时交易风险高
- 需要券商 API Key
- 合规要求严格

---

## 技术约束

### Python 版本
- 最低：Python 3.11
- 推荐：Python 3.13

### 模型部署
- 模型权重：external/Kronos-small (95MB)
- 推理环境：Windows Python 3.13.6 + PyTorch 2.11.0 (CPU)
- WSL 调用：通过 kronos.sh 调用 Windows Python

### 数据格式
- Kronos 必需字段：open, high, low, close
- 可选字段：volume, amount
- 预测输出：D1~D5 格式（不输出具体日期）

---

## 安全与风控

1. 所有预测结果默认仅用于 research/backtest/paper trading
2. 真实交易必须另行手动确认
3. 不存储券商 API Key
4. 日志中不输出敏感信息
5. 回测报告必须明确：不是投资建议

---

## 已确认决策

1. 项目名：KronosFinceptLab
2. 定位：独立平台（非集成层）
3. 技术栈：FastAPI + Next.js + Click
4. 默认模型：Kronos-small
5. 保留 FinceptTerminal 兼容层
6. CLI 支持 Hermes Agent 远程调用
7. 不做登录注册系统
8. 不做自动实盘交易
