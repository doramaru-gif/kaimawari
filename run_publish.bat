@echo off
REM 承認済み Threads 投稿の公開（タスクスケジューラから10分おきに実行）

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
set PYTHONIOENCODING=utf-8
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

python publish_due.py >> "%SCRIPT_DIR%logs\publish.log" 2>&1
