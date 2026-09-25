#!/bin/zsh
set -euo pipefail

ROOT="${H3_ROOT:-$HOME/MiniMax-H3-M4}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="$ROOT/runtime/h3.c-ane"
MODEL_DIR="$ROOT/MiniMax-H3"
VENV="$ROOT/venv"

echo "=== MiniMax H3 / M4 16GB setup ==="
echo "Root: $ROOT"

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: Apple Silicon arm64 is required."
  exit 2
fi

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Xcode Command Line Tools are required."
  echo "Starting Apple's installer..."
  xcode-select --install || true
  echo "Re-run this script after Command Line Tools finish installing."
  exit 3
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "ERROR: Homebrew is not installed."
  echo "Install Homebrew first, then re-run this script."
  exit 4
fi

echo "[1/6] Dependencies"
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
brew list git >/dev/null 2>&1 || brew install git

mkdir -p "$ROOT/runtime" "$ROOT/outputs" "$ROOT/conditionings"

echo "[2/6] h3.c-ane"
if [[ -d "$RUNTIME/.git" ]]; then
  git -C "$RUNTIME" fetch --all --prune
  git -C "$RUNTIME" pull --ff-only
else
  git clone https://github.com/maderix/h3.c-ane.git "$RUNTIME"
fi

echo "[3/6] Python helper environment"
PY="$(brew --prefix python@3.12)/bin/python3.12"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -U pip "huggingface_hub[hf_xet]"

echo "[4/6] Download minimal Mac model set"
"$VENV/bin/python" "$SCRIPT_DIR/download_mac_models.py" --root "$ROOT"

echo "[5/6] Build h3.c-ane"
make -C "$RUNTIME" -j"$(sysctl -n hw.ncpu)" h3

echo "[6/6] Inspect layout/device"
(
  cd "$RUNTIME"
  ./h3 --info -d "$MODEL_DIR"
)

echo
echo "=== READY ==="
echo "Mac runtime: $RUNTIME/h3"
echo "Models:      $MODEL_DIR"
echo "Outputs:     $ROOT/outputs"
echo "Conditioning:$ROOT/conditionings"
echo
echo "You still need a .h3cd conditioning file generated on the RTX 5080 machine."
echo "Then run smoke_test.sh first."
