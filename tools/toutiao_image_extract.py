#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone lightweight Toutiao image / gallery extractor.

Intentionally independent from tools/toutiao_video_extract.py:
- no ffmpeg
- no yt-dlp
- no Whisper
- Python standard library only
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

UA_MOBILE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
)

RENDER_RE = re.compile(
    r"""<script[^>]*\bid=["']RENDER_DATA["'][^>]*>(.*?)</script>""",
    re.I | re.S,
)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def fetch(url: str, *, referer: str | None = None) -> tuple[str, bytes, str]:
    headers = {
        "User-Agent": UA_MOBILE,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    with urlopen(req, timeout=40) as resp:
        return resp.geturl(), resp.read(), resp.headers.get("Content-Type", "")


def decode_repeated(value: str, rounds: int = 4) -> str:
    out = html_lib.unescape(value)
    for _ in range(rounds):
        nxt = unquote(out)
        if nxt == out:
            break
        out = nxt
    return out.replace("\\/", "/")


def parse_render_data(page: str) -> Any | None:
    m = RENDER_RE.search(page)
    if not m:
        return None
    raw = html_lib.unescape(m.group(1).strip())
    trials = [raw]
    cur = raw
    for _ in range(4):
        cur = unquote(cur)
        trials.append(cur)
    for value in trials:
        try:
            return json.loads(value)
        except Exception:
            pass
    return None


def deep_values(obj: Any, key: str):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from deep_values(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from deep_values(v, key)


def first_nonempty_list(data: Any, keys: list[str]) -> tuple[str | None, list[Any]]:
    for key in keys:
        for value in deep_values(data, key):
            if isinstance(value, list) and value:
                return key, value
    return None, []


def first_text(data: Any, keys: list[str]) -> str:
    for key in keys:
        for value in deep_values(data, key):
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def get_nested(data: Any, path: list[str]) -> Any:
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def choose_item_url(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    values: list[str] = []
    direct = item.get("url")
    if isinstance(direct, str):
        values.append(direct)
    url_list = item.get("urlList") or item.get("url_list")
    if isinstance(url_list, list):
        for entry in url_list:
            if isinstance(entry, dict) and isinstance(entry.get("url"), str):
                values.append(entry["url"])
            elif isinstance(entry, str):
                values.append(entry)
    for value in values:
        url = decode_repeated(value)
        if url.startswith(("http://", "https://")):
            return url
    return ""


def ext_from_type(content_type: str, url: str) -> str:
    ct = content_type.lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    path = urlparse(url).path.lower()
    for ext in IMAGE_EXTS:
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


def fallback_image_urls(page: str) -> list[str]:
    decoded = decode_repeated(page)
    found = re.findall(r'https?://[^"\\<> ]+', decoded)
    out: list[str] = []
    for url in found:
        url = html_lib.unescape(url).rstrip(");,")
        low = url.lower()
        if "toutiaoimg.com" not in low:
            continue
        if not any(token in low for token in ("tplv-shrink", "/origin/", ".jpeg", ".jpg", ".png", ".webp")):
            continue
        if "400:400" in low or "172:120" in low or "user-avatar" in low:
            continue
        if url not in out:
            out.append(url)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    images_dir = out / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {"input_url": args.url, "errors": []}

    try:
        final_url, body, content_type = fetch(args.url)
    except Exception as e:
        report["errors"].append(f"page fetch failed: {type(e).__name__}: {e}")
        (out / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 2

    report["resolved_url"] = final_url
    report["page_content_type"] = content_type
    page = body.decode("utf-8", errors="ignore")
    (out / "page.html").write_text(page, encoding="utf-8", errors="ignore")

    data = parse_render_data(page)
    report["render_data_found"] = data is not None

    items: list[Any] = []
    source_field: str | None = None
    if data is not None:
        thread_base = get_nested(data, ["articleInfo", "thread", "threadBase"])
        if isinstance(thread_base, dict):
            report["title"] = str(thread_base.get("title") or "")
            report["content"] = str(thread_base.get("content") or "")
            report["gid"] = str(thread_base.get("threadId") or "")
        if not report.get("title"):
            report["title"] = first_text(data, ["shareTitle", "title", "abstract"])

        source_field, items = first_nonempty_list(
            data,
            ["originImageList", "largeImageList", "ugcCutImageList", "thumbImageList"],
        )

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = choose_item_url(item)
        if not url or url in seen:
            continue
        seen.add(url)
        candidates.append({
            "url": url,
            "width": item.get("width") if isinstance(item, dict) else None,
            "height": item.get("height") if isinstance(item, dict) else None,
            "uri": item.get("uri") if isinstance(item, dict) else None,
        })

    if not candidates:
        source_field = "html_fallback"
        for url in fallback_image_urls(page):
            if url not in seen:
                seen.add(url)
                candidates.append({
                    "url": url,
                    "width": None,
                    "height": None,
                    "uri": None,
                })

    report["source_field"] = source_field
    report["candidate_count"] = len(candidates)
    report["images"] = []

    for idx, item in enumerate(candidates, start=1):
        try:
            final_img_url, img_bytes, img_type = fetch(item["url"], referer=final_url)
            if not img_bytes:
                raise ValueError("empty image")
            if "text/html" in img_type.lower():
                raise ValueError(f"unexpected content type: {img_type}")
            ext = ext_from_type(img_type, final_img_url)
            name = f"{idx:02d}{ext}"
            path = images_dir / name
            path.write_bytes(img_bytes)
            report["images"].append({
                "index": idx,
                "filename": f"images/{name}",
                "url": item["url"],
                "final_url": final_img_url,
                "width": item.get("width"),
                "height": item.get("height"),
                "bytes": len(img_bytes),
                "content_type": img_type,
            })
        except Exception as e:
            report["errors"].append(
                f"image {idx} failed: {type(e).__name__}: {e}"
            )

    report["image_count"] = len(report["images"])
    (out / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["image_count"] > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
