#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Douyin public video extractor for personal research.

Flow:
1) Resolve v.douyin.com short links -> aweme_id.
2) Fetch iesdouyin mobile share pages.
3) Parse _ROUTER_DATA / RENDER_DATA.
4) Extract play_addr / bit_rate video candidates and download the best.
5) Save metadata and raw pages for reproducibility.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import unquote

try:
    from curl_cffi import requests as crequests
except Exception:
    crequests = None

import requests

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

ID_PATTERNS = [
    re.compile(r"/(?:video|note|slides)/(\d+)"),
    re.compile(r"/share/(?:video|note|slides)/(\d+)"),
    re.compile(r"[?&](?:modal_id|aweme_id|item_ids)=(\d+)"),
]
RENDER_RE = re.compile(
    r'<script[^>]*\bid=["\']RENDER_DATA["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def session_new():
    return crequests.Session() if crequests is not None else requests.Session()


def http_get(session, url: str, *, mobile: bool = True, referer: str | None = None, stream: bool = False):
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


def extract_id(text: str) -> str | None:
    for pat in ID_PATTERNS:
        m = pat.search(text or "")
        if m:
            return m.group(1)
    m = re.search(r"\b(7\d{18})\b", text or "")
    return m.group(1) if m else None


def resolve(session, url: str) -> tuple[str, str | None, list[dict[str, Any]], str]:
    r = http_get(session, url, mobile=True)
    chain = []
    for h in list(getattr(r, "history", []) or []) + [r]:
        chain.append({
            "status": getattr(h, "status_code", None),
            "url": str(getattr(h, "url", "")),
            "location": getattr(h, "headers", {}).get("location") if getattr(h, "headers", None) else None,
        })
    final_url = str(r.url)
    return final_url, extract_id(final_url) or extract_id(r.text) or extract_id(url), chain, r.text


def scan_balanced(text: str, start: int, open_ch: str, close_ch: str) -> str | None:
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def parse_router_data(page: str) -> Any | None:
    idx = page.find("_ROUTER_DATA")
    if idx < 0:
        return None
    eq = page.find("=", idx)
    if eq < 0:
        return None
    pos = eq + 1
    while pos < len(page) and page[pos] in " \t\r\n":
        pos += 1
    if pos >= len(page):
        return None
    if page[pos] == "{":
        raw = scan_balanced(page, pos, "{", "}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
    return None


def parse_render_data(page: str) -> Any | None:
    m = RENDER_RE.search(page)
    if not m:
        return None
    raw = html_lib.unescape(m.group(1).strip())
    for candidate in (raw, unquote(raw)):
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None


def walk(obj: Any, path: tuple[str, ...] = ()):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (str(i),))


def find_item(data: Any, aweme_id: str | None) -> dict[str, Any] | None:
    best = None
    best_score = -1
    for path, obj in walk(data):
        if not isinstance(obj, dict):
            continue
        score = 0
        oid = str(obj.get("aweme_id") or obj.get("item_id") or "")
        if aweme_id and oid == aweme_id:
            score += 100
        if "video" in obj:
            score += 30
        if "author" in obj:
            score += 10
        if "desc" in obj:
            score += 10
        if "aweme_id" in obj:
            score += 10
        p = ".".join(path).lower()
        if any(k in p for k in ("aweme_detail", "item_list", "aweme_list", "aweme")):
            score += 8
        if score > best_score and score >= 30:
            best = obj
            best_score = score
    return best


def first_url(node: Any) -> str | None:
    if isinstance(node, str) and node.startswith(("http://", "https://")):
        return node
    if not isinstance(node, dict):
        return None
    for key in ("url_list", "urlList", "uri"):
        val = node.get(key)
        if isinstance(val, list):
            for u in val:
                if isinstance(u, str) and u.startswith(("http://", "https://")):
                    return u
        elif isinstance(val, str) and val.startswith(("http://", "https://")):
            return val
    return None


def normalize_video_url(url: str) -> str:
    return url.replace("/playwm/", "/play/").replace("playwm", "play")


def collect_item(item: dict[str, Any], aweme_id: str | None) -> dict[str, Any]:
    author_obj = item.get("author") if isinstance(item.get("author"), dict) else {}
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    title = str(item.get("desc") or item.get("title") or "").strip()
    author = str(author_obj.get("nickname") or author_obj.get("unique_id") or "").strip()

    media: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(node: Any, path: str, score: int, meta: dict[str, Any] | None = None):
        url = first_url(node)
        if not url:
            return
        url = normalize_video_url(url)
        if url in seen:
            return
        seen.add(url)
        row = {"path": path, "url": url, "score": score}
        if meta:
            row.update(meta)
        media.append(row)

    add(video.get("play_addr"), "video.play_addr", 80)
    add(video.get("play_addr_h264"), "video.play_addr_h264", 85)
    add(video.get("play_addr_bytevc1"), "video.play_addr_bytevc1", 70)
    add(video.get("download_addr"), "video.download_addr", 20)

    bit_rates = video.get("bit_rate") or video.get("bitRate") or []
    if isinstance(bit_rates, list):
        for i, br in enumerate(bit_rates):
            if not isinstance(br, dict):
                continue
            gear = str(br.get("gear_name") or br.get("quality_type") or "")
            bit_rate = int(br.get("bit_rate") or 0)
            score = 90 + min(bit_rate // 100000, 40)
            if "1080" in gear:
                score += 30
            elif "720" in gear:
                score += 20
            add(br.get("play_addr") or br.get("playAddr"), f"video.bit_rate.{i}", score, {
                "gear": gear,
                "bit_rate": bit_rate,
            })

    media.sort(key=lambda x: int(x.get("score") or 0), reverse=True)

    cover = (
        first_url(video.get("origin_cover"))
        or first_url(video.get("cover"))
        or first_url(video.get("dynamic_cover"))
    )
    return {
        "aweme_id": str(item.get("aweme_id") or aweme_id or ""),
        "title": title,
        "author": author,
        "cover": cover,
        "create_time": item.get("create_time"),
        "media_candidates": media,
    }


def download(session, url: str, dest: Path) -> dict[str, Any]:
    headers = {
        "User-Agent": UA_MOBILE,
        "Referer": "https://www.iesdouyin.com/",
        "Accept": "*/*",
    }
    kwargs = dict(headers=headers, timeout=90, allow_redirects=True, stream=True)
    if crequests is not None and session.__class__.__module__.startswith("curl_cffi"):
        kwargs["impersonate"] = "chrome"
    r = session.get(url, **kwargs)
    r.raise_for_status()
    ctype = (r.headers.get("content-type") or "").lower()
    if ctype.startswith("text/html") or ctype.startswith("application/json"):
        raise ValueError(f"not video content-type={ctype}")
    total = 0
    with dest.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                total += len(chunk)
    if total < 100 * 1024:
        raise ValueError(f"video too small: {total}")
    return {
        "status": r.status_code,
        "content_type": ctype,
        "bytes": total,
        "final_url": str(r.url),
        "path": str(dest),
    }


def ytdlp_fallback(url: str, out: Path) -> dict[str, Any]:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--write-info-json",
        "--merge-output-format", "mp4",
        "-f", "bv*+ba/b",
        "-o", str(out / "video.%(ext)s"),
        url,
    ]
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return {"returncode": cp.returncode, "log_tail": cp.stdout[-8000:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    session = session_new()
    report: dict[str, Any] = {"input_url": args.url, "errors": []}

    try:
        final_url, aweme_id, chain, short_html = resolve(session, args.url)
        report["resolved_url"] = final_url
        report["redirect_chain"] = chain
        report["aweme_id"] = aweme_id
        (out / "shortlink_response.html").write_text(short_html, encoding="utf-8", errors="ignore")
    except Exception as e:
        report["errors"].append(f"shortlink resolve failed: {type(e).__name__}: {e}")
        final_url = args.url
        aweme_id = extract_id(args.url)
        report["aweme_id"] = aweme_id

    if not aweme_id:
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    pages: list[tuple[str, str]] = []
    urls = [
        ("share_video", f"https://www.iesdouyin.com/share/video/{aweme_id}/", True),
        ("share_note", f"https://www.iesdouyin.com/share/note/{aweme_id}/", True),
        ("share_slides", f"https://www.iesdouyin.com/share/slides/{aweme_id}/", True),
        ("douyin_web", f"https://www.douyin.com/video/{aweme_id}", False),
    ]
    for name, page_url, mobile in urls:
        try:
            r = http_get(session, page_url, mobile=mobile, referer="https://www.douyin.com/")
            text = r.text
            (out / f"{name}.html").write_text(text, encoding="utf-8", errors="ignore")
            pages.append((name, text))
            report.setdefault("fetches", []).append({
                "name": name,
                "status": r.status_code,
                "url": str(r.url),
                "bytes": len(r.content),
            })
        except Exception as e:
            report["errors"].append(f"{name} failed: {type(e).__name__}: {e}")

    best_item = None
    best_source = None
    for name, page in pages:
        for kind, data in (("router", parse_router_data(page)), ("render", parse_render_data(page))):
            if data is None:
                continue
            (out / f"{name}.{kind}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            item = find_item(data, aweme_id)
            if item is not None:
                candidate = collect_item(item, aweme_id)
                if best_item is None or len(candidate["media_candidates"]) > len(best_item["media_candidates"]):
                    best_item = candidate
                    best_source = f"{name}.{kind}"

    if best_item:
        report.update(best_item)
        report["metadata_source"] = best_source
    else:
        report.setdefault("media_candidates", [])

    video_path = out / "video.mp4"
    for i, media in enumerate(report.get("media_candidates") or []):
        try:
            result = download(session, media["url"], video_path)
            report["selected_media"] = media
            report["download"] = result
            break
        except Exception as e:
            report["errors"].append(f"candidate {i} failed: {type(e).__name__}: {e}")
            video_path.unlink(missing_ok=True)

    if not video_path.exists():
        fb = ytdlp_fallback(final_url or args.url, out)
        report["yt_dlp_fallback"] = fb
        candidates = sorted(out.glob("video.*"))
        for p in candidates:
            if p.suffix.lower() in {".mp4", ".webm", ".mkv", ".mov"} and p.stat().st_size > 100 * 1024:
                if p != video_path:
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", str(p), "-c", "copy", str(video_path)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                        )
                    except Exception:
                        pass
                break

    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if video_path.exists() else 3


if __name__ == "__main__":
    raise SystemExit(main())
