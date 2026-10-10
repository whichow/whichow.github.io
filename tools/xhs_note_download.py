#!/usr/bin/env python3
import json, os, sys, mimetypes, requests
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "output")
note_path = out / "note.json"
raw = note_path.read_text(encoding="utf-8").strip()

def parse_note(s):
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v[0] if v else {}
        return v
    except Exception:
        for line in s.splitlines():
            line=line.strip()
            if not line: continue
            try:
                v=json.loads(line)
                if isinstance(v, dict): return v
            except Exception:
                pass
    return {}

note = parse_note(raw)
(out/"note.pretty.json").write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
title = note.get("title") or ""
desc = note.get("desc") or ""
nickname = note.get("nickname") or ""
tags = note.get("tags") or []
(out/"content.txt").write_text(
    f"标题：{title}\n作者：{nickname}\n标签：{' '.join('#'+str(x) for x in tags)}\n\n{desc}\n",
    encoding="utf-8"
)

session = requests.Session()
headers = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
    "Referer":"https://www.xiaohongshu.com/",
    "Accept":"*/*",
}

report = {"note_id": note.get("note_id"), "type": note.get("type"), "downloaded":[]}
media_dir = out/"media"
media_dir.mkdir(exist_ok=True)

def save_url(url, stem):
    r = session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True)
    r.raise_for_status()
    ct = (r.headers.get("content-type") or "").split(";")[0].lower()
    ext = mimetypes.guess_extension(ct) or ".bin"
    if ct == "image/jpeg": ext = ".jpg"
    elif ct == "image/webp": ext = ".webp"
    elif ct in ("video/mp4","application/mp4"): ext = ".mp4"
    path = media_dir / f"{stem}{ext}"
    total=0
    with path.open("wb") as f:
        for chunk in r.iter_content(1024*1024):
            if chunk:
                f.write(chunk); total += len(chunk)
    report["downloaded"].append({"url":url,"path":str(path.relative_to(out)),"bytes":total,"content_type":ct})
    return path, total

video = note.get("video") or {}
masters = video.get("masters") or []
if masters:
    best = None
    for i,u in enumerate(masters[:8],1):
        try:
            p,n = save_url(u, f"video_{i}")
            if n > 100000:
                best = p
                break
        except Exception as e:
            report.setdefault("errors",[]).append(f"video {i}: {type(e).__name__}: {e}")
    if best:
        target = out/"video.mp4"
        if best.suffix.lower()==".mp4":
            target.write_bytes(best.read_bytes())

images = note.get("images") or []
for i,img in enumerate(images,1):
    u = img.get("url")
    if u:
        try: save_url(u, f"image_{i:02d}")
        except Exception as e: report.setdefault("errors",[]).append(f"image {i}: {type(e).__name__}: {e}")
    su = img.get("stream_url")
    if su:
        try: save_url(su, f"live_{i:02d}")
        except Exception as e: report.setdefault("errors",[]).append(f"live {i}: {type(e).__name__}: {e}")

(out/"result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
