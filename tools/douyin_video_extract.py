#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone Douyin single-video extractor.
Keeps all Toutiao extractors untouched.

Strategy:
1) Resolve via public parser APIs (BugPk first; fallbacks optional).
2) Download the returned original video URL.
3) Emit result.json + video.mp4.
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.parse, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"

PARSERS = [
    ("bugpk", "https://api.bugpk.com/api/douyin?url={url}"),
    ("xinyew", "https://api.xinyew.cn/api/douyinjx?url={url}"),
    ("jxcxin", "https://apis.jxcxin.cn/api/douyin?url={url}"),
]

def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8", errors="strict"))

def parse_payload(name: str, obj: dict) -> dict | None:
    if not isinstance(obj, dict):
        return None
    data = obj.get("data")
    if name == "bugpk" and obj.get("code") == 200 and isinstance(data, dict):
        u = data.get("url")
        if u:
            return {
                "parser": name,
                "title": data.get("title") or data.get("desc") or "",
                "author": (data.get("author") or {}).get("name") if isinstance(data.get("author"), dict) else "",
                "video_url": u,
                "cover": data.get("cover") or "",
                "width": data.get("width"),
                "height": data.get("height"),
                "duration": data.get("duration"),
                "aweme_id": ((data.get("extra") or {}).get("aweme_id") if isinstance(data.get("extra"), dict) else None),
                "size_hint": data.get("size"),
            }
    if obj.get("code") == 200 and isinstance(data, dict):
        u = data.get("video") or data.get("video_url") or data.get("play_url") or data.get("url")
        if u:
            return {
                "parser": name,
                "title": data.get("title") or "",
                "author": data.get("author") if isinstance(data.get("author"), str) else "",
                "video_url": u,
                "cover": data.get("cover") or "",
                "width": data.get("width"),
                "height": data.get("height"),
                "duration": data.get("duration"),
                "aweme_id": data.get("aweme_id"),
            }
    if isinstance(obj.get("url"), str) and obj.get("url"):
        return {
            "parser": name,
            "title": obj.get("title") or "",
            "author": obj.get("author") or "",
            "video_url": obj["url"],
            "cover": obj.get("cover") or obj.get("img") or "",
            "width": obj.get("width"),
            "height": obj.get("height"),
            "duration": obj.get("duration"),
            "aweme_id": obj.get("aweme_id"),
        }
    return None

def download(url: str, dest: Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        total = 0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return total

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"input_url": args.url, "errors": []}

    parsed = None
    encoded = urllib.parse.quote(args.url, safe="")
    for name, template in PARSERS:
        try:
            obj = get_json(template.format(url=encoded))
            candidate = parse_payload(name, obj)
            if candidate:
                parsed = candidate
                break
            report["errors"].append(f"{name}: parser returned no usable video")
        except Exception as e:
            report["errors"].append(f"{name}: {type(e).__name__}: {e}")

    if not parsed:
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    report.update({k: v for k, v in parsed.items() if k != "video_url"})
    report["video_url_found"] = True
    try:
        n = download(parsed["video_url"], out / "video.mp4")
        report["bytes"] = n
    except Exception as e:
        report["errors"].append(f"download: {type(e).__name__}: {e}")
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 3

    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
