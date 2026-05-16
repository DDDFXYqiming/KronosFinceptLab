# FinceptTerminal Integration Guide

## End-to-End Integration Status

### Verified

| Component | Status | Notes |
|-----------|--------|-------|
| Bridge script | Deployed | `kronos_forecast.py` is in `fincept-qt/scripts/` |
| PythonWorker protocol | Compatible | 4-byte length-prefixed framing tested |
| Forecast (dry-run) | Passed | Single-asset forecast returns correctly |
| Batch forecast | Passed | Multi-asset ranking returns correctly |
| Shutdown | Passed | Clean exit |
| Error handling | Passed | Errors return without crash |
| C++ service layer | Written | `KronosForecastService.h/.cpp` |

### Pending (requires FinceptTerminal compilation)

- [ ] Add C++ files to FinceptTerminal CMakeLists.txt
- [ ] Register KronosForecastService in ServiceManager
- [ ] Add Kronos forecast panel to UI
- [ ] Install kronos_fincept package in Python venv

---

## Quick Integration Steps

### 1. Copy Files to FinceptTerminal

```bash
# Bridge script (already done)
cp integrations/fincept_terminal/scripts/kronos_forecast.py \
   /path/to/FinceptTerminal/fincept-qt/scripts/

# C++ service layer
cp integrations/fincept_terminal/src/KronosForecastService.h \
   /path/to/FinceptTerminal/fincept-qt/src/services/kronos/

cp integrations/fincept_terminal/src/KronosForecastService.cpp \
   /path/to/FinceptTerminal/fincept-qt/src/services/kronos/
```

### 2. Modify CMakeLists.txt

Add to `fincept-qt/CMakeLists.txt` `SOURCES` list:

```cmake
src/services/kronos/KronosForecastService.cpp
```

Add to `HEADERS` list:

```cmake
src/services/kronos/KronosForecastService.h
```

### 3. Register Service

In `ServiceManager.cpp` or relevant initialization file:

```cpp
#include "services/kronos/KronosForecastService.h"

// In initialization function:
auto& kronos = fincept::kronos::KronosForecastService::instance();
Q_UNUSED(kronos); // Trigger singleton initialization
```

### 4. Install Python Dependencies

Inside FinceptTerminal's Python venv:

```bash
# Activate venv
source /path/to/FinceptTerminal/fincept-qt/venv-numpy2/bin/activate

# Install kronos_fincept
cd /path/to/KronosFinceptLab
pip install -e ".[kronos,astock]"
```

### 5. Download Models

```bash
# Download via HuggingFace mirror (faster in China)
python -c "
from huggingface_hub import snapshot_download
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
snapshot_download('NeoQuasar/Kronos-base', local_dir='external/Kronos-base')
snapshot_download('NeoQuasar/Kronos-Tokenizer-base', local_dir='external/Kronos-Tokenizer-base')
"
```

---

## C++ Usage Examples

### Single-Asset Forecast

```cpp
#include "services/kronos/KronosForecastService.h"

auto& kronos = fincept::kronos::KronosForecastService::instance();

// Build OHLCV data
QJsonArray rows;
QJsonObject row1;
row1["timestamp"] = "2026-04-01";
row1["open"] = 1400;
row1["high"] = 1420;
row1["low"] = 1390;
row1["close"] = 1410;
rows.append(row1);
// ... add more rows

kronos.forecast("600036", "1d", 5, rows,
    [](fincept::kronos::ForecastResult result) {
        if (result.ok) {
            qDebug() << "Forecast:" << result.data;
        } else {
            qDebug() << "Error:" << result.error;
        }
    });
```

### Batch Ranking

```cpp
QJsonArray assets;
QJsonObject asset1;
asset1["symbol"] = "600036";
asset1["rows"] = rows1;
assets.append(asset1);
// ... more assets

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

### Fetching A-Share Data

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

## File Inventory

```
KronosFinceptLab/
├── integrations/fincept_terminal/
│   ├── scripts/
│   │   └── kronos_forecast.py          # Bridge script (deployed to FinceptTerminal)
│   ├── src/
│   │   ├── KronosForecastService.h     # C++ service layer header
│   │   └── KronosForecastService.cpp   # C++ service layer implementation
│   └── qlib_adapter/
│       └── kronos_model_adapter.py     # Qlib/AI Quant Lab adapter
├── tests/
│   └── test_fincept_integration.py     # End-to-end integration test (PythonWorker protocol)
└── docs/
    └── FINCEPT_INTEGRATION.md          # This document
```