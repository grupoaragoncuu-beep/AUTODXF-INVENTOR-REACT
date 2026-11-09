$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dll = Join-Path $root "AutoDXF.AddIn.dll"
if (-not (Test-Path $dll)) { throw "Faltan los archivos del complemento junto a Instalar.bat." }

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
  Copy-Item (Join-Path $root $name) (Join-Path $dest $name) -Force
}
Copy-Item (Join-Path $root "AutoDXF.Inventor.addin") (Join-Path $addins "AutoDXF.Inventor.addin") -Force
Copy-Item (Join-Path $root "servidor.txt") (Join-Path $dest "servidor.txt") -Force

$comhost = Join-Path $dest "AutoDXF.AddIn.comhost.dll"
$reg = Start-Process -FilePath "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList @("/s", "/n", "/i:user", "`"$comhost`"") -Wait -PassThru
if ($reg.ExitCode -ne 0) {
  Write-Warning "Inventor puede cargar el modulo igual. Si no aparece, vuelve a ejecutar Instalar.bat como el mismo usuario de Windows."
}
Write-Output "Complemento instalado para este usuario."
