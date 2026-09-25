param(
  [string]$Root = "$env:USERPROFILE\MiniMax-H3-Conditioner",
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
Write-Host "=== RTX-side H3 conditioning setup ==="
Write-Host "Root: $Root"

New-Item -ItemType Directory -Force -Path $Root | Out-Null
$Runtime = Join-Path $Root "h3.c-ane"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git is required and was not found on PATH."
}

if (Test-Path (Join-Path $Runtime ".git")) {
  git -C $Runtime pull --ff-only
} else {
  git clone https://github.com/maderix/h3.c-ane.git $Runtime
}

& $PythonExe -c "import torch; print('Torch',torch.__version__,'CUDA',torch.version.cuda,'GPU',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE'); assert torch.cuda.is_available(), 'CUDA PyTorch is required'"
& $PythonExe -m pip install -U safetensors tokenizers "huggingface_hub[hf_xet]"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
& $PythonExe (Join-Path $Here "download_conditioner_assets.py") --root $Root

Write-Host
Write-Host "READY."
Write-Host "The BF16 text encoder is about 51.5 GB on disk."
Write-Host "Use mint_conditioning.ps1 to create one tiny .h3cd file per prompt."
