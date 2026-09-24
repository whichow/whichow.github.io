#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download the exact MiniMax H3 files used by the RTX 5080 workflows."""
from __future__ import annotations
import argparse
from pathlib import Path

FILES = [
    "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae/minimax_h3_video_vae_int8_convrot.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
    "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
]
REPO_ID = "Comfy-Org/MiniMax-H3"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comfy-dir", required=True, help="Path to ComfyUI root")
    args = ap.parse_args()
    comfy = Path(args.comfy_dir).expanduser().resolve()
    models = comfy / "models"
    models.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise SystemExit(
            "huggingface_hub is missing. Install it into the same Python used by ComfyUI:\n"
            "  python -m pip install -U huggingface_hub"
        ) from e

    print(f"ComfyUI: {comfy}")
    print(f"Model root: {models}")
    print("Approximate download size: ~42.1 GB")
    print()
    for i, filename in enumerate(FILES, 1):
        print(f"[{i}/{len(FILES)}] {filename}")
        path = hf_hub_download(
            repo_id=REPO_ID,
            filename=filename,
            local_dir=str(models),
        )
        print(f"  -> {path}")
    print("\nDone. The workflow filenames now match the downloaded model paths.")

if __name__ == "__main__":
    main()
