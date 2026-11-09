@echo off
setlocal
set "PLUGIN=%~dp0"
if "%PLUGIN:~-1%"=="\" set "PLUGIN=%PLUGIN:~0,-1%"
if "%~1"=="" (
  echo Uso: "Publicar version.bat" 1.0.0
  echo La carpeta de publicacion se lee de servidor.txt
  exit /b 1
)
set "VERSION=%~1"
if "%~2"=="" (
  for %%I in ("%PLUGIN%\..") do set "ORIGEN=%%~fI"
) else (
  set "ORIGEN=%~2"
)
if not exist "%PLUGIN%\servidor.txt" (
  echo Falta plugin\servidor.txt con la carpeta de publicacion.
  exit /b 1
)
set "GENOUT=%ORIGEN%\tools\InventorGenerativo"
set "GENPROJ=%ORIGEN%\..\BENDING MACHINE BUSBAR\SHEET METAL\InventorGenerativo\InventorGenerativo.csproj"
if exist "%GENPROJ%" (
  echo Compilando InventorGenerativo para el paquete...
  dotnet publish "%GENPROJ%" -c Release -o "%GENOUT%" -p:DebugType=none -p:DebugSymbols=false
  if errorlevel 1 exit /b 1
  del /q "%GENOUT%\*.pdb" 2>nul
  del /q "%GENOUT%\*.xml" 2>nul
)
if not exist "%GENOUT%\InventorGenerativo.exe" (
  echo Falta InventorGenerativo.exe en tools\InventorGenerativo.
  echo Compilalo en la PC de desarrollo antes de publicar. Sin ese programa la chapa falla en el cliente.
  exit /b 1
)
pushd "%ORIGEN%\ui"
call pnpm.cmd build
set "ERR=%ERRORLEVEL%"
popd
if not "%ERR%"=="0" exit /b %ERR%
dotnet build "%PLUGIN%\AutoDXF.Publicar\AutoDXF.Publicar.csproj" -c Release
if errorlevel 1 exit /b 1
"%PLUGIN%\AutoDXF.Publicar\bin\Release\AutoDXF.Publicar.exe" --destino-archivo "%PLUGIN%\servidor.txt" --version "%VERSION%" --origen "%ORIGEN%"
