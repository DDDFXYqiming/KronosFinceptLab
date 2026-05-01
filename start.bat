@echo off
chcp 65001 >nul
title KronosFinceptLab

echo ========================================
echo KronosFinceptLab 启动中...
echo ========================================
echo.

:: 设置项目目录
set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 找不到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

:: 检查 Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 找不到 Node.js，请先安装 Node.js
    pause
    exit /b 1
)

:: 检查 npm
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 找不到 npm，请先安装 Node.js
    pause
    exit /b 1
)

:: 安装前端依赖（如果需要）
if not exist "web\node_modules" (
    echo 安装前端依赖...
    cd web
    call npm install
    cd ..
)

echo [1/2] 启动 API 后端...
echo       地址: http://localhost:8000
echo       文档: http://localhost:8000/docs
echo.

:: 启动 API 后端（新窗口）
start "KronosFinceptLab API" cmd /k "cd /d "%PROJECT_DIR%" && set PYTHONPATH=src && python -m kronos_fincept.api.app"

:: 等待 API 启动
timeout /t 3 /nobreak >nul

echo [2/2] 启动 Web 前端...
echo       地址: http://localhost:3000
echo.

:: 启动 Web 前端（新窗口）
start "KronosFinceptLab Web" cmd /k "cd /d "%PROJECT_DIR%\web" && npm run dev"

:: 等待前端启动
timeout /t 5 /nobreak >nul

echo ========================================
echo 启动完成！
echo ========================================
echo.
echo API 后端: http://localhost:8000
echo Web 前端: http://localhost:3000
echo API 文档: http://localhost:8000/docs
echo.
echo 按任意键打开浏览器...
pause >nul

:: 打开浏览器
start http://localhost:3000

echo.
echo 关闭此窗口不会停止服务
echo 如需停止服务，请关闭 "KronosFinceptLab API" 和 "KronosFinceptLab Web" 窗口
echo.
pause
