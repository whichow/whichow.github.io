#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import re
import urllib.parse
import urllib.request
from pathlib import Path

PIPIXIA_RE = re.compile(r"https?://(?:h5\.)?pipix\.com/[^\s]+", re.I)
UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Mobile Safari/537.36"
)


def extract_url(raw: str) -> str:
    m = PIPIXIA_RE.search(raw or "")
    if not m:
        raise ValueError("No Pipixia URL found")
    return m.group(0).rstrip("，。,.!！?？;；")


def ext_from(content_type: str, url: str, fallback: str) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    table = {
        "video/mp4": ".mp4",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if ct in table:
        return table[ct]
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return fallback


def download(url: str, dest_base: Path, referer: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": referer,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
        final_url = r.geturl()
    if not data:
        raise RuntimeError("empty response")
    ext = ext_from(ctype, final_url, dest_base.suffix or ".bin")
    dest = dest_base.with_suffix(ext)
    dest.write_bytes(data)
    return {
        "filename": dest.as_posix(),
        "bytes": len(data),
        "content_type": ctype,
        "final_url": final_url,
    }


async def main_async(args) -> int:
    from parse_video_py.parser.pipixia import PiPiXia

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)

    report = {
        "input": args.input,
        "upstream": "hiyufan/shizhen@f25a6a7da753e71888a3fec00b8b4a85610f890e",
        "errors": [],
    }

    try:
        share_url = extract_url(args.input)
        report["share_url"] = share_url
        info = await PiPiXia().parse_share_url(share_url)
    except Exception as e:
        report["errors"].append(f"parse: {type(e).__name__}: {e}")
        (out / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    report.update({
        "type": "video" if info.video_url else "image",
        "title": info.title,
        "author": {
            "uid": info.author.uid,
            "name": info.author.name,
            "avatar": info.author.avatar,
        },
        "video_url": info.video_url or "",
        "cover_url": info.cover_url or "",
        "image_count": len(info.images or []),
        "downloads": [],
        "images": [],
    })

    if info.video_url:
        try:
            meta = await asyncio.to_thread(
                download,
                info.video_url,
                out / "video.mp4",
                share_url,
            )
            meta["kind"] = "video"
            report["downloads"].append(meta)
        except Exception as e:
            report["errors"].append(f"video: {type(e).__name__}: {e}")

    for i, img in enumerate(info.images or [], start=1):
        rec = {"index": i, "url": img.url}
        try:
            meta = await asyncio.to_thread(
                download,
                img.url,
                out / "images" / f"{i:02d}.jpg",
                share_url,
            )
            rec["download"] = meta
            report["downloads"].append({"kind": "image", "index": i, **meta})
        except Exception as e:
            report["errors"].append(f"image {i}: {type(e).__name__}: {e}")
        report["images"].append(rec)

    report["video_downloaded"] = any(x.get("kind") == "video" for x in report["downloads"])
    report["downloaded_image_count"] = sum(1 for x in report["images"] if x.get("download"))

    (out / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "type": report["type"],
        "title": report["title"],
        "author": report["author"]["name"],
        "image_count": report["image_count"],
        "downloaded_image_count": report["downloaded_image_count"],
        "video_downloaded": report["video_downloaded"],
        "errors": report["errors"],
    }, ensure_ascii=False, indent=2))

    if report["errors"]:
        return 3
    if report["type"] == "video" and not report["video_downloaded"]:
        return 4
    if report["type"] == "image" and report["downloaded_image_count"] != report["image_count"]:
        return 5
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
