#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Toutiao public video extractor for one-off research/personal use.

Flow:
1) Resolve m.toutiao.com short links.
2) Fetch /video/{id}/ page with browser-like HTTP.
3) Parse RENDER_DATA and scan nested play info for direct/base64 media URLs.
4) Download the best discovered video.
5) Emit metadata + raw page artifacts for reproducibility.
"""
from __future__ import annotations

import argparse
import base64
import html as html_lib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

try:
    from curl_cffi import requests as crequests
except Exception:
    crequests = None

import requests

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
)

VIDEO_ID_RE = re.compile(r"/video/(\d+)")
RENDER_RE = re.compile(
    r'<script[^>]*\bid=["\']RENDER_DATA["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
MEDIA_EXT_RE = re.compile(r"\.(?:mp4|m3u8|mov|webm)(?:\?|$)", re.I)


def mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def get_session():
    if crequests is not None:
        return crequests.Session()
    return requests.Session()


def get(session, url: str, *, referer: str | None = None, mobile: bool = False, stream: bool = False):
    headers = {
        "User-Agent": UA_MOBILE if mobile else UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    if referer:
        headers["Referer"] = referer
    kwargs = dict(headers=headers, allow_redirects=True, timeout=40)
    if stream:
        kwargs["stream"] = True
    if crequests is not None and session.__class__.__module__.startswith("curl_cffi"):
        kwargs["impersonate"] = "chrome"
    return session.get(url, **kwargs)


def resolve_url(session, url: str) -> tuple[str, list[dict[str, Any]], str]:
    r = get(session, url, mobile=True)
    chain = []
    for h in list(getattr(r, "history", []) or []) + [r]:
        chain.append({
            "status": getattr(h, "status_code", None),
            "url": str(getattr(h, "url", "")),
            "location": getattr(h, "headers", {}).get("location") if getattr(h, "headers", None) else None,
        })
    return str(r.url), chain, r.text


def extract_video_id(*texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        m = VIDEO_ID_RE.search(text)
        if m:
            return m.group(1)
    for text in texts:
        if not text:
            continue
        m = re.search(r"\b(7\d{18})\b", text)
        if m:
            return m.group(1)
    return None


def parse_render_data(page: str) -> Any | None:
    m = RENDER_RE.search(page)
    if not m:
        return None
    raw = html_lib.unescape(m.group(1).strip())
    trials = [raw, unquote(raw)]
    for t in trials:
        try:
            return json.loads(t)
        except Exception:
            pass
    return None


def maybe_json(value: str) -> Any | None:
    s = value.strip()
    if len(s) < 2:
        return None
    candidates = [s, html_lib.unescape(s), unquote(s)]
    for c in candidates:
        if c[:1] in "[{":
            try:
                return json.loads(c)
            except Exception:
                pass
    return None


def maybe_base64_url(value: str) -> str | None:
    s = value.strip().replace("\\/", "/")
    if s.startswith(("http://", "https://")):
        return s
    if len(s) < 24:
        return None
    # Toutiao commonly returns base64 main_url / backup_url values.
    if re.fullmatch(r"[A-Za-z0-9+/=_-]+", s) is None:
        return None
    try:
        pad = "=" * ((4 - len(s) % 4) % 4)
        raw = base64.b64decode((s + pad).replace("-", "+").replace("_", "/"), validate=False)
        decoded = raw.decode("utf-8", errors="ignore").strip()
        if decoded.startswith(("http://", "https://")):
            return decoded
    except Exception:
        return None
    return None


def walk(obj: Any, path: tuple[str, ...] = ()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (str(i),))
    else:
        yield path, obj
        if isinstance(obj, str):
            nested = maybe_json(obj)
            if nested is not None:
                yield from walk(nested, path + ("<json>",))



def fetch_vod_play_info(session, data: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Use Toutiao's own playAuthTokenV2 to request the signed VOD play list."""
    if not isinstance(data, dict):
        return None, None
    article = data.get("articleInfo")
    if not isinstance(article, dict):
        return None, None
    token_b64 = article.get("playAuthTokenV2")
    if not isinstance(token_b64, str) or not token_b64:
        return None, None

    try:
        pad = "=" * ((4 - len(token_b64) % 4) % 4)
        auth = json.loads(base64.b64decode(token_b64 + pad).decode("utf-8"))
        query = auth["GetPlayInfoToken"]
        endpoint = "https://vod.bytedanceapi.com/?" + query + "&ssl=true"
        headers = {
            "User-Agent": UA_DESKTOP,
            "Referer": "https://www.toutiao.com/",
            "Accept": "application/json,text/plain,*/*",
        }
        kwargs = dict(headers=headers, timeout=40, allow_redirects=True)
        if crequests is not None and session.__class__.__module__.startswith("curl_cffi"):
            kwargs["impersonate"] = "chrome"
        r = session.get(endpoint, **kwargs)
        r.raise_for_status()
        return r.json(), endpoint
    except Exception:
        return None, None


def extract_vod_media(play_info: Any) -> list[dict[str, str]]:
    """Extract real VOD media URLs from Result.Data.PlayInfoList."""
    out: list[dict[str, str]] = []
    if not isinstance(play_info, dict):
        return out

    node = play_info
    for key in ("Result", "Data"):
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            node = None
            break

    items = node.get("PlayInfoList") if isinstance(node, dict) else None
    if not isinstance(items, list):
        # Fallback recursive search for PlayInfoList if response shape changes.
        stack = [play_info]
        while stack and items is None:
            cur = stack.pop()
            if isinstance(cur, dict):
                if isinstance(cur.get("PlayInfoList"), list):
                    items = cur["PlayInfoList"]
                    break
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)

    if not isinstance(items, list):
        return out

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        definition = str(item.get("Definition") or "")
        fmt = str(item.get("Format") or "")
        for field in ("MainPlayUrl", "BackupPlayUrl"):
            raw = item.get(field)
            if not isinstance(raw, str) or not raw:
                continue
            url = maybe_base64_url(raw) or raw.replace("\\/", "/")
            if url.startswith(("http://", "https://")):
                out.append({
                    "path": f"vod.PlayInfoList.{idx}.{field}.{definition}.{fmt}",
                    "url": url,
                })

    def qscore(entry: dict[str, str]) -> int:
        s = (entry["path"] + " " + entry["url"]).lower()
        score = 0
        if "1080" in s:
            score += 50
        elif "720" in s:
            score += 40
        elif "540" in s:
            score += 30
        elif "480" in s:
            score += 20
        elif "360" in s:
            score += 10
        if "mainplayurl" in s:
            score += 5
        if "mp4" in s:
            score += 3
        return score

    out.sort(key=qscore, reverse=True)
    return out

def collect(data: Any, page: str) -> dict[str, Any]:
    media: list[dict[str, str]] = []
    titles: list[tuple[str, str]] = []
    authors: list[tuple[str, str]] = []
    seen: set[str] = set()

    if data is not None:
        for path, value in walk(data):
            key = path[-1].lower() if path else ""
            pstr = ".".join(path)
            if isinstance(value, str):
                if key in {"title", "abstract", "description", "content"} and 2 <= len(value.strip()) <= 500:
                    titles.append((pstr, value.strip()))
                if key in {"name", "author", "author_name", "nickname"} and 1 <= len(value.strip()) <= 100:
                    authors.append((pstr, value.strip()))
                u = maybe_base64_url(value)
                if u and u not in seen:
                    low_path = pstr.lower()
                    if (
                        MEDIA_EXT_RE.search(u)
                        or "mainplayurl" in low_path
                        or "backupplayurl" in low_path
                        or "main_url" in low_path
                        or "backup_url" in low_path
                        or "playurllist" in low_path
                        or "video_list" in low_path
                    ):
                        seen.add(u)
                        media.append({"path": pstr, "url": u})

    # Fallback: direct/base64 main_url fields in the HTML itself.
    for m in re.finditer(r'"(?:main_url|backup_url_\d+)"\s*:\s*"([^"]+)"', page, re.I):
        raw = m.group(1).replace("\\u002F", "/").replace("\\/", "/")
        try:
            raw = json.loads('"' + m.group(1) + '"')
        except Exception:
            pass
        u = maybe_base64_url(raw)
        if u and u not in seen:
            seen.add(u)
            media.append({"path": "<html-regex>.main_url", "url": u})

    def score(item: dict[str, str]) -> int:
        p = (item["path"] + " " + item["url"]).lower()
        s = 0
        if "main_url" in p:
            s += 50
        if "video_3" in p or "1080" in p or "origin" in p:
            s += 20
        if ".mp4" in p:
            s += 10
        if "backup" in p:
            s -= 2
        return s

    media.sort(key=score, reverse=True)

    # Prefer paths that are specifically inside initialVideo for title/author.
    def text_score(pair: tuple[str, str]) -> int:
        p, v = pair
        pl = p.lower()
        score = 0
        if "initialvideo" in pl:
            score += 30
        if p.lower().endswith(".title"):
            score += 15
        if "itemcell" in pl:
            score += 5
        score += min(len(v), 120) // 20
        return score

    titles.sort(key=text_score, reverse=True)
    authors.sort(key=text_score, reverse=True)

    return {
        "title_candidates": [{"path": p, "value": v} for p, v in titles[:20]],
        "author_candidates": [{"path": p, "value": v} for p, v in authors[:20]],
        "media_candidates": media[:100],
    }


def download_media(session, url: str, dest: Path) -> dict[str, Any]:
    headers = {
        "User-Agent": UA_DESKTOP,
        "Referer": "https://www.toutiao.com/",
        "Accept": "*/*",
    }
    if ".m3u8" in url.lower():
        cmd = ["ffmpeg", "-y", "-headers", f"Referer: https://www.toutiao.com/\r\nUser-Agent: {UA_DESKTOP}\r\n", "-i", url, "-c", "copy", str(dest)]
        cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return {"method": "ffmpeg", "returncode": cp.returncode, "log_tail": cp.stdout[-5000:], "path": str(dest) if dest.exists() else ""}
    kwargs = dict(headers=headers, timeout=60, allow_redirects=True, stream=True)
    if crequests is not None and session.__class__.__module__.startswith("curl_cffi"):
        kwargs["impersonate"] = "chrome"
    r = session.get(url, **kwargs)
    r.raise_for_status()
    content_type = (r.headers.get("content-type", "") or "").lower()
    if content_type.startswith("image/") or content_type.startswith("text/html"):
        raise ValueError(f"not a video response: content-type={content_type}")
    total = 0
    with dest.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                total += len(chunk)
    return {
        "method": "http",
        "status": r.status_code,
        "content_type": content_type,
        "content_length": r.headers.get("content-length", ""),
        "bytes": total,
        "final_url": str(r.url),
        "path": str(dest),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    mkdir(out)
    session = get_session()

    report: dict[str, Any] = {"input_url": args.url, "errors": []}

    try:
        final_url, chain, short_html = resolve_url(session, args.url)
        report["resolved_url"] = final_url
        report["redirect_chain"] = chain
        (out / "shortlink_response.html").write_text(short_html, encoding="utf-8", errors="ignore")
    except Exception as e:
        report["errors"].append(f"shortlink resolve failed: {type(e).__name__}: {e}")
        final_url, short_html = args.url, ""

    vid = extract_video_id(final_url, short_html, args.url)
    report["video_id"] = vid
    if not vid:
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    page_url = f"https://www.toutiao.com/video/{vid}/"
    report["canonical_video_url"] = page_url

    pages: list[tuple[str, str]] = []
    for mobile in (False, True):
        try:
            r = get(session, page_url, referer="https://www.toutiao.com/", mobile=mobile)
            name = "page_mobile.html" if mobile else "page_desktop.html"
            (out / name).write_text(r.text, encoding="utf-8", errors="ignore")
            pages.append((name, r.text))
            report.setdefault("fetches", []).append({
                "name": name,
                "status": r.status_code,
                "final_url": str(r.url),
                "bytes": len(r.content),
            })
        except Exception as e:
            report["errors"].append(f"page fetch mobile={mobile} failed: {type(e).__name__}: {e}")

    best_collection = None
    render_found = False
    for name, page in pages:
        data = parse_render_data(page)
        if data is not None:
            render_found = True
            (out / f"{name}.render_data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        collection = collect(data, page)
        play_info, play_info_endpoint = fetch_vod_play_info(session, data)
        if play_info is not None:
            safe_name = name.replace(".html", "")
            (out / f"{safe_name}.vod_play_info.json").write_text(
                json.dumps(play_info, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            vod_media = extract_vod_media(play_info)
            collection["media_candidates"] = vod_media + collection["media_candidates"]
            report.setdefault("vod_play_info", []).append({
                "source": name,
                "endpoint": play_info_endpoint,
                "media_count": len(vod_media),
            })
        if best_collection is None or len(collection["media_candidates"]) > len(best_collection["media_candidates"]):
            best_collection = collection

    report["render_data_found"] = render_found
    report.update(best_collection or {
        "title_candidates": [], "author_candidates": [], "media_candidates": []
    })

    # Save an easy-to-read metadata text summary.
    if report["title_candidates"]:
        report["title"] = report["title_candidates"][0]["value"]
    if report["author_candidates"]:
        report["author"] = report["author_candidates"][0]["value"]

    video_path = out / "video.mp4"
    if report["media_candidates"]:
        for idx, item in enumerate(report["media_candidates"][:8]):
            try:
                dl = download_media(session, item["url"], video_path)
                report["selected_media"] = item
                report["download"] = dl
                if video_path.exists() and video_path.stat().st_size > 1024 * 100:
                    break
                if video_path.exists():
                    video_path.unlink(missing_ok=True)
            except Exception as e:
                report["errors"].append(f"download candidate {idx} failed: {type(e).__name__}: {e}")
                try:
                    video_path.unlink(missing_ok=True)
                except Exception:
                    pass

    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if video_path.exists() else 3


if __name__ == "__main__":
    raise SystemExit(main())
