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



def parse_router_data(page: str) -> Any | None:
    """Extract Douyin mobile share page window._ROUTER_DATA JSON."""
    m = re.search(r"window\._ROUTER_DATA\s*=\s*", page)
    if not m:
        return None
    tail = page[m.end():]
    end = tail.find("</script>")
    if end >= 0:
        tail = tail[:end]
    raw = tail.strip().rstrip(";").strip()
    try:
        return json.loads(raw)
    except Exception:
        return None


def find_aweme_item(obj: Any, aweme_id: str) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        if str(obj.get("aweme_id") or "") == str(aweme_id) and isinstance(obj.get("video"), dict):
            return obj
        for v in obj.values():
            found = find_aweme_item(v, aweme_id)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_aweme_item(v, aweme_id)
            if found is not None:
                return found
    return None


def extract_douyin_media(item: dict[str, Any]) -> list[dict[str, str]]:
    video = item.get("video") if isinstance(item, dict) else None
    if not isinstance(video, dict):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_urls(node: Any, path: str, score_hint: int = 0) -> None:
        if not isinstance(node, dict):
            return
        urls = node.get("url_list")
        if not isinstance(urls, list):
            return
        for idx, raw in enumerate(urls):
            if not isinstance(raw, str) or not raw.startswith(("http://", "https://")):
                continue
            variants = [raw]
            if "/playwm/" in raw:
                variants.insert(0, raw.replace("/playwm/", "/play/"))
            for v in variants:
                if v in seen:
                    continue
                seen.add(v)
                out.append({"path": f"douyin.{path}.{idx}.score{score_hint}", "url": v})

    bit_rates = video.get("bit_rate")
    if isinstance(bit_rates, list):
        for i, br in enumerate(bit_rates):
            if not isinstance(br, dict):
                continue
            is_h265 = br.get("is_h265")
            codec = str(br.get("codec_type") or br.get("gear_name") or "")
            bitrate = int(br.get("bit_rate") or 0)
            # Prefer H.264/browser-friendly streams, then higher bitrate.
            bonus = bitrate + (10_000_000 if is_h265 in (0, False, None) or "h264" in codec.lower() else 0)
            add_urls(br.get("play_addr"), f"bit_rate.{i}.play_addr", bonus)

    for key in ("play_addr", "play_addr_h264", "download_addr"):
        add_urls(video.get(key), key, 0)

    def score(entry: dict[str, str]) -> int:
        p = entry["path"]
        m = re.search(r"\.score(\d+)$", p)
        s = int(m.group(1)) if m else 0
        if "/play/" in entry["url"]:
            s += 1000
        return s

    out.sort(key=score, reverse=True)
    return out


def fetch_douyin_share_fallback(session, aweme_id: str, out: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"aweme_id": aweme_id, "media_candidates": []}
    # Primary path for normal Douyin videos: mobile Feed API.
    # It avoids the PC Web Argus gate and does not require cookie/a_bogus.
    mobile_feed_ua = (
        "com.ss.android.ugc.aweme/290101 (Linux; U; Android 10; zh_CN; Pixel 4; "
        "Build/QQ3A.200805.001; Cronet/TTNetVersion:5f9037be 2023-01-13 "
        "QuicVersion:4668bb42 2022-11-21)"
    )
    feed_endpoints = [
        "https://api5-normal-c-hl.amemv.com/aweme/v1/feed/",
        "https://aweme.snssdk.com/aweme/v1/feed/",
    ]
    for endpoint in feed_endpoints:
        try:
            headers = {
                "User-Agent": mobile_feed_ua,
                "Accept": "application/json, text/plain, */*",
            }
            r = session.get(
                endpoint,
                params={"aweme_id": str(aweme_id), "aid": "1128"},
                headers=headers,
                timeout=12,
                allow_redirects=True,
            )
            report.setdefault("mobile_feed", []).append({
                "endpoint": endpoint,
                "status": r.status_code,
                "bytes": len(r.content),
            })
            if r.status_code != 200 or not r.text:
                continue
            data = r.json()
            safe = "amemv" if "amemv.com" in endpoint else "snssdk"
            (out / f"douyin_mobile_feed_{safe}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            aweme_list = data.get("aweme_list") if isinstance(data, dict) else None
            if not isinstance(aweme_list, list):
                continue
            item = next(
                (
                    x for x in aweme_list
                    if isinstance(x, dict)
                    and str(x.get("aweme_id") or x.get("id") or "") == str(aweme_id)
                ),
                None,
            )
            if item is None:
                continue
            media = extract_douyin_media(item)
            report["source"] = "douyin_mobile_feed"
            report["title"] = str(item.get("desc") or "").strip()
            author = item.get("author")
            if isinstance(author, dict):
                report["author"] = str(author.get("nickname") or "").strip()
            report["media_candidates"] = media
            if media:
                return report
        except Exception as e:
            report.setdefault("errors", []).append(
                f"mobile feed {endpoint} failed: {type(e).__name__}: {e}"
            )

    share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
    try:
        r = get(session, share_url, referer="https://www.douyin.com/", mobile=True)
        report["share_url"] = share_url
        report["share_status"] = r.status_code
        report["share_final_url"] = str(r.url)
        (out / "douyin_share.html").write_text(r.text, encoding="utf-8", errors="ignore")
        data = parse_router_data(r.text)
        if data is not None:
            (out / "douyin_share.router_data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            item = find_aweme_item(data, aweme_id)
            if item is not None:
                report["source"] = "iesdouyin_share_router_data"
                report["title"] = str(item.get("desc") or "").strip()
                author = item.get("author")
                if isinstance(author, dict):
                    report["author"] = str(author.get("nickname") or "").strip()
                report["media_candidates"] = extract_douyin_media(item)
                return report
    except Exception as e:
        report.setdefault("errors", []).append(f"share page failed: {type(e).__name__}: {e}")

    # Older public JSON endpoint still works intermittently; keep it as a secondary fallback.
    api = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={aweme_id}"
    try:
        headers = {
            "User-Agent": UA_MOBILE,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json,text/plain,*/*",
        }
        kwargs = dict(headers=headers, timeout=40, allow_redirects=True)
        if crequests is not None and session.__class__.__module__.startswith("curl_cffi"):
            kwargs["impersonate"] = "chrome"
        r = session.get(api, **kwargs)
        report["iteminfo_status"] = r.status_code
        data = r.json()
        (out / "douyin_iteminfo.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        item = find_aweme_item(data, aweme_id)
        if item is not None:
            report["source"] = "iesdouyin_iteminfo"
            report["title"] = str(item.get("desc") or "").strip()
            author = item.get("author")
            if isinstance(author, dict):
                report["author"] = str(author.get("nickname") or "").strip()
            report["media_candidates"] = extract_douyin_media(item)
    except Exception as e:
        report.setdefault("errors", []).append(f"iteminfo failed: {type(e).__name__}: {e}")
    return report


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
    # The resolved short link may already be a working m.toutiao.com/video page even when
    # www.toutiao.com/video/{id}/ returns 404. Reuse that HTML as a first-class source.
    if short_html:
        pages.append(("shortlink_response.html", short_html))

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

    # Toutiao "from_aweme=1" reflux pages may expose no playable URL/token.
    # Fall back to Douyin's mobile share SSR, which can carry the original aweme item.
    if not report.get("media_candidates") and vid:
        dy = fetch_douyin_share_fallback(session, vid, out)
        report["douyin_fallback"] = {
            k: v for k, v in dy.items() if k != "media_candidates"
        }
        dy_media = dy.get("media_candidates") or []
        if dy_media:
            report["media_candidates"] = dy_media
            if dy.get("title"):
                report["title"] = dy["title"]
            if dy.get("author"):
                report["author"] = dy["author"]

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
