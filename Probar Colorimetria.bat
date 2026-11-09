@echo off
cd /d "%~dp0"
echo Cierra Colorimetría del módulo AutoDXF (Terminar) si está activa.
echo Luego usa la mini barra en Inventor: clasificacion + clic en cada pieza.
py -3 "python\probar_colorimetria.py"
pause
