# MiniMax H3 — M4 16GB deployment

This preset is for a base Apple M4 Mac with 16 GB unified memory.

It deliberately does not use the normal ComfyUI/MPS H3 path. The current official
INT8/FP8 ComfyUI path still hits unsupported MPS operators on Apple Silicon, while
the BF16 path requires far more unified memory.

Instead, this project uses:

- Mac: maderix/h3.c-ane
  - 21 GB pruned INT8 ConvRot H3 DiT
  - SSD weight streaming
  - rotating ANE programs
  - Metal for packing and VAE
  - precomputed prompt conditioning
- RTX 5080 PC: released 51.5 GB BF16 Qwen3-VL H3 text encoder
  - loaded layer-by-layer by mint_h3_conditioning.py
  - produces a small prompt-specific .h3cd
  - the .h3cd is copied to the Mac

So the Mac generates video and audio locally, but prompt encoding is prepared on
the RTX machine.

## Important status

The upstream ANE fork has been publicly tested on a base 24 GB M4, not 16 GB.
Its published 512-output / 384-internal / 4 s / 6-step demo peaked around 2.1 GB
RAM because it streams the 21 GB DiT from SSD and rotates compiled ANE programs.

That makes 16 GB plausible, but this repository treats it as an experiment until
your machine completes the smoke test.

The ANE fork uses Apple's private AppleNeuralEngine.framework APIs. A macOS
update can break it, and it is not suitable for App Store software.

## Disk requirements

Plan for at least 100 GB free before the first full test.

Mac model payload is roughly:

- DiT INT8 ConvRot: about 21 GB
- Video VAE FP16: about 5.21 GB
- Audio VAE FP32: about 0.605 GB
- tokenizer/config: small

The first ANE compile can add about 19 GB per fixed shape under
$TMPDIR/h3-ane-cache. Apple's /Library/Caches/com.apple.aned may keep another
copy, so one test shape can consume roughly another 38 GB of cache in total.

The RTX conditioner needs an additional 51.5 GB BF16 text encoder on disk.

## Repository layout

    minimax-h3-m4-16gb/
    ├── mac/
    │   ├── setup_mac.sh
    │   ├── download_mac_models.py
    │   ├── smoke_test.sh
    │   ├── render_4s.sh
    │   └── cleanup_ane_cache.sh
    ├── windows/
    │   ├── setup_conditioner.ps1
    │   ├── download_conditioner_assets.py
    │   └── mint_conditioning.ps1
    └── shared/
        └── example_prompt.txt

## 1. Clone this deployment branch on both machines

    git clone -b minimax-h3-m4-16gb-ane https://github.com/whichow/whichow.github.io.git H3-M4-Deploy

## 2. Mac setup

Open Terminal on the M4 Mac:

    cd H3-M4-Deploy
    zsh minimax-h3-m4-16gb/mac/setup_mac.sh

The script:

1. checks Apple Silicon
2. requires Xcode Command Line Tools
3. installs ffmpeg, Python 3.12 and Git through Homebrew
4. clones or updates maderix/h3.c-ane
5. downloads the minimal Mac model set
6. arranges the model tree exactly as h3.c expects
7. builds h3
8. runs h3 --info

Default root:

    ~/MiniMax-H3-M4/

Model layout after setup:

    ~/MiniMax-H3-M4/MiniMax-H3/
    └── FL2VA/
        ├── transformer/
        │   ├── config.json
        │   └── minimax_h3_fl2va_pruned_int8_convrot.safetensors
        ├── tokenizer/
        │   └── tokenizer.json
        ├── video_vae/
        │   └── source/
        │       └── minimax_h3_video_vae_fp16.safetensors
        └── audio_vae/
            └── minimax_h3_audio_vae_fp32.safetensors

The Mac intentionally has no FL2VA/text_encoder directory.

## 3. Prepare the RTX 5080 conditioning machine

Use the Python environment that already has your CUDA PyTorch. For a portable
ComfyUI install this is often its embedded Python.

Example:

    cd H3-M4-Deploy
    powershell -ExecutionPolicy Bypass -File .\minimax-h3-m4-16gb\windows\setup_conditioner.ps1 -PythonExe "D:\AI\ComfyUI\python_embeded\python.exe"

The script verifies CUDA, installs the helper packages, clones h3.c-ane, then
downloads:

    qwen3vl_32b_minimax_h3_bf16.safetensors   about 51.5 GB
    tokenizer.json

The BF16 encoder is large on disk, but mint_h3_conditioning.py streams it
layer by layer and computes in float32 on CUDA rather than keeping the complete
51.5 GB model resident in the 5080 VRAM.

## 4. Mint a prompt conditioning file

Every different prompt needs its own .h3cd. Use the exact same prompt later on
the Mac.

    $Prompt = Get-Content .\minimax-h3-m4-16gb\shared\example_prompt.txt -Raw
    powershell -ExecutionPolicy Bypass -File .\minimax-h3-m4-16gb\windows\mint_conditioning.ps1 -PythonExe "D:\AI\ComfyUI\python_embeded\python.exe" -Prompt $Prompt

This creates two files:

    prompt-YYYYMMDD-HHMMSS.h3cd
    prompt-YYYYMMDD-HHMMSS.h3cd.prompt.txt

The prompt sidecar is deliberate: the Mac runner checks it and refuses an
accidental prompt and conditioning mismatch.

## Optional: copy directly to the Mac with SCP

First enable Remote Login on the Mac:

    System Settings -> General -> Sharing -> Remote Login

Then:

    $Prompt = Get-Content .\minimax-h3-m4-16gb\shared\example_prompt.txt -Raw
    powershell -ExecutionPolicy Bypass -File .\minimax-h3-m4-16gb\windows\mint_conditioning.ps1 -PythonExe "D:\AI\ComfyUI\python_embeded\python.exe" -Prompt $Prompt -MacTargetDir "YOUR_MAC_USER@YOUR_MAC_IP:~/MiniMax-H3-M4/conditionings/"

If you do not want SSH enabled, copy both files manually.

## 5. M4 16GB smoke test first

Do not start with the 4-second render.

On the Mac:

    cd H3-M4-Deploy
    PROMPT="$(cat minimax-h3-m4-16gb/shared/example_prompt.txt)"
    zsh minimax-h3-m4-16gb/mac/smoke_test.sh ~/MiniMax-H3-M4/conditionings/prompt-XXXXXXXX-XXXXXX.h3cd "$PROMPT"

Smoke settings:

    256 x 256
    22 frames about 0.92 s
    4 denoise steps
    50 ANE blocks
    ANE rotation enabled
    SSD streaming enabled

This is only a memory and stability check. 256-square is not the target quality.

## 6. Run the published base-M4 style 4-second preset

After the smoke test succeeds:

    PROMPT="$(cat minimax-h3-m4-16gb/shared/example_prompt.txt)"
    zsh minimax-h3-m4-16gb/mac/render_4s.sh ~/MiniMax-H3-M4/conditionings/prompt-XXXXXXXX-XXXXXX.h3cd "$PROMPT"

Preset:

    output:          512 x 512
    internal render: 384 x 384
    duration:        4 seconds
    steps:           6
    ANE blocks:      50
    SSD streaming:   on

The upstream base-M4 24GB report for this general route was about 8.5 minutes
end to end, roughly 370 seconds DiT plus 88 seconds VAE. Do not assume the
16 GB machine will match that number.

## 7. Clean ANE caches when disk usage grows

    zsh minimax-h3-m4-16gb/mac/cleanup_ane_cache.sh

It shows cache sizes first and asks before deleting anything.

Deleting these caches is safe; the models are recompiled next time.

## What not to install on the M4 16GB

Do not copy the RTX workflow directly to the Mac:

- no CUDA SageAttention
- no --use-sage-attention
- no NVFP4-AWQ text encoder path
- no KJNodes Sage patch
- no normal 21 GB DiT full-residency path
- no BF16 51.5 GB text encoder on the Mac

The current official ComfyUI INT8 route can load on MPS but fails when the first
INT8 matmul hits an unsupported MPS operator. CPU fallback is not a practical
solution for this model.

## Later upgrade path

Once the M4 16 GB smoke and full preset are confirmed, change one variable at a
time:

1. 512x512 internal render instead of 384
2. longer 56 or 107 frame requests
3. 8 steps
4. compare ANE vs Metal on the same INT8 checkpoint
5. automate the RTX conditioning service so the Mac can submit a prompt and
   fetch its .h3cd automatically

Do not vary resolution, duration, steps and backend simultaneously when
benchmarking.
