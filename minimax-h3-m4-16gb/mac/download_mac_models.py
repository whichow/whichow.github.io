#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download and arrange the minimal MiniMax H3 files for h3.c-ane on a small Apple Silicon Mac.

The 51.5 GB Qwen3-VL text encoder is intentionally NOT downloaded on the Mac.
Prompt conditioning is supplied as a small .h3cd file minted on the RTX machine.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

ASSETS = [
    # repo, remote path, destination relative to MiniMax-H3
    (
        "Comfy-Org/MiniMax-H3",
        "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "FL2VA/transformer/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    ),
    (
        "Comfy-Org/MiniMax-H3",
        "vae/minimax_h3_video_vae_fp16.safetensors",
        "FL2VA/video_vae/source/minimax_h3_video_vae_fp16.safetensors",
    ),
    (
        "Comfy-Org/MiniMax-H3",
        "vae/minimax_h3_audio_vae_fp32.safetensors",
        "FL2VA/audio_vae/minimax_h3_audio_vae_fp32.safetensors",
    ),
    (
        "MiniMaxAI/MiniMax-H3",
        "FL2VA/transformer/config.json",
        "FL2VA/transformer/config.json",
    ),
    (
        "MiniMaxAI/MiniMax-H3",
        "FL2VA/tokenizer/tokenizer.json",
        "FL2VA/tokenizer/tokenizer.json",
    ),
]

def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink() and dst.resolve() == src.resolve():
            return
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()

    # Prefer a symlink so the ~27 GB model payload isn't duplicated.
    try:
        dst.symlink_to(src)
        return
    except Exception:
        pass

    # Same-volume hardlink is second choice.
    try:
        os.link(src, dst)
        return
    except Exception:
        pass

    shutil.copy2(src, dst)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.home() / "MiniMax-H3-M4"))
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_root = root / "MiniMax-H3"
    cache_root = root / "downloads"
    model_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    print("Root:", root)
    print("Model layout:", model_root)
    print("The Mac download is roughly 27 GB, excluding HF metadata.")
    print("The 51.5 GB BF16 text encoder is deliberately NOT downloaded here.")
    print()

    for idx, (repo_id, filename, rel_dst) in enumerate(ASSETS, 1):
        local_dir = cache_root / repo_id.replace("/", "--")
        print(f"[{idx}/{len(ASSETS)}] {repo_id}:{filename}")
        src = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=str(local_dir),
            )
        ).resolve()
        dst = model_root / rel_dst
        link_or_copy(src, dst)
        print("  source:", src)
        print("  target:", dst)

    print("\nLayout ready.")
    print("Next: build h3.c-ane and run ./h3 --info -d", model_root)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
