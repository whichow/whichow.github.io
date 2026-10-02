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

XHS_URL_RE = re.compile(
    r"https?://(?:(?:www\.)?xiaohongshu\.com|(?:www\.)?xhslink\.(?:com|cn))/[^\s]+",
    re.I,
)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def extract_url(raw: str) -> str:
    m = XHS_URL_RE.search(raw or "")
    if not m:
        raise ValueError("No Xiaohongshu URL found")
    return m.group(0).rstrip("，。,.!！?？;；")


def ext_from(content_type: str, url: str, fallback: str) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    table = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
    }
    if ct in table:
        return table[ct]

    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return fallback


def download(url: str, dest_base: Path, referer: str) -> dict:
    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": referer,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
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
    from parse_video_py.parser.redbook import RedBook

    raw = args.input
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    (out / "live").mkdir(exist_ok=True)

    report = {
        "input": raw,
        "errors": [],
        "upstream": "hiyufan/shizhen@f25a6a7da753e71888a3fec00b8b4a85610f890e",
    }

    try:
        url = extract_url(raw)
        report["share_url"] = url
        info = await RedBook().parse_share_url(url)
    except Exception as e:
        report["errors"].append(f"parse: {type(e).__name__}: {e}")
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    report.update({
        "title": info.title,
        "author": {
            "uid": info.author.uid,
            "name": info.author.name,
            "avatar": info.author.avatar,
        },
        "duration": info.duration,
        "width": info.width,
        "height": info.height,
        "cover_url": info.cover_url,
        "type": "video" if info.video_url else "image",
        "video_url": info.video_url or "",
        "image_count": len(info.images or []),
        "live_photo_count": sum(1 for x in (info.images or []) if x.live_photo_url),
        "formats": [
            {
                "label": f.label,
                "height": f.height,
                "filesize": f.filesize,
                "codec": f.codec,
                "url": f.url,
            }
            for f in (info.formats or [])
        ],
        "downloads": [],
        "images": [],
        "live_photos": [],
    })

    if info.video_url:
        try:
            meta = await asyncio.to_thread(
                download,
                info.video_url,
                out / "video.mp4",
                url,
            )
            meta["kind"] = "video"
            report["downloads"].append(meta)
        except Exception as e:
            report["errors"].append(f"video: {type(e).__name__}: {e}")

    for i, img in enumerate(info.images or [], start=1):
        image_rec = {
            "index": i,
            "url": img.url,
            "live_photo_url": img.live_photo_url or "",
        }
        try:
            meta = await asyncio.to_thread(
                download,
                img.url,
                out / "images" / f"{i:02d}.jpg",
                url,
            )
            image_rec["download"] = meta
            report["downloads"].append({"kind": "image", "index": i, **meta})
        except Exception as e:
            report["errors"].append(f"image {i}: {type(e).__name__}: {e}")
        report["images"].append(image_rec)

        if img.live_photo_url:
            live_rec = {
                "index": i,
                "url": img.live_photo_url,
            }
            try:
                meta = await asyncio.to_thread(
                    download,
                    img.live_photo_url,
                    out / "live" / f"{i:02d}.mp4",
                    url,
                )
                live_rec["download"] = meta
                report["downloads"].append({"kind": "live", "index": i, **meta})
            except Exception as e:
                report["errors"].append(f"live {i}: {type(e).__name__}: {e}")
            report["live_photos"].append(live_rec)

    report["downloaded_image_count"] = sum(1 for x in report["images"] if x.get("download"))
    report["downloaded_live_count"] = sum(1 for x in report["live_photos"] if x.get("download"))
    report["video_downloaded"] = any(x.get("kind") == "video" for x in report["downloads"])

    (out / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "type": report["type"],
        "title": report["title"],
        "author": report["author"]["name"],
        "image_count": report["image_count"],
        "live_photo_count": report["live_photo_count"],
        "downloaded_image_count": report["downloaded_image_count"],
        "downloaded_live_count": report["downloaded_live_count"],
        "video_downloaded": report["video_downloaded"],
        "errors": report["errors"],
    }, ensure_ascii=False, indent=2))

    if report["errors"]:
        return 3
    if report["type"] == "video" and not report["video_downloaded"]:
        return 4
    if report["type"] == "image" and report["downloaded_image_count"] != report["image_count"]:
        return 5
    if report["downloaded_live_count"] != report["live_photo_count"]:
        return 6
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
