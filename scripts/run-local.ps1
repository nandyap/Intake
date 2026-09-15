<#
.SYNOPSIS
    Run the whole solution on this machine. No Azure needed.

.DESCRIPTION
    Starts the backend and frontend in separate windows and opens the
    browser. Everything runs locally: stub agents, seed artifacts, state
    on disk. Nothing is sent to Azure and no credentials are required.

    First run installs dependencies, which takes a few minutes. Later runs
    start in seconds.

.PARAMETER SkipInstall
    Skip dependency installation when you know it is already done.

.EXAMPLE
    ./scripts/run-local.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$root     = Split-Path $PSScriptRoot -Parent
$backend  = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

# --- prerequisites ------------------------------------------------------------

function Resolve-Tool {
    param([string[]]$Candidates, [string]$Label, [string]$Hint)
    foreach ($c in $Candidates) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    throw "$Label not found. $Hint"
}

$python = Resolve-Tool -Candidates @('python', 'python3', 'py') `
    -Label 'Python' -Hint 'Install Python 3.11 or later from python.org.'
$npm = Resolve-Tool -Candidates @('npm') `
    -Label 'npm' -Hint 'Install Node.js 20 or later from nodejs.org.'

Write-Host "Python : $python"
Write-Host "npm    : $npm"
Write-Host ''

# --- dependencies -------------------------------------------------------------

if (-not $SkipInstall) {
    Write-Host 'Installing backend dependencies ...' -ForegroundColor Cyan
    & $python -m pip install --quiet --disable-pip-version-check `
        -r (Join-Path $backend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency install failed.' }

    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        Write-Host 'Installing frontend dependencies (a few minutes) ...' -ForegroundColor Cyan
        Push-Location $frontend
        try {
            & $npm install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency install failed.' }
        }
        finally { Pop-Location }
    }
    else {
        Write-Host 'Frontend dependencies already present.'
    }
    Write-Host ''
}

# --- .env ---------------------------------------------------------------------

$envFile = Join-Path $backend '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend '.env.example') $envFile
    Write-Host 'Created backend/.env from the example (stub mode).' -ForegroundColor Yellow
}

# --- start --------------------------------------------------------------------

Write-Host 'Starting backend on http://localhost:8000 ...' -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$backend'; & '$python' server.py"
) -WindowStyle Normal

# Give uvicorn a moment before the frontend starts proxying to it.
Start-Sleep -Seconds 3

Write-Host 'Starting frontend on http://localhost:3000 ...' -ForegroundColor Cyan
Start-Process pwsh -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$frontend'; & '$npm' run dev"
) -WindowStyle Normal

Start-Sleep -Seconds 6
Start-Process 'http://localhost:3000'

Write-Host ''
Write-Host 'Running.' -ForegroundColor Green
Write-Host '  Frontend  http://localhost:3000'
Write-Host '  Backend   http://localhost:8000/api/health'
Write-Host '  API docs  http://localhost:8000/docs'
Write-Host ''
Write-Host 'Start with a worked example on the "New submission" page.'
Write-Host 'Close the two windows to stop.'
