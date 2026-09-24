#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Environment check for MiniMax H3 on RTX 5080 / Blackwell."""
from __future__ import annotations
import platform
import sys

def main():
    print("=== MiniMax H3 RTX 5080 environment check ===")
    print("Python:", sys.version.split()[0])
    print("OS:", platform.platform())

    try:
        import torch
    except Exception as e:
        print("ERROR: torch import failed:", e)
        return 2

    print("Torch:", torch.__version__)
    print("Torch CUDA runtime:", torch.version.cuda)
    if not torch.cuda.is_available():
        print("ERROR: CUDA is not available in this Python environment.")
        return 2

    idx = torch.cuda.current_device()
    name = torch.cuda.get_device_name(idx)
    cc = torch.cuda.get_device_capability(idx)
    total = torch.cuda.get_device_properties(idx).total_memory / (1024**3)
    print("GPU:", name)
    print("Compute capability:", f"{cc[0]}.{cc[1]}")
    print("VRAM:", f"{total:.2f} GB")

    cuda = torch.version.cuda or "0.0"
    try:
        cuda_tuple = tuple(int(x) for x in cuda.split(".")[:2])
    except Exception:
        cuda_tuple = (0, 0)

    if cc[0] == 12:
        if cuda_tuple < (12, 8):
            print("ERROR: Blackwell SageAttention 2.2 requires CUDA >= 12.8.")
        else:
            print("OK: CUDA runtime is new enough for Blackwell SageAttention 2.2.")
    else:
        print("WARNING: This preset was built for Blackwell sm_120-class GPUs.")

    # Comfy-Org wheel matrix currently has a known sm120 gap for these exact builds.
    tv = torch.__version__.split("+")[0].split(".")
    torch_mm = tuple(int(x) for x in tv[:2])
    if cc[0] == 12 and ((cuda_tuple == (12, 8) and torch_mm == (2, 10)) or
                        (cuda_tuple == (13, 0) and torch_mm == (2, 10))):
        print("BLOCK: Comfy-Org SageAttention wheel for this Torch/CUDA combo is known to omit sm120.")
        print("Use Torch 2.11 with cu128/cu130, or another matrix entry that includes arch 12.0.")

    try:
        import sageattention
        print("SageAttention import: OK")
        funcs = [
            "sageattn",
            "sageattn_qk_int8_pv_fp16_cuda",
            "sageattn_qk_int8_pv_fp8_cuda",
        ]
        for fn in funcs:
            print(f"  {fn}:", "yes" if hasattr(sageattention, fn) else "no")
    except Exception as e:
        print("SageAttention import: NOT AVAILABLE")
        print("  ", repr(e))

    print("\nRecommendation for the experimental workflow:")
    print("  Patch Sage Attention KJ -> sageattn_qk_int8_pv_fp16_cuda")
    print("  allow_compile = false")
    print("  Do NOT use MiniMax H3 Memory Efficient SageAttention Patch on RTX 5080 yet.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
