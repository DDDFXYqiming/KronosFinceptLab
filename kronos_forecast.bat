@echo off
REM Kronos Forecast - Windows 批处理脚本
REM 用于在 FinceptTerminal 中运行 Kronos 模型推理

setlocal enabledelayedexpansion

REM 设置项目路径
set PROJECT_ROOT=E:\AI_Projects\KronosFinceptLab
set KRONOS_REPO_PATH=%PROJECT_ROOT%\external\Kronos
set HF_HOME=%PROJECT_ROOT%\external
set PYTHONPATH=%PROJECT_ROOT%\src

REM 设置 FinceptTerminal 路径
set FINCEPT_SCRIPTS=E:\FinceptTerminal\scripts

echo === Kronos Forecast - Windows 批处理脚本 ===
echo.
echo 项目路径: %PROJECT_ROOT%
echo Kronos 模型: %KRONOS_REPO_PATH%
echo FinceptTerminal 脚本: %FINCEPT_SCRIPTS%
echo.

REM 检查 Python 是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请确保 Python 已安装并添加到 PATH
    pause
    exit /b 1
)

REM 检查 PyTorch 是否可用
python -c "import torch; print('PyTorch 版本:', torch.__version__)" >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 PyTorch，请确保已安装 PyTorch
    echo 安装命令: pip install torch
    pause
    exit /b 1
)

REM 检查 kronos_fincept 包是否可用
python -c "import kronos_fincept; print('kronos_fincept 包已安装')" >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 kronos_fincept 包，请先安装
    echo 安装命令: cd %PROJECT_ROOT% ^&^& pip install -e .
    pause
    exit /b 1
)

echo 环境检查通过！
echo.

REM 如果没有参数，显示帮助
if "%~1"=="" (
    echo 用法:
    echo   %0 [选项]
    echo.
    echo 选项:
    echo   --help          显示此帮助信息
    echo   --test          运行测试预测
    echo   --input FILE    从文件读取输入
    echo   --stdin         从标准输入读取
    echo   --batch         运行批量预测
    echo   --mcp           启动 MCP 服务器
    echo.
    echo 示例:
    echo   %0 --test
    echo   %0 --input request.json
    echo   echo {"symbol":"600519",...} ^| %0 --stdin
    pause
    exit /b 0
)

REM 处理参数
if "%~1"=="--help" (
    echo 用法:
    echo   %0 [选项]
    echo.
    echo 选项:
    echo   --help          显示此帮助信息
    echo   --test          运行测试预测
    echo   --input FILE    从文件读取输入
    echo   --stdin         从标准输入读取
    echo   --batch         运行批量预测
    echo   --mcp           启动 MCP 服务器
    pause
    exit /b 0
)

if "%~1"=="--test" (
    echo 运行测试预测...
    echo.
    
    REM 创建测试输入文件
    echo {"symbol":"600519","timeframe":"1d","pred_len":5,"dry_run":false,"rows":[{"timestamp":"2026-04-01","open":1400,"high":1420,"low":1390,"close":1410},{"timestamp":"2026-04-02","open":1410,"high":1430,"low":1400,"close":1420},{"timestamp":"2026-04-03","open":1420,"high":1440,"low":1410,"close":1430},{"timestamp":"2026-04-04","open":1430,"high":1450,"low":1420,"close":1440},{"timestamp":"2026-04-07","open":1440,"high":1460,"low":1430,"close":1450},{"timestamp":"2026-04-08","open":1450,"high":1470,"low":1440,"close":1460},{"timestamp":"2026-04-09","open":1460,"high":1480,"low":1450,"close":1470},{"timestamp":"2026-04-10","open":1470,"high":1490,"low":1460,"close":1480},{"timestamp":"2026-04-11","open":1480,"high":1500,"low":1470,"close":1490},{"timestamp":"2026-04-14","open":1490,"high":1510,"low":1480,"close":1500}]} > temp_test_input.json
    
    REM 运行预测
    python -m kronos_fincept.cli --input temp_test_input.json
    
    REM 清理临时文件
    del temp_test_input.json >nul 2>&1
    
    pause
    exit /b 0
)

if "%~1"=="--input" (
    if "%~2"=="" (
        echo 错误: --input 需要指定文件路径
        pause
        exit /b 1
    )
    
    echo 从文件 %~2 读取输入...
    python -m kronos_fincept.cli --input "%~2"
    pause
    exit /b 0
)

if "%~1"=="--stdin" (
    echo 从标准输入读取...
    python -m kronos_fincept.cli
    pause
    exit /b 0
)

if "%~1"=="--batch" (
    echo 运行批量预测...
    echo.
    
    REM 创建批量测试输入文件
    echo {"assets":[{"symbol":"600519","rows":[{"timestamp":"2026-04-01","open":1400,"high":1420,"low":1390,"close":1410},{"timestamp":"2026-04-02","open":1410,"high":1430,"low":1400,"close":1420},{"timestamp":"2026-04-03","open":1420,"high":1440,"low":1410,"close":1430},{"timestamp":"2026-04-04","open":1430,"high":1450,"low":1420,"close":1440},{"timestamp":"2026-04-07","open":1440,"high":1460,"low":1430,"close":1450},{"timestamp":"2026-04-08","open":1450,"high":1470,"low":1440,"close":1460},{"timestamp":"2026-04-09","open":1460,"high":1480,"low":1450,"close":1470},{"timestamp":"2026-04-10","open":1470,"high":1490,"low":1460,"close":1480},{"timestamp":"2026-04-11","open":1480,"high":1500,"low":1470,"close":1490},{"timestamp":"2026-04-14","open":1490,"high":1510,"low":1480,"close":1500}]},{"symbol":"000858","rows":[{"timestamp":"2026-04-01","open":100,"high":105,"low":95,"close":102},{"timestamp":"2026-04-02","open":102,"high":107,"low":100,"close":105},{"timestamp":"2026-04-03","open":105,"high":110,"low":103,"close":108},{"timestamp":"2026-04-04","open":108,"high":113,"low":106,"close":110},{"timestamp":"2026-04-07","open":110,"high":115,"low":108,"close":112},{"timestamp":"2026-04-08","open":112,"high":117,"low":110,"close":114},{"timestamp":"2026-04-09","open":114,"high":119,"low":112,"close":116},{"timestamp":"2026-04-10","open":116,"high":121,"low":114,"close":118},{"timestamp":"2026-04-11","open":118,"high":123,"low":116,"close":120},{"timestamp":"2026-04-14","open":120,"high":125,"low":118,"close":122}]}],"pred_len":5,"dry_run":false} > temp_batch_input.json
    
    REM 运行批量预测
    python -m kronos_fincept.cli --input temp_batch_input.json
    
    REM 清理临时文件
    del temp_batch_input.json >nul 2>&1
    
    pause
    exit /b 0
)

if "%~1"=="--mcp" (
    echo 启动 MCP 服务器...
    echo.
    echo 服务器将监听 stdin/stdout，用于 AI Agent 调用
    echo 按 Ctrl+C 停止服务器
    echo.
    python -m kronos_mcp.kronos_mcp_server
    pause
    exit /b 0
)

echo 未知选项: %~1
echo 使用 --help 查看帮助
pause
exit /b 1
