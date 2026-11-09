@echo off
cd /d "%~dp0"
py -3 -m pip install -r "python\requirements.txt"
if errorlevel 1 exit /b 1
cd ui
call pnpm install
if errorlevel 1 exit /b 1
call pnpm build
if errorlevel 1 exit /b 1
cd ..
py -3 "python\host.py"
