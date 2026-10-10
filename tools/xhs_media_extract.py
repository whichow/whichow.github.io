#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import re
import html as html_lib
from pathlib import Path
from urllib.parse import urlparse, urlunparse

try:
    from curl_cffi import requests as crequests
except Exception:
    crequests = None
import requests

UA_DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36"
)
XHS_HOSTS = ("xiaohongshu.com", "xhslink.com", "xhslink.cn", "rednote.com")
MEDIA_HOSTS = ("xhscdn.com", "xiaohongshu.com")


def session():
    return crequests.Session() if crequests is not None else requests.Session()


def get(sess, url: str, mobile=False, stream=False, referer="https://www.xiaohongshu.com/"):
    headers = {
        "User-Agent": UA_MOBILE if mobile else UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
    }
    kwargs = dict(headers=headers, allow_redirects=True, timeout=40)
    if stream:
        kwargs["stream"] = True
    if crequests is not None and sess.__class__.__module__.startswith("curl_cffi"):
        kwargs["impersonate"] = "chrome"
    return sess.get(url, **kwargs)


def host_ok(url: str, suffixes) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in suffixes)


def resolve(sess, url: str):
    r = get(sess, url, mobile=True, referer="https://www.xiaohongshu.com/")
    chain = []
    for h in list(getattr(r, "history", []) or []) + [r]:
        chain.append({
            "status": getattr(h, "status_code", None),
            "url": str(getattr(h, "url", "")),
            "location": getattr(h, "headers", {}).get("location") if getattr(h, "headers", None) else None,
        })
    return str(r.url), chain, r.text


def extract_note_id(url: str, html: str = "") -> str | None:
    texts = [url, html]
    pats = [
        r"/(?:explore|discovery/item)/([A-Za-z0-9]+)",
        r'"noteId"\s*:\s*"([A-Za-z0-9]+)"',
        r'"note_id"\s*:\s*"([A-Za-z0-9]+)"',
    ]
    for text in texts:
        for pat in pats:
            m = re.search(pat, text or "")
            if m:
                return m.group(1)
    return None


def extract_json_object(text: str, start: int):
    i = text.find("{", start)
    if i < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = text[i:j+1]
                raw = re.sub(r"\bundefined\b", "null", raw)
                try:
                    return json.loads(raw)
                except Exception:
                    return None
    return None


def parse_initial_state(html: str):
    if not html:
        return None
    marker = "window.__INITIAL_STATE__"
    idx = html.find(marker)
    if idx >= 0:
        eq = html.find("=", idx)
        if eq >= 0:
            data = extract_json_object(html, eq + 1)
            if isinstance(data, dict):
                return data
    # Some builds use script blobs without the exact window. prefix.
    for marker in ("__INITIAL_STATE__", "__NEXT_DATA__", "noteDetailMap"):
        idx = html.find(marker)
        if idx >= 0:
            data = extract_json_object(html, idx)
            if isinstance(data, dict):
                return data
    return None


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def pick_note(state, note_id: str):
    if not isinstance(state, dict):
        return None
    note_root = state.get("note") if isinstance(state.get("note"), dict) else {}
    nmap = note_root.get("noteDetailMap") or note_root.get("note_detail_map")
    if isinstance(nmap, dict):
        card = nmap.get(note_id)
        if isinstance(card, dict):
            note = card.get("note") if isinstance(card.get("note"), dict) else card
            if isinstance(note, dict):
                return note
        for card in nmap.values():
            if isinstance(card, dict):
                note = card.get("note") if isinstance(card.get("note"), dict) else card
                if isinstance(note, dict) and str(note.get("noteId") or note.get("note_id") or note.get("id") or "") == note_id:
                    return note
    # Recursive fallback for layout changes.
    best = None
    best_score = -1
    for d in walk(state):
        did = str(d.get("noteId") or d.get("note_id") or d.get("id") or "")
        score = 0
        if did == note_id:
            score += 100
        if "imageList" in d or "image_list" in d:
            score += 20
        if isinstance(d.get("video"), dict):
            score += 20
        if "title" in d or "desc" in d:
            score += 5
        if score > best_score:
            best, best_score = d, score
    return best if best_score >= 20 else None


def media_https(url: str) -> str:
    if not isinstance(url, str):
        return url
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme == "http" and any(host == s or host.endswith("." + s) for s in MEDIA_HOSTS):
        return urlunparse(p._replace(scheme="https"))
    return url


def extract_images(note):
    images = []
    seen = set()
    for img in note.get("imageList") or note.get("image_list") or []:
        if not isinstance(img, dict):
            continue
        candidates = []
        for key in ("urlDefault", "url_default", "urlPre", "url_pre", "url"):
            v = img.get(key)
            if isinstance(v, str) and v.startswith("http"):
                candidates.append(v)
        infos = img.get("infoList") or img.get("info_list") or []
        if isinstance(infos, list):
            for info in reversed(infos):
                if isinstance(info, dict):
                    v = info.get("url")
                    if isinstance(v, str) and v.startswith("http"):
                        candidates.append(v)
        if candidates:
            u = media_https(candidates[0])
            if u not in seen:
                seen.add(u)
                images.append(u)
    return images


def extract_video(note):
    video = note.get("video")
    if not isinstance(video, dict):
        return None, []
    media = video.get("media") if isinstance(video.get("media"), dict) else {}
    stream = media.get("stream") if isinstance(media.get("stream"), dict) else {}
    choices = []
    codec_pref = {"h264": 300, "EF4": 290, "avc": 280, "h265": 200, "EF5": 190, "hevc": 180}
    if isinstance(stream, dict):
        for codec, entries in stream.items():
            if not isinstance(entries, list):
                continue
            for e in entries:
                if not isinstance(e, dict):
                    continue
                urls = []
                for key in ("masterUrl", "master_url", "url"):
                    v = e.get(key)
                    if isinstance(v, str) and v.startswith("http"):
                        urls.append(v)
                backups = e.get("backupUrls") or e.get("backup_urls") or []
                if isinstance(backups, list):
                    urls.extend([v for v in backups if isinstance(v, str) and v.startswith("http")])
                height = e.get("height") or 0
                bitrate = e.get("videoBitrate") or e.get("video_bitrate") or e.get("bitrate") or 0
                try:
                    height = int(height)
                except Exception:
                    height = 0
                try:
                    bitrate = int(bitrate)
                except Exception:
                    bitrate = 0
                for u in urls:
                    score = codec_pref.get(str(codec), 100) * 10**9 + height * 10**6 + bitrate
                    choices.append((score, str(codec), height, bitrate, media_https(u)))
    choices.sort(reverse=True)
    if choices:
        return choices[0][4], [
            {"codec": c, "height": h, "bitrate": b, "url": u}
            for _, c, h, b, u in choices[:20]
        ]
    consumer = video.get("consumer") if isinstance(video.get("consumer"), dict) else {}
    origin = consumer.get("originVideoKey") or consumer.get("origin_video_key")
    if origin:
        return "https://sns-video-bd.xhscdn.com/" + str(origin), []
    return None, []


def title_from_html(html: str):
    for pat in [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r"<title>(.*?)</title>",
    ]:
        m = re.search(pat, html or "", re.I | re.S)
        if m:
            return html_lib.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    return ""


def download(sess, url: str, dest: Path):
    if not host_ok(url, MEDIA_HOSTS):
        raise ValueError("unexpected media host: " + (urlparse(url).hostname or ""))
    r = get(sess, media_https(url), stream=True, referer="https://www.xiaohongshu.com/")
    r.raise_for_status()
    total = 0
    with dest.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)
                total += len(chunk)
    return {
        "status": r.status_code,
        "content_type": r.headers.get("content-type", ""),
        "content_length": r.headers.get("content-length", ""),
        "bytes": total,
        "final_url": str(r.url),
        "path": str(dest),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sess = session()
    report = {"input_url": args.url, "errors": []}

    try:
        final_url, chain, short_html = resolve(sess, args.url)
        report["resolved_url"] = final_url
        report["redirect_chain"] = chain
        (out / "shortlink_response.html").write_text(short_html, encoding="utf-8", errors="ignore")
    except Exception as e:
        report["errors"].append(f"resolve failed: {type(e).__name__}: {e}")
        final_url, short_html = args.url, ""

    note_id = extract_note_id(final_url, short_html)
    report["note_id"] = note_id
    if not note_id:
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    pages = [("shortlink_response.html", short_html)] if short_html else []
    for mobile in (False, True):
        try:
            r = get(sess, final_url, mobile=mobile)
            name = "page_mobile.html" if mobile else "page_desktop.html"
            (out / name).write_text(r.text, encoding="utf-8", errors="ignore")
            pages.append((name, r.text))
            report.setdefault("fetches", []).append({
                "name": name, "status": r.status_code, "final_url": str(r.url), "bytes": len(r.content)
            })
        except Exception as e:
            report["errors"].append(f"page fetch mobile={mobile} failed: {type(e).__name__}: {e}")

    note = None
    source = None
    for name, page in pages:
        state = parse_initial_state(page)
        if isinstance(state, dict):
            (out / f"{name}.initial_state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            cand = pick_note(state, note_id)
            if isinstance(cand, dict):
                note, source = cand, name
                break

    if not note:
        report["title"] = next((title_from_html(p) for _, p in pages if title_from_html(p)), "")
        report["errors"].append("note data not found in public INITIAL_STATE")
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 3

    report["source"] = source
    report["title"] = str(note.get("title") or "").strip() or str(note.get("desc") or "").strip()[:120]
    report["desc"] = str(note.get("desc") or "").strip()
    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    report["author"] = {
        "user_id": user.get("userId") or user.get("user_id"),
        "nickname": user.get("nickname") or user.get("nickName"),
    }
    report["type"] = note.get("type")
    images = extract_images(note)
    video_url, video_candidates = extract_video(note)
    report["images"] = images
    report["video_url"] = video_url
    report["video_candidates"] = video_candidates
    (out / "note.json").write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")

    downloads = []
    for i, url in enumerate(images, 1):
        try:
            dl = download(sess, url, out / f"image_{i:02d}.jpg")
            downloads.append({"kind": "image", "index": i, **dl})
        except Exception as e:
            report["errors"].append(f"image {i} download failed: {type(e).__name__}: {e}")
    if video_url:
        try:
            dl = download(sess, video_url, out / "video.mp4")
            downloads.append({"kind": "video", **dl})
        except Exception as e:
            report["errors"].append(f"video download failed: {type(e).__name__}: {e}")

    report["downloads"] = downloads
    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if (images or video_url) and downloads else 4


if __name__ == "__main__":
    raise SystemExit(main())
