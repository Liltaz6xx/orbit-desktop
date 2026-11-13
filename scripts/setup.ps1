# Create a Python 3.12 virtual environment without requiring administrator rights.
param([switch]$NonInteractive)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

Write-Host 'ORBIT Desktop setup' -ForegroundColor Cyan
$python = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.12 with its Windows launcher from https://www.python.org/downloads/windows/.'
    }
    & py -3.12 -m venv (Join-Path $Root '.venv')
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not create the virtual environment. Install Python 3.12 and retry.'
    }
}
& $python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.prefix != sys.base_prefix else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'Existing .venv is invalid or uses the wrong Python. Rename .venv and run setup again.'
}

Write-Host 'Installing ORBIT dependencies into .venv...' -ForegroundColor Cyan
& $python -m pip install -r (Join-Path $Root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

$assets = Join-Path $Root 'assets'
$voiceFiles = [ordered]@{'kokoro-v1.0.int8.onnx' = 50000000; 'voices-v1.0.bin' = 20000000}
$missing = @($voiceFiles.Keys | Where-Object {
    $path = Join-Path $assets $_
    -not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -lt $voiceFiles[$_]
})
if ($missing.Count) {
    Write-Host "Missing or incomplete Kokoro files: $($missing -join ', ')" -ForegroundColor Yellow
    $download = if ($NonInteractive) { 'n' } else { Read-Host 'Download the Kokoro model and voices (about 136 MB)? [y/N]' }
    if ($download -match '^(y|yes)$') {
        & (Join-Path $PSScriptRoot 'download_voice_models.ps1') -AssetsDirectory $assets
    }
    else {
        Write-Host 'ORBIT uses Windows speech until the Kokoro assets are available.'
    }
}

$model = & $python -m orbit.diagnostics --model-name
if ($LASTEXITCODE -ne 0) { throw 'Check the ORBIT settings before continuing.' }
Write-Host 'Install or start Ollama for Windows if needed: https://ollama.com/download/windows'
Write-Host "If the local model is missing, run: ollama pull $model"
& $python -m orbit.diagnostics
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Setup installed the Python dependencies. Review the system check above for optional services and assets.' -ForegroundColor Yellow
}
exit 0
