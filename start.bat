@echo off
chcp 65001 >nul 2>&1
title KronosFinceptLab

echo ========================================
echo KronosFinceptLab
echo ========================================
echo.

cd /d "%~dp0"

set "PROJECT_ROOT=%~dp0"
set "PYTHON_EXE=%PROJECT_ROOT%.venv311\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo   未找到项目虚拟环境：%PYTHON_EXE%
    echo   请先创建 .venv311 并安装项目依赖后重新运行 start.bat
    pause
    exit /b 1
)

REM 低内存默认值：必须在 NumPy/Pandas/OpenBLAS 导入前设置
set KRONOS_LOW_MEMORY_DEFAULTS=1
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set NUMEXPR_MAX_THREADS=1
set VECLIB_MAXIMUM_THREADS=1
set TOKENIZERS_PARALLELISM=false

REM 检查并安装 Python 依赖
echo [0/3] 检查 Python 依赖...
"%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo   项目虚拟环境依赖不完整，请使用 .venv311 中的 Python 安装依赖后重试。
    pause
    exit /b 1
) else (
    echo   依赖已就绪
)
echo.

where node >nul 2>&1
if errorlevel 1 (
    echo   未找到 Node.js。请先安装 Node.js 后重新运行 start.bat
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo   未找到 npm。请确认 Node.js 安装目录已经加入 PATH
    pause
    exit /b 1
)

echo [1/3] 检查 Web 依赖...
node "%~dp0scripts\check_web_deps.js" --fix
if errorlevel 1 (
    echo   Web 依赖检查失败！请按上方提示修复后重新运行 start.bat
    pause
    exit /b 1
)
echo.

echo [2/3] 启动 API 后端...
echo.

set API_RELOAD_FLAG=
if "%KRONOS_API_RELOAD%"=="1" set API_RELOAD_FLAG=--reload

start "KronosFinceptLab API" cmd /k "cd /d ""%~dp0"" && set PYTHONPATH=src && ""%PYTHON_EXE%"" -m uvicorn kronos_fincept.api.app:app --host 127.0.0.1 --port 8000 %API_RELOAD_FLAG%"

timeout /t 2 /nobreak >nul

echo [3/3] 启动 Web 前端...
echo.

start "KronosFinceptLab Web" cmd /k "cd /d ""%~dp0web"" && set NEXT_IGNORE_INCORRECT_LOCKFILE=1&& npm run dev"

timeout /t 3 /nobreak >nul

echo ========================================
echo 启动完成！
echo ========================================
echo.
echo API 后端: http://localhost:8000
echo Web 前端: http://localhost:3000
echo.
echo 按任意键打开浏览器...
pause >nul

start http://localhost:3000

echo.
echo 关闭此窗口不会停止服务
echo 如需停止服务，请关闭 "KronosFinceptLab API" 和 "KronosFinceptLab Web" 窗口
echo.
pause
