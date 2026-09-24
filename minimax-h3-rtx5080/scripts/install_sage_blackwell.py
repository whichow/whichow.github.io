#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install the exact Comfy-Org SageAttention wheel matching this Python/Torch/CUDA.

Designed for Blackwell. It intentionally refuses known wheel combinations that
currently omit sm120 support instead of installing a wheel that imports but
fails at runtime.
"""
from __future__ import annotations
import html.parser
import os
import platform
import re
import subprocess
import sys
import urllib.request

INDEX = "https://comfy-org.github.io/wheels/sageattention/"

class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

def main():
    try:
        import torch
    except Exception as e:
        raise SystemExit(f"torch import failed: {e}")

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable.")
    cc = torch.cuda.get_device_capability()
    if cc[0] != 12:
        raise SystemExit(f"This helper is for Blackwell sm120-class GPUs; detected capability {cc}.")

    cuda = torch.version.cuda
    if not cuda:
        raise SystemExit("torch.version.cuda is empty.")
    cmaj, cmin = [int(x) for x in cuda.split(".")[:2]]
    if (cmaj, cmin) < (12, 8):
        raise SystemExit("Blackwell SageAttention requires CUDA >= 12.8.")

    tparts = torch.__version__.split("+")[0].split(".")
    tmaj, tmin = int(tparts[0]), int(tparts[1])
    if ((cmaj, cmin) == (12, 8) and (tmaj, tmin) == (2, 10)) or        ((cmaj, cmin) == (13, 0) and (tmaj, tmin) == (2, 10)):
        raise SystemExit(
            "Refusing this wheel combination: the current Comfy-Org wheel matrix "
            "does not compile sm120 for this Torch/CUDA pair. Prefer Torch 2.11."
        )

    cuda_tag = f"cu{cmaj}{cmin}"
    torch_tag = f"torch{tmaj}{tmin}"
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    is_win = os.name == "nt"
    platform_marker = "win_amd64.whl" if is_win else "manylinux"

    print("Looking for:", cuda_tag, torch_tag, py_tag, platform_marker)
    with urllib.request.urlopen(INDEX, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    p = LinkParser()
    p.feed(body)

    candidates = []
    for href in p.links:
        name = href.rsplit("/", 1)[-1]
        if (
            "sageattention-2.2.0+" in name
            and cuda_tag in name
            and torch_tag in name
            and f"-{py_tag}-{py_tag}-" in name
            and platform_marker in name
        ):
            candidates.append(href)

    if not candidates:
        raise SystemExit(
            "No exact Comfy-Org wheel found for this Python/Torch/CUDA combination.\n"
            "Run check_env.py and use a supported wheel matrix or build SageAttention from source."
        )

    url = candidates[0]
    print("Installing:", url)
    cmd = [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", url]
    print(" ".join(cmd))
    subprocess.check_call(cmd)

    print("\nVerifying import...")
    code = (
        "import sageattention; "
        "print('sageattention OK'); "
        "print('fp16_cuda=', hasattr(sageattention,'sageattn_qk_int8_pv_fp16_cuda'))"
    )
    subprocess.check_call([sys.executable, "-c", code])
    print("Done. Fully restart ComfyUI before loading the experimental workflow.")

if __name__ == "__main__":
    main()
