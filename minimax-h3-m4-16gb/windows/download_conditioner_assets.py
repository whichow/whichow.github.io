#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download RTX-side assets required to mint h3.c .h3cd prompt conditioning."""
from __future__ import annotations
import argparse
from pathlib import Path
from huggingface_hub import hf_hub_download

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    models = root / "models"
    models.mkdir(parents=True, exist_ok=True)

    print("Downloading the BF16 H3 conditioner (~51.5 GB).")
    te = hf_hub_download(
        repo_id="Comfy-Org/MiniMax-H3",
        filename="text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors",
        local_dir=str(models / "Comfy-Org--MiniMax-H3"),
    )
    tok = hf_hub_download(
        repo_id="MiniMaxAI/MiniMax-H3",
        filename="FL2VA/tokenizer/tokenizer.json",
        local_dir=str(models / "MiniMaxAI--MiniMax-H3"),
    )
    (root / "asset_paths.txt").write_text(
        "TEXT_ENCODER=" + str(Path(te).resolve()) + "\n"
        "TOKENIZER=" + str(Path(tok).resolve()) + "\n",
        encoding="utf-8",
    )
    print("Text encoder:", Path(te).resolve())
    print("Tokenizer:", Path(tok).resolve())
    print("Wrote:", root / "asset_paths.txt")

if __name__ == "__main__":
    main()
