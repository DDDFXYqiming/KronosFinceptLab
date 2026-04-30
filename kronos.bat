@echo off
REM Kronos CLI Launcher for Windows
REM Usage: kronos.bat forecast --symbol 601398 --pred-len 5
REM Usage: kronos.bat forecast --symbol 601398 --pred-len 5 --output table

set PROJECT_ROOT=E:\AI_Projects\KronosFinceptLab
set KRONOS_REPO_PATH=%PROJECT_ROOT%\external\Kronos
set HF_HOME=%PROJECT_ROOT%\external
set PYTHONPATH=%PROJECT_ROOT%\src;%KRONOS_REPO_PATH%

"%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%PROJECT_ROOT%\scripts\win_launcher.py" %*
