param(
  [Parameter(Mandatory=$true)][string]$Prompt,
  [string]$Root = "$env:USERPROFILE\MiniMax-H3-Conditioner",
  [string]$PythonExe = "python",
  [string]$Out = "",
  [string]$MacTarget = ""
)

$ErrorActionPreference = "Stop"

$Runtime = Join-Path $Root "h3.c-ane"
$PathsFile = Join-Path $Root "asset_paths.txt"
if (-not (Test-Path $PathsFile)) {
  throw "asset_paths.txt not found. Run setup_conditioner.ps1 first."
}

$Map = @{}
Get-Content $PathsFile | ForEach-Object {
  if ($_ -match "^([^=]+)=(.*)$") {
    $Map[$matches[1]] = $matches[2]
  }
}
$TE = $Map["TEXT_ENCODER"]
$Tokenizer = $Map["TOKENIZER"]
if (-not (Test-Path $TE)) { throw "Text encoder missing: $TE" }
if (-not (Test-Path $Tokenizer)) { throw "Tokenizer missing: $Tokenizer" }

if ([string]::IsNullOrWhiteSpace($Out)) {
  $CondDir = Join-Path $Root "conditionings"
  New-Item -ItemType Directory -Force -Path $CondDir | Out-Null
  $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $Out = Join-Path $CondDir "prompt-$Stamp.h3cd"
}

$Mint = Join-Path $Runtime "scripts\mint_h3_conditioning.py"
& $PythonExe $Mint --prompt $Prompt --te $TE --tokenizer $Tokenizer --device cuda --out $Out
if ($LASTEXITCODE -ne 0) { throw "Conditioning mint failed." }

Write-Host
Write-Host "Created: $Out"

if (-not [string]::IsNullOrWhiteSpace($MacTarget)) {
  if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "scp not found. Install the Windows OpenSSH Client or copy the .h3cd manually."
  }
  Write-Host "Copying to Mac: $MacTarget"
  scp $Out $MacTarget
  if ($LASTEXITCODE -ne 0) { throw "scp failed." }
}
