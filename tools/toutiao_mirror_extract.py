#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover and optionally download article images from a public mirror page.

Supports ordinary article DOMs and Next.js pages that hide article HTML inside
__NEXT_DATA__. Intended as a fallback after the primary Toutiao extractor.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import zipfile
from urllib.parse import urlsplit, urlunsplit

import requests
from parsel import Selector

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

IMAGE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


def dedupe(values):
    out = []
    seen = set()
    for value in values:
        value = html.unescape(str(value or "")).strip()
        if value.startswith("//"):
            value = "https:" + value
        if not value or value in seen or value.startswith(("data:", "javascript:")):
            continue
        seen.add(value)
        out.append(value)
    return out


def image_urls_from_html(fragment: str):
    sel = Selector(text=fragment or "")
    urls = []
    for attr in ("src", "data-src", "data-original", "data-backsrc"):
        urls.extend(
            x.strip()
            for x in sel.xpath(f"//img/@{attr}").getall()
            if isinstance(x, str) and x.strip()
        )
    return dedupe(urls)


def walk_strings(value, path=()):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk_strings(v, path + (str(k),))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk_strings(v, path + (str(i),))
    elif isinstance(value, str):
        yield path, value


def extract_next_data(page: str):
    sel = Selector(text=page)
    raw = sel.xpath('//script[@id="__NEXT_DATA__"]/text()').get()
    if not raw:
        return [], {}
    try:
        data = json.loads(raw)
    except Exception:
        return [], {}

    html_candidates = []
    direct_urls = []
    metadata = {}
    for path, value in walk_strings(data):
        low_path = ".".join(path).lower()
        low = value.lower()
        if "<img" in low:
            html_candidates.append((low.count("<img"), len(value), value, low_path))
        if any(k in low_path for k in ("image", "img", "cover", "poster", "pic")):
            if re.match(r"^https?://", value.strip()):
                direct_urls.append(value.strip())
        leaf = path[-1].lower() if path else ""
        if leaf in ("title", "article_title") and "title" not in metadata:
            metadata["title"] = value.strip()
        if leaf in ("froms", "source", "author", "author_name") and "source" not in metadata:
            metadata["source"] = value.strip()

    urls = []
    if html_candidates:
        html_candidates.sort(reverse=True)
        # Prefer the candidate containing the most inline images. When this
        # yields body images, do not mix in cover/related-card images elsewhere
        # in __NEXT_DATA__.
        urls = image_urls_from_html(html_candidates[0][2])
        metadata["next_data_path"] = html_candidates[0][3]
        if urls:
            return dedupe(urls), metadata
    return dedupe(direct_urls), metadata


def extract_dom(page: str):
    sel = Selector(text=page)
    roots = (
        sel.xpath("//article")
        or sel.xpath("//main")
        or sel.xpath("//*[contains(@class,'article-content') or contains(@class,'article_content') or contains(@class,'news-content')]")
    )
    urls = []
    scope = roots if roots else sel
    for attr in ("src", "data-src", "data-original", "data-backsrc"):
        urls.extend(
            x.strip()
            for x in scope.xpath(f".//img/@{attr}").getall()
            if isinstance(x, str) and x.strip()
        )
    return dedupe(urls)


def clean_original_url(url: str):
    parts = urlsplit(url)
    # Try the underlying asset without resize/tracking query first. Fall back to
    # the exact URL if the origin requires a signature.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def download_images(urls, outdir: pathlib.Path, referer: str):
    outdir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    headers = {"User-Agent": UA, "Referer": referer}
    manifest = []
    for index, url in enumerate(urls, 1):
        attempts = dedupe([clean_original_url(url), url])
        response = None
        used = None
        for candidate in attempts:
            try:
                r = session.get(candidate, timeout=40, headers=headers)
                if r.status_code < 400 and r.content:
                    response = r
                    used = candidate
                    break
            except requests.RequestException:
                pass
        if response is None:
            manifest.append({"index": index, "url": url, "error": "download failed"})
            continue

        ctype = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        ext = IMAGE_EXT.get(ctype)
        if not ext:
            ext = pathlib.Path(urlsplit(used).path).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"):
                ext = ".bin"
        path = outdir / f"{index:02d}{ext}"
        path.write_bytes(response.content)
        manifest.append({
            "index": index,
            "url": url,
            "download_url": used,
            "file": path.name,
            "bytes": len(response.content),
            "content_type": ctype,
        })
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    r = requests.get(
        args.url,
        timeout=40,
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"},
    )
    r.raise_for_status()
    (out / "mirror.html").write_text(r.text, encoding="utf-8", errors="ignore")

    next_urls, metadata = extract_next_data(r.text)
    dom_urls = extract_dom(r.text)
    # Structured article-body extraction wins over full-page DOM scanning.
    # The latter often contains cover, recommendation and UI images.
    urls = dedupe(next_urls if next_urls else dom_urls)

    result = {
        "mirror_url": args.url,
        "status": r.status_code,
        "final_url": str(r.url),
        "bytes": len(r.content),
        "image_count": len(urls),
        "images": urls,
        **metadata,
    }

    if args.download and urls:
        files = download_images(urls, out / "images", str(r.url))
        result["downloaded_count"] = len([x for x in files if not x.get("error")])
        result["files"] = files
        with zipfile.ZipFile(out / "article_images.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for item in files:
                if item.get("file"):
                    z.write(out / "images" / item["file"], arcname=item["file"])

    (out / "mirror_images.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
