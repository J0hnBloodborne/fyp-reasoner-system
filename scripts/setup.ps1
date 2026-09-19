param([switch]$SkipModel)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}

& $venvPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed' }

& $venvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Application dependency installation failed' }

& $venvPython -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.__version__, torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed' }

if (-not $SkipModel) {
    & $venvPython -m scripts.download_model
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed; rerun to resume' }
}

Write-Host 'Setup complete. Run: .\.venv\Scripts\python.exe -m traffic_poc --warmup'
