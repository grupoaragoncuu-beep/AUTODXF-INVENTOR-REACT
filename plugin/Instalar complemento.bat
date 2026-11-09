@echo off
cd /d "%~dp0"
dotnet build "AutoDXF.AddIn\AutoDXF.AddIn.csproj" -c Release
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0registrar.ps1"
if errorlevel 1 exit /b 1
