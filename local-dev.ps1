param(
  [int]$FrontendPort = 5500,
  [int]$BackendPort  = 3000,
  [switch]$DBReset
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$publicDir  = Join-Path $root "public"
$backendDir = Join-Path $root "backend"
if (-not (Test-Path $publicDir))  { throw "Missing ./public" }
if (-not (Test-Path $backendDir)) { throw "Missing ./backend" }

$venvActivate = Join-Path $root ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) { $venvActivate = Join-Path $root "venv\Scripts\Activate.ps1" }

function New-Terminal {
  param([string]$WorkingDir, [string]$Command)
  Start-Process -FilePath "powershell" -ArgumentList @('-NoExit','-Command',"Set-Location `"$WorkingDir`"; $Command") | Out-Null
}

$frontendOrigin = "http://127.0.0.1:$FrontendPort"
$activate = ""
if (Test-Path $venvActivate) { $activate = "& `"$venvActivate`"" }

$frontendCmd = "$activate`npython -m http.server $FrontendPort --bind 127.0.0.1"

$backendLines = @()
if ($activate) { $backendLines += $activate }
$backendLines += "`$env:FRONTEND_ORIGIN = '$frontendOrigin'"
if ($DBReset) { $backendLines += "`$env:DB_RESET = '1'" }
$backendLines += "uvicorn backend.app:app --host 127.0.0.1 --port $BackendPort"
$backendCmd = ($backendLines -join "`r`n")

New-Terminal -WorkingDir $publicDir -Command $frontendCmd
New-Terminal -WorkingDir $root      -Command $backendCmd

Write-Host "Frontend: $frontendOrigin"
Write-Host "Backend : http://127.0.0.1:$BackendPort"
if ($DBReset) { Write-Host "DB_RESET=1 enabled for this run" -ForegroundColor Yellow }
