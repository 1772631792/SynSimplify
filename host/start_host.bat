@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "dist\SynSimplify.exe" (
    start "" "dist\SynSimplify.exe"
    exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
    echo 没找到 python，请先安装 Python 3.9+ 并加入 PATH
    pause
    exit /b 1
)

python main.py
if errorlevel 1 pause
