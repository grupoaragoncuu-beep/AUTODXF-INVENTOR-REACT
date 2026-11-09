@echo off
cd /d "%~dp0"
dotnet build "AutoDXF.AddIn\AutoDXF.AddIn.csproj" -c Release
if errorlevel 1 exit /b 1
set "KIT=%~dp0paquete-usuario"
set "BIN=%~dp0AutoDXF.AddIn\bin\Release"
copy /Y "%BIN%\AutoDXF.AddIn.dll" "%KIT%\" >nul
copy /Y "%BIN%\AutoDXF.AddIn.comhost.dll" "%KIT%\" >nul
copy /Y "%BIN%\AutoDXF.AddIn.runtimeconfig.json" "%KIT%\" >nul
copy /Y "%BIN%\AutoDXF.AddIn.deps.json" "%KIT%\" >nul
copy /Y "%BIN%\AutoDXF.Core.dll" "%KIT%\" >nul
copy /Y "%~dp0AutoDXF.Inventor.addin" "%KIT%\" >nul
copy /Y "%~dp0servidor.txt" "%KIT%\" >nul
set "DEST=\\192.168.2.80\Grupo Arga Metals\Proyectos\Módulo Ingenieria\instalador"
mkdir "%DEST%" 2>nul
xcopy /Y /I /Q "%KIT%\*" "%DEST%\"
echo Paquete de usuarios listo en:
echo %DEST%
pause
