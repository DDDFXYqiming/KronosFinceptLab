// src/services/kronos/KronosForecastService.h
//
// Kronos K-line prediction service for FinceptTerminal.
// Calls kronos_forecast.py via PythonRunner to generate OHLCV forecasts.
//
// Integration: add to CMakeLists.txt and instantiate in ServiceManager.
//
// Usage from Qt/QML:
//   KronosForecastService::instance().forecast(symbol, timeframe, pred_len,
//       rows_json, [](bool ok, QJsonObject result, QString err) { ... });
//
// Dependencies:
//   - kronos_forecast.py in fincept-qt/scripts/
//   - kronos_fincept Python package installed in active venv
//   - Kronos model weights (auto-downloaded from HuggingFace on first use)

#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <functional>

namespace fincept::kronos {

/// Forecast result
struct ForecastResult {
    bool ok = false;
    QJsonObject data;      // Full forecast JSON (forecast candles, metadata)
    QString error;         // Error message if ok=false
    int exit_code = -1;
};

/// Ranked signal from batch forecast
struct RankedSignal {
    int rank;
    QString symbol;
    double last_close;
    double predicted_close;
    double predicted_return_pct;
    QString signal;  // "BUY", "HOLD", "SELL"
};

/// Kronos K-line prediction service.
/// Singleton — owns the PythonRunner interaction for Kronos forecasting.
class KronosForecastService : public QObject {
    Q_OBJECT
  public:
    using ForecastCallback = std::function<void(ForecastResult)>;
    using BatchCallback = std::function<void(bool ok, QVector<RankedSignal> signals, QString error)>;

    static KronosForecastService& instance();

    /// Forecast future K-line candles for a single asset.
    /// \param symbol    Asset symbol (e.g. "600036", "BTC/USDT")
    /// \param timeframe Data interval ("1d", "1h", etc.)
    /// \param pred_len  Number of future candles to predict
    /// \param rows_json JSON array of OHLCV rows [{timestamp, open, high, low, close, volume, amount}]
    /// \param cb        Callback with forecast result
    /// \param dry_run   Use deterministic mock predictor (no model loading)
    void forecast(const QString& symbol,
                  const QString& timeframe,
                  int pred_len,
                  const QJsonArray& rows_json,
                  ForecastCallback cb,
                  bool dry_run = false);

    /// Batch forecast multiple assets and rank by predicted return.
    /// \param assets    JSON array of {symbol, rows} objects
    /// \param pred_len  Number of future candles per asset
    /// \param cb        Callback with ranked signals
    /// \param dry_run   Use deterministic mock predictor
    void batch_forecast(const QJsonArray& assets,
                        int pred_len,
                        BatchCallback cb,
                        bool dry_run = false);

    /// Fetch real A-share data via AkShare.
    /// \param symbol     6-digit A-share code (e.g. "600036")
    /// \param start_date YYYYMMDD
    /// \param end_date   YYYYMMDD
    /// \param cb         Callback with OHLCV data
    void fetch_a_stock(const QString& symbol,
                       const QString& start_date,
                       const QString& end_date,
                       ForecastCallback cb);

    /// Check if the bridge script is available
    bool is_available() const;

  signals:
    void forecast_completed(const QString& symbol, bool success);

  private:
    KronosForecastService();
    QString bridge_script_path() const;
};

} // namespace fincept::kronos
