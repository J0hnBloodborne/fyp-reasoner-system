param(
    [int]$WaitForCudaPid = 0,
    [int]$WaitForModelPid = 0,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if ($WaitForCudaPid -gt 0) {
    Write-Host 'Waiting for CUDA PyTorch installation...'
    $cudaProcess = Get-Process -Id $WaitForCudaPid -ErrorAction SilentlyContinue
    if ($cudaProcess) { $cudaProcess | Wait-Process }
}

& $venvPython -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; x = torch.ones((16,16), device='cuda'); assert (x @ x)[0,0].item() == 16; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw 'CUDA verification failed' }

& $venvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }

& $venvPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Application tests failed' }

if ($WaitForModelPid -gt 0) {
    Write-Host 'Waiting for model download...'
    $modelProcess = Get-Process -Id $WaitForModelPid -ErrorAction SilentlyContinue
    if ($modelProcess) { $modelProcess | Wait-Process }
}

$env:TRAFFIC_OFFLINE = '1'
$sampleImage = Join-Path $projectRoot 'data\samples\bus.jpg'
if (Test-Path -LiteralPath $sampleImage) {
    & $venvPython -m scripts.tier2.smoke_model $sampleImage --runs 2
    if ($LASTEXITCODE -ne 0) { throw 'Real model smoke check failed' }
}

& $venvPython -m traffic_poc --port $Port --warmup
if ($LASTEXITCODE -ne 0) { throw 'Application startup failed' }
