# MiniMax H3 — RTX 5080 16GB 8-step local preset

This folder turns the Toutiao article's acceleration stack into a reproducible RTX 5080 setup, while keeping the current Blackwell/SageAttention caveats explicit.

## What is included

- `workflows/H3_RTX5080_8step_SAFE.json`
  - Based directly on Comfy-Org's official `video_minimax_h3_i2v.json`
  - FL2VA pruned INT8 ConvRot diffusion model
  - Qwen3-VL 32B NVFP4/AWQ text encoder
  - INT8 ConvRot video VAE
  - FP32 audio VAE
  - 8-step LightX2V Turbo LoRA enabled
  - Default benchmark canvas: 16:9, 0.4 MP ≈ 864×480
  - Default duration: 5 seconds
  - No SageAttention patch. Use this first.

- `workflows/H3_RTX5080_8step_SAGE_EXPERIMENTAL.json`
  - Same model stack and settings
  - Adds KJNodes **Patch Sage Attention KJ**
  - Backend: `sageattn_qk_int8_pv_fp16_cuda`
  - `allow_compile = false`
  - The patch is inserted after the turbo model switch and before `BasicScheduler` + `BasicGuider`
  - Intentionally does **not** use KJNodes' `MiniMax H3 Memory Efficient SageAttention Patch`

- `scripts/download_models.py`
  - Downloads the exact model files from `Comfy-Org/MiniMax-H3` into the proper `ComfyUI/models/*` folders.

- `scripts/check_env.py`
  - Prints Python / Torch / CUDA / GPU / compute capability / VRAM.
  - Checks whether SageAttention imports and whether the Blackwell backend symbols are available.
  - Warns about known bad Comfy-Org Sage wheel combinations.

- `scripts/install_sage_blackwell.py`
  - Reads the official Comfy-Org wheel index.
  - Selects a wheel matching the exact Python + Torch + CUDA + OS combination.
  - Refuses known wheel matrix entries that currently omit `sm120`.

- `scripts/install_kjnodes.bat`
  - Installs or updates `kijai/ComfyUI-KJNodes` in the target ComfyUI instance.

- `scripts/launch_h3_1gb.bat`
  - Launches ComfyUI with `--reserve-vram 1`.

## Exact model set

Approximate total download: **42.1 GB**.

| ComfyUI folder | File | Approx. size |
|---|---|---:|
| `models/diffusion_models/` | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 21 GB |
| `models/text_encoders/` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15.7 GB |
| `models/vae/` | `minimax_h3_video_vae_int8_convrot.safetensors` | 2.81 GB |
| `models/vae/` | `minimax_h3_audio_vae_fp32.safetensors` | 605 MB |
| `models/loras/` | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 1.96 GB |

## Recommended execution order on RTX 5080

### 1. Update ComfyUI

Use a recent ComfyUI build that supports MiniMax H3 and the current official H3 workflow/subgraph.

### 2. Install KJNodes

From this repository root:

```bat
minimax-h3-rtx5080\scripts\install_kjnodes.bat D:\AI\ComfyUI
```

### 3. Find the exact Python environment ComfyUI uses

For portable ComfyUI it is usually:

```text
D:\AI\ComfyUI\python_embeded\python.exe
```

For a venv install:

```text
D:\AI\ComfyUI\venv\Scripts\python.exe
```

Every package below must be installed into that exact Python, not system Python.

### 4. Environment check

Portable example:

```bat
D:\AI\ComfyUI\python_embeded\python.exe minimax-h3-rtx5080\scripts\check_env.py
```

On an RTX 5080 the compute capability should report a Blackwell 12.x target.

### 5. Download models

Install the downloader dependency into the same Python if needed:

```bat
D:\AI\ComfyUI\python_embeded\python.exe -m pip install -U huggingface_hub
```

Then:

```bat
D:\AI\ComfyUI\python_embeded\python.exe minimax-h3-rtx5080\scripts\download_models.py --comfy-dir D:\AI\ComfyUI
```

If Hugging Face asks for authentication/license acceptance, run `hf auth login` first.

### 6. First run: SAFE workflow

Start ComfyUI with 1GB reserved:

```bat
minimax-h3-rtx5080\scripts\launch_h3_1gb.bat D:\AI\ComfyUI
```

Load:

```text
workflows/H3_RTX5080_8step_SAFE.json
```

Run the default 864×480 / 5s / 8-step preset first.

This establishes the 5080 baseline without adding SageAttention instability.

### 7. Install SageAttention only after SAFE succeeds

Use the exact same Python:

```bat
D:\AI\ComfyUI\python_embeded\python.exe minimax-h3-rtx5080\scripts\install_sage_blackwell.py
```

Then fully restart ComfyUI and run `check_env.py` again.

### 8. Experimental Sage A/B run

Load:

```text
workflows/H3_RTX5080_8step_SAGE_EXPERIMENTAL.json
```

Keep prompt, seed, input image, resolution and duration identical to the SAFE run.

Compare:

- total wall-clock time
- sampling time
- peak VRAM
- first-run vs second-run time
- output corruption / gray-noise / driver-reset behavior

If Sage crashes, resets the driver, or creates corrupted output, return to SAFE. Do not treat successful import as proof that a Blackwell Sage kernel is stable under H3.

## Why the Sage workflow uses FP16-PV

The article says "Sage Attention", but RTX 50-series Blackwell has had several recent H3-specific reports involving FP8/memory-efficient Sage paths, including driver loss and corrupted output.

For that reason this preset uses the generic KJNodes patch with:

```text
sageattn_qk_int8_pv_fp16_cuda
```

rather than the H3 memory-efficient FP8 path.

This is a deliberate stability-first change for RTX 5080, not a claim that FP16-PV is always the fastest backend.

## How to reproduce the article's four stages

Use the SAFE/SAGE workflows and change one variable at a time.

1. **Base / no Turbo**
   - SAFE workflow
   - set `turbo_mode = false`
   - set normal steps (official template baseline: 20)

2. **8-step Turbo LoRA**
   - SAFE workflow
   - `turbo_mode = true`
   - `turbo_steps = 8`
   - LoRA strength = 1.0

3. **8-step + Sage**
   - SAGE_EXPERIMENTAL workflow
   - same seed/input/resolution/duration

4. **8-step + Sage + 1GB reserve**
   - same Sage workflow
   - start ComfyUI with `--reserve-vram 1`

Do not compare timings from different resolutions, frame counts, seeds, first-run compilation states, or model variants.

## Important current caveats

- The Toutiao article's **66 seconds is a specific test result**, not a guaranteed RTX 5080 time.
- Current ComfyUI officially exposes `--reserve-vram <GB>`; this preset uses `--reserve-vram 1` to reproduce the article's "leave about 1GB free" idea.
- KJNodes' MiniMax H3 memory-efficient Sage path has had open Blackwell `sm120` issues. This repository therefore keeps it out of the 5080 preset.
- Current Comfy-Org SageAttention wheel builds do not all contain `sm120`; the installer refuses known bad Torch/CUDA combinations instead of forcing installation.
- For first troubleshooting, always go back to the SAFE workflow.

## Upstream references

- Comfy-Org/workflow_templates — official MiniMax H3 workflow
- Comfy-Org/MiniMax-H3 — official ComfyUI model repack
- lightx2v/Minimax-h3-Turbo — 8-step Turbo LoRA origin
- kijai/ComfyUI-KJNodes — Patch Sage Attention KJ
- thu-ml/SageAttention — SageAttention 2.2
- Comfy-Org/wheels — prebuilt CUDA wheels
