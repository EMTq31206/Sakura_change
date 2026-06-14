@echo off
chcp 65001 > nul
set "PRJ_ROOT=%~dp0"
set "SAKURA_PRJ_ROOT=%PRJ_ROOT%"

REM ============================================================
REM 检测非 ASCII 路径（PySide6 在非英文路径下会崩溃）
REM ============================================================
powershell -NoProfile -Command "$path = $env:SAKURA_PRJ_ROOT; if ($path -match '[^\x20-\x7E]') { exit 1 } else { exit 0 }" > nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "$path = $env:SAKURA_PRJ_ROOT; Write-Host '[错误] 项目路径包含非英文字符，PySide6 无法正常启动'; Write-Host '       请将项目移动到纯英文路径，如 D:\sakura'; Write-Host ('       当前路径: ' + $path)"
    pause
    exit /b 1
)

REM ============================================================
REM 激活 Anaconda sakura 环境
REM ============================================================
call "C:\ProgramData\anaconda3\Scripts\activate.bat" sakura
if errorlevel 1 (
    echo [错误] 无法激活 conda 环境 sakura
    pause
    exit /b 1
)

REM ============================================================
REM 检测 Python
REM ============================================================
set "PYTHON_EXE=C:\ProgramData\anaconda3\envs\sakura\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [错误] 未找到 Python: %PYTHON_EXE%
    pause
    exit /b 1
)

REM ============================================================
REM 设置 sentence-transformers 模型缓存到项目目录
REM ============================================================
set "HF_HOME=%PRJ_ROOT%\runtime\hf-cache"
set "SENTENCE_TRANSFORMERS_HOME=%PRJ_ROOT%\runtime\hf-cache"
if not exist "%HF_HOME%" mkdir "%HF_HOME%"

REM ============================================================
REM 启动
REM ============================================================
cd /d "%PRJ_ROOT%"
"%PYTHON_EXE%" main.py
pause
