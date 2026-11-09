@echo off
cd /d "%~dp0"
echo Cierra Inventor antes de continuar.
pause
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0registrar.ps1"
if errorlevel 1 (
  echo La instalacion no termino bien.
  pause
  exit /b 1
)
echo.
echo Listo. Abre Inventor y usa la pestana Modulo Ingenieria.
pause
