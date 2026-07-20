@echo off
chcp 65001 >nul 2>&1
title KronosFinceptLab (GPU - DirectML)

echo ========================================
echo  KronosFinceptLab GPU 启动器
echo  Python 3.11 + torch-directml (7800XT)
echo ========================================
echo.

cd /d "%~dp0"

REM ---- 低内存 / 线程限制 (NumPy/OpenBLAS 导入前) ----
set KRONOS_LOW_MEMORY_DEFAULTS=1
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set NUMEXPR_MAX_THREADS=1
set VECLIB_MAXIMUM_THREADS=1
set TOKENIZERS_PARALLELISM=false

REM ---- Web 代理 site-owner 认证 (前端无需输入 key) ----
REM 其余所有配置 (LLM/Kronos/HF_ENDPOINT/SSL) 已在 .env 中, 由 config.py 自动加载
set KRONOS_API_KEYS=local-dev-key
set KRONOS_ADMIN_API_KEYS=local-admin-key
set KRONOS_INTERNAL_API_KEY=local-internal-key

set PYTHONPATH=%~dp0src
set VENV_PY=%~dp0.venv311\Scripts\python.exe

if not exist "%VENV_PY%" (
  echo [错误] 未找到 venv311: %VENV_PY%
  echo 请先创建: uv venv --python 3.11 .venv311
  pause
  exit /b 1
)

echo [1/2] 启动 API 后端 (venv311 + DirectML GPU)...
start "KronosFinceptLab API" "%VENV_PY%" -m uvicorn kronos_fincept.api.app:app --host 0.0.0.0 --port 8000

echo [2/2] 启动 Web 前端 (Next.js)...
start "KronosFinceptLab Web" cmd /c "cd /d %~dp0web && set NEXT_IGNORE_INCORRECT_LOCKFILE=1 && npm run dev"

echo.
echo ========================================
echo  启动完成!
echo ========================================
echo  API 后端 : http://localhost:8000
echo  Web 前端 : http://localhost:3000
echo  API Key  : local-dev-key  (header: x-kronos-api-key)
echo  LLM      : deepseek-v4-flash (关思考)
echo  Kronos   : NeoQuasar/Kronos-base @ DirectML(7800XT)
echo.
echo  关闭此窗口不会停止服务。
echo  停止服务请运行 stop_kronos_gpu.bat
echo.
pause
