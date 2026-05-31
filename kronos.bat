@echo off
chcp 65001 >nul 2>&1
REM Kronos CLI Launcher for Windows
REM Usage: kronos.bat forecast --symbol 601398 --pred-len 5
REM Usage: kronos.bat --output table forecast --symbol 601398 --pred-len 5

set PROJECT_ROOT=E:\AI_Projects\KronosFinceptLab
set KRONOS_REPO_PATH=%PROJECT_ROOT%\external\Kronos
set HF_HOME=%PROJECT_ROOT%\external
set PYTHONPATH=%PROJECT_ROOT%\src;%KRONOS_REPO_PATH%
set KRONOS_LOW_MEMORY_DEFAULTS=1
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set NUMEXPR_MAX_THREADS=1
set VECLIB_MAXIMUM_THREADS=1
set TOKENIZERS_PARALLELISM=false

"%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%PROJECT_ROOT%\scripts\win_launcher.py" %*
