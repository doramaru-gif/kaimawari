@echo off
REM 買いまわり帳 デイリー更新（タスクスケジューラから毎朝実行）
REM 1. 楽天市場APIでサイトを生成  2. Threads の下書きを作る  3. Git設定済みなら dist/ を push

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
set PYTHONIOENCODING=utf-8
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

python main.py >> "%SCRIPT_DIR%logs\daily.log" 2>&1
if errorlevel 1 exit /b %errorlevel%

python queue_cli.py draft >> "%SCRIPT_DIR%logs\daily.log" 2>&1

if exist "%SCRIPT_DIR%.git" (
  git add dist >> "%SCRIPT_DIR%logs\daily.log" 2>&1
  git commit -m "daily update" >> "%SCRIPT_DIR%logs\daily.log" 2>&1
  git push >> "%SCRIPT_DIR%logs\daily.log" 2>&1
)
