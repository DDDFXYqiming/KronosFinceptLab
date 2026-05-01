# FinceptTerminal Integration Guide

## 端到端集成状态

### ✅ 已验证

| 组件 | 状态 | 说明 |
|------|------|------|
| Bridge 脚本 | ✅ 已部署 | `kronos_forecast.py` 已在 `fincept-qt/scripts/` |
| PythonWorker 协议 | ✅ 兼容 | 4-byte length-prefixed framing 测试通过 |
| Forecast (dry-run) | ✅ 通过 | 单资产预测返回正确 |
| Batch forecast | ✅ 通过 | 多资产排名返回正确 |
| Shutdown | ✅ 通过 | 干净退出 |
| Error handling | ✅ 通过 | 错误返回非崩溃 |
| C++ 服务层 | ✅ 已写 | `KronosForecastService.h/.cpp` |

### 待完成（需要编译 FinceptTerminal）

- [ ] 将 C++ 文件添加到 FinceptTerminal CMakeLists.txt
- [ ] 在 ServiceManager 中注册 KronosForecastService
- [ ] 在 UI 中添加 Kronos 预测面板
- [ ] 在 Python venv 中安装 kronos_fincept 包

---

## 快速集成步骤

### 1. 复制文件到 FinceptTerminal

```bash
# Bridge 脚本（已自动完成）
cp integrations/fincept_terminal/scripts/kronos_forecast.py \
   /path/to/FinceptTerminal/fincept-qt/scripts/

# C++ 服务层
cp integrations/fincept_terminal/src/KronosForecastService.h \
   /path/to/FinceptTerminal/fincept-qt/src/services/kronos/

cp integrations/fincept_terminal/src/KronosForecastService.cpp \
   /path/to/FinceptTerminal/fincept-qt/src/services/kronos/
```

### 2. 修改 CMakeLists.txt

在 `fincept-qt/CMakeLists.txt` 的 `SOURCES` 列表中添加:

```cmake
src/services/kronos/KronosForecastService.cpp
```

在 `HEADERS` 列表中添加:

```cmake
src/services/kronos/KronosForecastService.h
```

### 3. 注册服务

在 `ServiceManager.cpp` 或相关初始化文件中:

```cpp
#include "services/kronos/KronosForecastService.h"

// 在初始化函数中:
auto& kronos = fincept::kronos::KronosForecastService::instance();
Q_UNUSED(kronos); // 触发单例初始化
```

### 4. 安装 Python 依赖

在 FinceptTerminal 的 Python venv 中:

```bash
# 激活 venv
source /path/to/FinceptTerminal/fincept-qt/venv-numpy2/bin/activate

# 安装 kronos_fincept
cd /path/to/KronosFinceptLab
pip install -e ".[kronos,astock]"
```

### 5. 下载模型

```bash
# 通过 HuggingFace 镜像下载（中国网络更快）
python -c "
from huggingface_hub import snapshot_download
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
snapshot_download('NeoQuasar/Kronos-base', local_dir='external/Kronos-base')
snapshot_download('NeoQuasar/Kronos-Tokenizer-base', local_dir='external/Kronos-Tokenizer-base')
"
```

---

## C++ 使用示例

### 单资产预测

```cpp
#include "services/kronos/KronosForecastService.h"

auto& kronos = fincept::kronos::KronosForecastService::instance();

// 构建 OHLCV 数据
QJsonArray rows;
QJsonObject row1;
row1["timestamp"] = "2026-04-01";
row1["open"] = 1400;
row1["high"] = 1420;
row1["low"] = 1390;
row1["close"] = 1410;
rows.append(row1);
// ... 添加更多行

kronos.forecast("600036", "1d", 5, rows,
    [](fincept::kronos::ForecastResult result) {
        if (result.ok) {
            qDebug() << "Forecast:" << result.data;
        } else {
            qDebug() << "Error:" << result.error;
        }
    });
```

### 批量排名

```cpp
QJsonArray assets;
QJsonObject asset1;
asset1["symbol"] = "600036";
asset1["rows"] = rows1;
assets.append(asset1);
// ... 更多资产

kronos.batch_forecast(assets, 5,
    [](bool ok, QVector<fincept::kronos::RankedSignal> signals, QString error) {
        if (ok) {
            for (const auto& sig : signals) {
                qDebug() << sig.rank << sig.symbol << sig.signal
                         << sig.predicted_return_pct << "%";
            }
        }
    });
```

### 获取 A 股数据

```cpp
kronos.fetch_a_stock("600036", "20250101", "20260429",
    [](fincept::kronos::ForecastResult result) {
        if (result.ok) {
            int count = result.data.value("count").toInt();
            qDebug() << "Got" << count << "rows of A-share data";
        }
    });
```

---

## 文件清单

```
KronosFinceptLab/
├── integrations/fincept_terminal/
│   ├── scripts/
│   │   └── kronos_forecast.py          # Bridge 脚本（已部署到 FinceptTerminal）
│   ├── src/
│   │   ├── KronosForecastService.h     # C++ 服务层头文件
│   │   └── KronosForecastService.cpp   # C++ 服务层实现
│   └── qlib_adapter/
│       └── kronos_model_adapter.py     # Qlib/AI Quant Lab 适配器
├── tests/
│   └── test_fincept_integration.py     # 端到端集成测试（PythonWorker 协议）
└── docs/
    └── FINCEPT_INTEGRATION.md          # 本文档
```
