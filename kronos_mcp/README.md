# KronosFinceptLab MCP Server

Kronos 金融 K 线预测的 MCP (Model Context Protocol) 服务端。

## 工具列表

| Tool | 描述 |
|------|------|
| `forecast_ohlcv` | 单资产 OHLCV K 线预测 |
| `batch_forecast_ohlcv` | 多资产批量预测 + 收益率排名 |
| `fetch_a_stock` | 获取 A 股真实日 K 数据 (AkShare) |

## 安装

```bash
pip install -e ".[mcp,kronos,astock]"
```

## 运行

```bash
# 直接运行 (stdio transport)
python kronos_mcp/kronos_mcp_server.py

# 或以模块方式
python -m kronos_mcp.kronos_mcp_server
```

## MCP 客户端配置

### Claude Desktop / Cursor / 其他 MCP 客户端

在 MCP 客户端配置中添加:

```json
{
  "mcpServers": {
    "kronos-fincept": {
      "command": "python",
      "args": ["mcp/kronos_mcp_server.py"],
      "cwd": "/path/to/KronosFinceptLab",
      "env": {
        "PYTHONPATH": "src",
        "KRONOS_REPO_PATH": "/path/to/Kronos",
        "HF_HOME": "/path/to/model/cache"
      }
    }
  }
}
```

### FinceptTerminal Agent 集成

FinceptTerminal 的 Agent/Node Editor 可通过 MCP 协议调用 Kronos 预测能力:

1. Agent 收到用户请求: "分析招商银行未来 5 天走势"
2. Agent 调用 `fetch_a_stock` 获取 600036 历史数据
3. Agent 调用 `forecast_ohlcv` 获取预测
4. Agent 基于预测结果生成分析报告

## 使用示例

### 单资产预测

```json
{
  "tool": "forecast_ohlcv",
  "arguments": {
    "symbol": "600036",
    "pred_len": 5,
    "rows": [
      {"timestamp": "2026-04-01", "open": 1400, "high": 1420, "low": 1390, "close": 1410},
      ...
    ]
  }
}
```

### 批量排名

```json
{
  "tool": "batch_forecast_ohlcv",
  "arguments": {
    "pred_len": 5,
    "assets": [
      {"symbol": "600036", "rows": [...]},
      {"symbol": "000858", "rows": [...]},
      {"symbol": "601318", "rows": [...]}
    ]
  }
}
```

### 获取 A 股数据

```json
{
  "tool": "fetch_a_stock",
  "arguments": {
    "symbol": "600036",
    "start_date": "20250101",
    "end_date": "20260429"
  }
}
```
