$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin = Join-Path $root "AutoDXF.AddIn\bin\Release"
if (-not (Test-Path (Join-Path $bin "AutoDXF.AddIn.dll"))) { throw "No está compilado AutoDXF.AddIn.dll. Ejecuta Instalar complemento.bat." }

$addins = Join-Path $env:APPDATA "Autodesk\Inventor 2027\Addins"
$dest = Join-Path $addins "AutoDXF"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
foreach ($name in @(
  "AutoDXF.AddIn.dll",
  "AutoDXF.AddIn.comhost.dll",
  "AutoDXF.AddIn.runtimeconfig.json",
  "AutoDXF.AddIn.deps.json",
  "AutoDXF.Core.dll"
)) {
  $src = Join-Path $bin $name
  if (Test-Path $src) { Copy-Item $src (Join-Path $dest $name) -Force }
}
Get-ChildItem $bin -Filter "System.Security.Cryptography.ProtectedData.dll" -ErrorAction SilentlyContinue | ForEach-Object {
  Copy-Item $_.FullName (Join-Path $dest $_.Name) -Force
}
$fromPublish = Join-Path $root "AutoDXF.Publicar\bin\Release\System.Security.Cryptography.ProtectedData.dll"
if ((Test-Path $fromPublish) -and -not (Test-Path (Join-Path $dest "System.Security.Cryptography.ProtectedData.dll"))) {
  Copy-Item $fromPublish (Join-Path $dest "System.Security.Cryptography.ProtectedData.dll") -Force
}
Copy-Item (Join-Path $root "AutoDXF.Inventor.addin") (Join-Path $addins "AutoDXF.Inventor.addin") -Force
$serverFile = Join-Path $dest "servidor.txt"
if (-not (Test-Path $serverFile)) {
  Copy-Item (Join-Path $root "servidor.txt") $serverFile
}

$comhost = Join-Path $dest "AutoDXF.AddIn.comhost.dll"
if (Test-Path $comhost) {
  $reg = Start-Process -FilePath "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList @("/s", "/n", "/i:user", "`"$comhost`"") -Wait -PassThru
  if ($reg.ExitCode -ne 0) {
    Write-Warning "No pude registrar el complemento para COM (codigo $($reg.ExitCode)). Inventor 2027 igual puede cargarlo por el archivo .addin."
  }
}
Write-Output "Complemento instalado para este usuario. Cierra Inventor y vuelve a abrirlo. En servidor.txt escribe la carpeta del servidor."
