#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import json
import subprocess
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1"

def download(url: str, dest: Path) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        ctype = r.headers.get("Content-Type", "")
        data = r.read()
    dest.write_bytes(data)
    return len(data), ctype

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--resolver", required=True)
    ap.add_argument("--python", required=True)
    args = ap.parse_args()

    result_path = Path(args.result)
    report = json.loads(result_path.read_text(encoding="utf-8"))
    item_id = str(report.get("item_id") or report.get("resolved_item_id") or "")
    if not item_id:
        raise SystemExit("missing item id")

    report["live_probe_attempted"] = True
    live_dir = result_path.parent / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        [args.python, args.resolver, item_id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    report["live_probe_exit_code"] = proc.returncode
    if proc.stderr.strip():
        report["live_probe_stderr"] = proc.stderr.strip()[-4000:]

    try:
        payload = json.loads(proc.stdout.strip() or "[]")
    except Exception:
        payload = []

    if not isinstance(payload, list):
        payload = []

    # Preserve slide positions. The resolver returns one object per visible slide.
    live_candidates = []
    for x in payload:
        if not isinstance(x, dict):
            continue
        video_url = str(x.get("videoUrl") or "").strip()
        if not video_url:
            continue
        index0 = x.get("index")
        try:
            index = int(index0) + 1
        except Exception:
            index = len(live_candidates) + 1
        live_candidates.append({
            "index": index,
            "video_url": video_url,
            "image_url": x.get("imageUrl") or "",
            "duration": x.get("duration") or 0,
            "video_width": x.get("videoWidth") or 0,
            "video_height": x.get("videoHeight") or 0,
        })

    report["live_candidate_count"] = len(live_candidates)
    report["live_candidates"] = live_candidates
    report["live_downloaded"] = []
    live_errors = []

    for item in live_candidates:
        idx = int(item["index"])
        dest = live_dir / f"{idx:02d}.mp4"
        try:
            n, ctype = download(item["video_url"], dest)
            report["live_downloaded"].append({
                "index": idx,
                "filename": f"live/{dest.name}",
                "bytes": n,
                "content_type": ctype,
                "duration": item["duration"],
                "video_width": item["video_width"],
                "video_height": item["video_height"],
                "source_url": item["video_url"],
            })
        except Exception as e:
            live_errors.append(f"live {idx}: {type(e).__name__}: {e}")

    report["live_downloaded_count"] = len(report["live_downloaded"])
    if live_errors:
        report.setdefault("errors", []).extend(live_errors)

    # Add an easy-to-consume per-image live mapping.
    by_index = {int(x["index"]): x for x in live_candidates}
    for img in report.get("downloaded") or []:
        try:
            idx = int(img.get("index"))
        except Exception:
            continue
        if idx in by_index:
            img["is_live"] = True
            img["live_video"] = next(
                (x for x in report["live_downloaded"] if int(x["index"]) == idx),
                None,
            )
        else:
            img["is_live"] = False

    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "item_id": item_id,
        "live_candidate_count": report["live_candidate_count"],
        "live_downloaded_count": report["live_downloaded_count"],
        "live_probe_exit_code": proc.returncode,
        "errors": live_errors,
    }, ensure_ascii=False, indent=2))

    if report["live_downloaded_count"] != report["live_candidate_count"] or live_errors:
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
