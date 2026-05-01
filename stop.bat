@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo    KronosFinceptLab - Stopping Services
echo ========================================
echo.

echo [1/3] Stopping API Backend (port 8000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   Killed PID %%a
)
echo.

echo [2/3] Stopping Web Frontend (port 3000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo   Killed PID %%a
)
echo.

echo [3/3] Cleaning up stray processes...
taskkill /FI "WINDOWTITLE eq KronosFinceptLab API*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq KronosFinceptLab Web*" /T /F >nul 2>&1
echo.

echo ========================================
echo    All KronosFinceptLab services stopped!
echo ========================================
timeout /t 2 /nobreak >nul
