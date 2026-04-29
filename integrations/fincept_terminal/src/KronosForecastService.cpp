// src/services/kronos/KronosForecastService.cpp
//
// Kronos K-line prediction service — implementation.
// Uses PythonRunner to call kronos_forecast.py as a subprocess.

#include "KronosForecastService.h"

#include "python/PythonRunner.h"
#include "core/logging/Logger.h"

#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

namespace fincept::kronos {

KronosForecastService& KronosForecastService::instance() {
    static KronosForecastService s;
    return s;
}

KronosForecastService::KronosForecastService() {
    LOG_INFO("Kronos", "KronosForecastService initialized");
    LOG_INFO("Kronos", "Bridge script: " + bridge_script_path());
    LOG_INFO("Kronos", "Available: " + QString(is_available() ? "yes" : "no"));
}

QString KronosForecastService::bridge_script_path() const {
    auto& runner = python::PythonRunner::instance();
    return runner.scripts_dir() + "/kronos_forecast.py";
}

bool KronosForecastService::is_available() const {
    return QFileInfo::exists(bridge_script_path());
}

// ── Forecast (single asset) ──────────────────────────────────────────────

void KronosForecastService::forecast(
    const QString& symbol,
    const QString& timeframe,
    int pred_len,
    const QJsonArray& rows_json,
    ForecastCallback cb,
    bool dry_run)
{
    if (!is_available()) {
        ForecastResult r;
        r.ok = false;
        r.error = "Kronos bridge script not found: " + bridge_script_path();
        cb(r);
        return;
    }

    // Build request JSON
    QJsonObject request;
    request["symbol"] = symbol;
    request["timeframe"] = timeframe;
    request["pred_len"] = pred_len;
    request["dry_run"] = dry_run;
    request["rows"] = rows_json;

    // Write to temp file (avoid command-line length limits)
    QString temp_dir = QStandardPaths::writableLocation(QStandardPaths::TempLocation);
    QString temp_input = temp_dir + "/kronos_req_" + QString::number QDateTime::currentMSecsSinceEpoch()) + ".json";
    {
        QFile f(temp_input);
        if (f.open(QIODevice::WriteOnly | QIODevice::Text)) {
            f.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
            f.close();
        } else {
            ForecastResult r;
            r.ok = false;
            r.error = "Failed to write temp request file";
            cb(r);
            return;
        }
    }

    // Call bridge script via PythonRunner
    auto& runner = python::PythonRunner::instance();
    QStringList args;
    args << "--input" << temp_input;

    runner.run("kronos_forecast.py", args,
        [cb = std::move(cb), temp_input](python::PythonResult py_result) {
            // Clean up temp file
            QFile::remove(temp_input);

            ForecastResult result;
            result.exit_code = py_result.exit_code;

            if (py_result.exit_code != 0 && py_result.output.isEmpty()) {
                result.ok = false;
                result.error = py_result.error;
                cb(result);
                return;
            }

            // Parse JSON output
            QString json_str = python::extract_json(py_result.output);
            QJsonParseError parse_err;
            QJsonDocument doc = QJsonDocument::fromJson(json_str.toUtf8(), &parse_err);

            if (parse_err.error != QJsonParseError::NoError || !doc.isObject()) {
                result.ok = false;
                result.error = "Failed to parse Kronos output: " + parse_err.errorString();
                cb(result);
                return;
            }

            result.data = doc.object();
            result.ok = result.data.value("ok").toBool(false);
            if (!result.ok) {
                result.error = result.data.value("error").toString("Unknown error");
            }

            cb(result);
        });
}

// ── Batch forecast ───────────────────────────────────────────────────────

void KronosForecastService::batch_forecast(
    const QJsonArray& assets,
    int pred_len,
    BatchCallback cb,
    bool dry_run)
{
    if (!is_available()) {
        cb(false, {}, "Kronos bridge script not found");
        return;
    }

    // Build batch request
    QJsonObject request;
    request["_action"] = "batch_forecast";
    request["assets"] = assets;
    QJsonObject shared;
    shared["pred_len"] = pred_len;
    shared["dry_run"] = dry_run;
    request["shared"] = shared;

    QString temp_dir = QStandardPaths::writableLocation(QStandardPaths::TempLocation);
    QString temp_input = temp_dir + "/kronos_batch_" + QString::number(QDateTime::currentMSecsSinceEpoch()) + ".json";
    {
        QFile f(temp_input);
        if (f.open(QIODevice::WriteOnly | QIODevice::Text)) {
            f.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
            f.close();
        } else {
            cb(false, {}, "Failed to write temp request file");
            return;
        }
    }

    auto& runner = python::PythonRunner::instance();
    QStringList args;
    args << "--input" << temp_input;

    runner.run("kronos_forecast.py", args,
        [cb = std::move(cb), temp_input](python::PythonResult py_result) {
            QFile::remove(temp_input);

            if (py_result.exit_code != 0 && py_result.output.isEmpty()) {
                cb(false, {}, py_result.error);
                return;
            }

            QString json_str = python::extract_json(py_result.output);
            QJsonParseError parse_err;
            QJsonDocument doc = QJsonDocument::fromJson(json_str.toUtf8(), &parse_err);

            if (parse_err.error != QJsonParseError::NoError) {
                cb(false, {}, "JSON parse error: " + parse_err.errorString());
                return;
            }

            QJsonObject root = doc.object();
            if (!root.value("ok").toBool(false)) {
                cb(false, {}, root.value("error").toString("Unknown error"));
                return;
            }

            // Parse ranked signals
            QVector<RankedSignal> signals;
            QJsonArray rankings = root.value("rankings").toArray();
            for (const auto& entry : rankings) {
                QJsonObject obj = entry.toObject();
                RankedSignal sig;
                sig.rank = obj.value("rank").toInt();
                sig.symbol = obj.value("symbol").toString();
                sig.last_close = obj.value("last_close").toDouble();
                sig.predicted_close = obj.value("predicted_close").toDouble();
                sig.predicted_return_pct = obj.value("predicted_return_pct").toDouble();
                sig.signal = obj.value("signal").toString();
                signals.append(sig);
            }

            cb(true, signals, {});
        });
}

// ── Fetch A-share data ──────────────────────────────────────────────────

void KronosForecastService::fetch_a_stock(
    const QString& symbol,
    const QString& start_date,
    const QString& end_date,
    ForecastCallback cb)
{
    if (!is_available()) {
        ForecastResult r;
        r.ok = false;
        r.error = "Kronos bridge script not found";
        cb(r);
        return;
    }

    QJsonObject request;
    request["_action"] = "fetch_a_stock";
    request["symbol"] = symbol;
    request["start_date"] = start_date;
    request["end_date"] = end_date;

    QString temp_dir = QStandardPaths::writableLocation(QStandardPaths::TempLocation);
    QString temp_input = temp_dir + "/kronos_fetch_" + QString::number(QDateTime::currentMSecsSinceEpoch()) + ".json";
    {
        QFile f(temp_input);
        if (f.open(QIODevice::WriteOnly | QIODevice::Text)) {
            f.write(QJsonDocument(request).toJson(QJsonDocument::Compact));
            f.close();
        } else {
            ForecastResult r;
            r.ok = false;
            r.error = "Failed to write temp request file";
            cb(r);
            return;
        }
    }

    auto& runner = python::PythonRunner::instance();
    QStringList args;
    args << "--input" << temp_input;

    runner.run("kronos_forecast.py", args,
        [cb = std::move(cb), temp_input](python::PythonResult py_result) {
            QFile::remove(temp_input);

            ForecastResult result;
            result.exit_code = py_result.exit_code;

            if (py_result.exit_code != 0 && py_result.output.isEmpty()) {
                result.ok = false;
                result.error = py_result.error;
                cb(result);
                return;
            }

            QString json_str = python::extract_json(py_result.output);
            QJsonParseError parse_err;
            QJsonDocument doc = QJsonDocument::fromJson(json_str.toUtf8(), &parse_err);

            if (parse_err.error != QJsonParseError::NoError) {
                result.ok = false;
                result.error = "JSON parse error: " + parse_err.errorString();
                cb(result);
                return;
            }

            result.data = doc.object();
            result.ok = result.data.value("ok").toBool(false);
            if (!result.ok) {
                result.error = result.data.value("error").toString("Unknown error");
            }
            cb(result);
        });
}

} // namespace fincept::kronos
