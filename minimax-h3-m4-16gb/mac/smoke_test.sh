#!/bin/zsh
set -euo pipefail

ROOT="${H3_ROOT:-$HOME/MiniMax-H3-M4}"
RUNTIME="$ROOT/runtime/h3.c-ane"
MODEL_DIR="$ROOT/MiniMax-H3"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 CONDITIONING.h3cd \"prompt text\" [output.mp4]"
  exit 2
fi

COND="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
PROMPT="$2"
OUT="${3:-$ROOT/outputs/m4-16gb-smoke.mp4}"
mkdir -p "$(dirname "$OUT")"

if [[ ! -s "$COND" ]]; then
  echo "ERROR: conditioning file not found: $COND"
  exit 3
fi
PROMPT_FILE="${COND}.prompt.txt"
if [[ -s "$PROMPT_FILE" ]]; then
  EXPECTED_PROMPT="$(cat "$PROMPT_FILE")"
  if [[ "$EXPECTED_PROMPT" != "$PROMPT" ]]; then
    echo "ERROR: prompt does not match the .h3cd sidecar."
    echo "The conditioning tensor is prompt-specific."
    echo "Expected: $EXPECTED_PROMPT"
    echo "Received: $PROMPT"
    exit 5
  fi
else
  echo "WARNING: no prompt sidecar found at $PROMPT_FILE"
  echo "Make sure the prompt exactly matches the one used to mint the .h3cd file."
fi
if [[ ! -x "$RUNTIME/h3" ]]; then
  echo "ERROR: h3 runtime missing. Run setup_mac.sh first."
  exit 4
fi

echo "=== M4 16GB smoke test ==="
echo "Output: 256x256, 22 frames (~0.92s), 4 steps"
echo "This is a memory/stability validation, not a quality target."
echo

cd "$RUNTIME"
H3_CONDITIONING_FILE="$COND" \
H3_ANE_FULL_BLOCKS=50 \
H3_ANE_ROTATE=1 \
H3_PROFILE=1 \
./h3 \
  -d "$MODEL_DIR" \
  -p "$PROMPT" \
  --width 256 --height 256 \
  --frames 22 --steps 4 \
  --ssd-streaming \
  -o "$OUT"

echo
echo "Smoke output: $OUT"
