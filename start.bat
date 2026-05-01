@echo off
chcp 65001 >nul 2>&1
title KronosFinceptLab

echo ========================================
echo KronosFinceptLab
echo ========================================
echo.

cd /d "%~dp0"

REM 检查并安装 Python 依赖
echo [0/2] 检查 Python 依赖...
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo   正在安装缺失的依赖...
    pip install fastapi "uvicorn[standard]" pydantic python-multipart --quiet
    if errorlevel 1 (
        echo   依赖安装失败！请手动运行: pip install fastapi "uvicorn[standard]" pydantic python-multipart
        pause
        exit /b 1
    )
    echo   依赖安装完成！
) else (
    echo   依赖已就绪
)
echo.

echo [1/2] 启动 API 后端...
echo.

start "KronosFinceptLab API" cmd /k "cd /d %~dp0 && set PYTHONPATH=src && python -m kronos_fincept.api.app"

timeout /t 2 /nobreak >nul

echo [2/2] 启动 Web 前端...
echo.

start "KronosFinceptLab Web" cmd /k "cd /d %~dp0web && npm run dev"

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
