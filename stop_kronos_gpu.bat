@echo off
chcp 65001 >nul 2>&1
title 停止 KronosFinceptLab

echo 正在停止 KronosFinceptLab 服务...
echo.

REM 停止 API (venv311 uvicorn)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo 停止 API 进程 PID=%%a
  taskkill /F /PID %%a >nul 2>&1
)

REM 停止 Web (Next.js / node on 3000)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
  echo 停止 Web 进程 PID=%%a
  taskkill /F /PID %%a >nul 2>&1
)

echo.
echo 服务已停止。
pause
