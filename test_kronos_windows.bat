@echo off
REM Kronos 模型服务测试脚本
REM 用于验证 Windows 上的 Kronos 模型部署是否成功

setlocal enabledelayedexpansion

echo === Kronos 模型服务测试 ===
echo.

REM 设置环境变量
set KRONOS_REPO_PATH=E:\AI_Projects\KronosFinceptLab\external\Kronos
set HF_HOME=E:\AI_Projects\KronosFinceptLab\external
set PYTHONPATH=E:\AI_Projects\KronosFinceptLab\src

echo 环境变量已设置:
echo   KRONOS_REPO_PATH: %KRONOS_REPO_PATH%
echo   HF_HOME: %HF_HOME%
echo   PYTHONPATH: %PYTHONPATH%
echo.

REM 检查 Python
echo [1/5] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未找到
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo ✅ %%i
echo.

REM 检查 PyTorch
echo [2/5] 检查 PyTorch...
python -c "import torch; print('PyTorch 版本:', torch.__version__)" >nul 2>&1
if errorlevel 1 (
    echo ❌ PyTorch 未找到
    echo 请安装 PyTorch: pip install torch
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python -c "import torch; print('PyTorch 版本:', torch.__version__)"') do echo ✅ %%i
echo.

REM 检查 kronos_fincept 包
echo [3/5] 检查 kronos_fincept 包...
python -c "import kronos_fincept; print('kronos_fincept 包已安装')" >nul 2>&1
if errorlevel 1 (
    echo ❌ kronos_fincept 包未找到
    echo 请安装包: cd E:\AI_Projects\KronosFinceptLab ^&^& pip install -e .
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python -c "import kronos_fincept; print('kronos_fincept 包已安装')"') do echo ✅ %%i
echo.

REM 检查模型文件
echo [4/5] 检查模型文件...
if exist "E:\AI_Projects\KronosFinceptLab\external\Kronos-small\model.safetensors" (
    echo ✅ Kronos-small 模型文件存在
) else (
    echo ❌ Kronos-small 模型文件不存在
    pause
    exit /b 1
)
echo.

REM 运行测试预测
echo [5/5] 运行测试预测...
echo.

REM 创建测试输入文件
echo {"symbol":"600519","timeframe":"1d","pred_len":5,"dry_run":false,"rows":[{"timestamp":"2026-04-01","open":1400,"high":1420,"low":1390,"close":1410},{"timestamp":"2026-04-02","open":1410,"high":1430,"low":1400,"close":1420},{"timestamp":"2026-04-03","open":1420,"high":1440,"low":1410,"close":1430},{"timestamp":"2026-04-04","open":1430,"high":1450,"low":1420,"close":1440},{"timestamp":"2026-04-07","open":1440,"high":1460,"low":1430,"close":1450},{"timestamp":"2026-04-08","open":1450,"high":1470,"low":1440,"close":1460},{"timestamp":"2026-04-09","open":1460,"high":1480,"low":1450,"close":1470},{"timestamp":"2026-04-10","open":1470,"high":1490,"low":1460,"close":1480},{"timestamp":"2026-04-11","open":1480,"high":1500,"low":1470,"close":1490},{"timestamp":"2026-04-14","open":1490,"high":1510,"low":1480,"close":1500}]} > temp_test_input.json

REM 运行预测
python -m kronos_fincept.cli --input temp_test_input.json > temp_test_output.json 2>&1

REM 检查结果
if errorlevel 1 (
    echo ❌ 测试失败
    echo 错误输出:
    type temp_test_output.json
    del temp_test_input.json >nul 2>&1
    del temp_test_output.json >nul 2>&1
    pause
    exit /b 1
)

REM 解析输出
for /f "tokens=*" %%i in ('python -c "import json; d=json.load(open('temp_test_output.json')); print('✅ 预测成功! 预测了', len(d.get('forecast', [])), '个时间点")') do echo %%i

echo.
echo === 测试完成 ===
echo.
echo Kronos 模型服务已成功部署到 Windows!
echo.
echo 使用方法:
echo   1. 进入 FinceptTerminal 脚本目录: cd E:\FinceptTerminal\scripts
echo   2. 运行预测: run_kronos_forecast.bat --test
echo   3. 查看详细文档: E:\AI_Projects\KronosFinceptLab\docs\WINDOWS_KRONOS_GUIDE.md
echo.

REM 清理临时文件
del temp_test_input.json >nul 2>&1
del temp_test_output.json >nul 2>&1

pause
