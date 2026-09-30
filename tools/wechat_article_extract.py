#!/usr/bin/env python3
"""Extract a public WeChat article using free/open-source strategies.

Strategy order:
1. Direct HTTPS parsing derived from XUMUMI/read-wechat-articles (MIT).
2. Browser extraction via xiguawang/wechat-reader (MIT), when installed.

The script never solves CAPTCHAs or bypasses access controls. On local desktops,
wechat-reader can reuse/attach to a real Chrome session after the user completes
any required verification.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_HTML_BYTES = 8 * 1024 * 1024
BLOCK_TAGS = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "li"}
SKIP_TAGS = {"script", "style", "noscript", "svg"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK_MARKERS = ("环境异常", "当前环境异常", "完成验证后即可继续访问", "去验证", "访问过于频繁", "操作频繁", "wappoc_appmsgcaptcha")


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.author = ""
        self.in_content = False
        self.content_depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta":
            name = values.get("name") or values.get("property") or ""
            value = (values.get("content") or "").strip()
            if name in {"og:title", "twitter:title"} and not self.title:
                self.title = value
            elif name in {"author", "og:article:author"} and not self.author:
                self.author = value
        if not self.in_content and values.get("id") == "js_content":
            self.in_content = True
            self.content_depth = 1
            return
        if not self.in_content:
            return
        if tag not in VOID_TAGS:
            self.content_depth += 1
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif not self.skip_depth:
            if tag == "br" or tag in BLOCK_TAGS:
                self.parts.append("\n")
            elif tag == "img":
                source = values.get("data-src") or values.get("src") or ""
                if source and source not in self.images:
                    self.images.append(source)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.in_content and tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_content:
            return
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in BLOCK_TAGS:
            self.parts.append("\n")
        self.content_depth -= 1
        if self.content_depth == 0:
            self.in_content = False

    def handle_data(self, data: str) -> None:
        if self.in_content and not self.skip_depth:
            text = re.sub(r"[\t\r\f\v ]+", " ", data)
            if text.strip():
                self.parts.append(text)


class ImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = dict(attrs)
        source = values.get("data-src") or values.get("src") or ""
        if source and source not in self.images:
            self.images.append(source)


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "mp.weixin.qq.com":
        raise ValueError("URL must be a public article under https://mp.weixin.qq.com/")


def direct_download(url: str, timeout: int) -> str:
    validate_url(url)
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://mp.weixin.qq.com/",
    })
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        data = response.read(MAX_HTML_BYTES + 1)
        if content_type != "text/html":
            raise ValueError(f"Expected HTML but received {content_type}")
        if len(data) > MAX_HTML_BYTES:
            raise ValueError("Page exceeds the 8 MiB read limit")
        charset = response.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace")


def direct_parse(html: str, url: str) -> dict[str, Any]:
    lowered = html.lower()
    if any(marker.lower() in lowered for marker in BLOCK_MARKERS):
        raise ValueError("WeChat returned a verification/rate-limit page")
    parser = ArticleParser()
    parser.feed(html)
    raw = unescape("".join(parser.parts)).replace("\u200b", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
    body = "\n\n".join(line for line in lines if line)
    if not parser.title or not body:
        raise ValueError("Article title or body was not found; the page may require verification")
    timestamp = re.search(r'(?:publish_time%22%3A|publish_time["\']?\s*[:=]\s*["\']?)(\d{10})', html)
    published_at = datetime.fromtimestamp(int(timestamp.group(1))).astimezone().isoformat(timespec="minutes") if timestamp else None
    return {
        "status": "ok", "extractor": "direct-http", "title": parser.title,
        "author": parser.author or None, "published_at": published_at,
        "url": url, "content": body, "images": parser.images,
    }


def extract_browser(url: str, timeout: int, browser_strategy: str, wait_for_manual_verify: int) -> dict[str, Any]:
    try:
        from wechat_reader import read_article_sync
    except ModuleNotFoundError as exc:
        raise RuntimeError("wechat-reader is not installed") from exc
    result = read_article_sync(
        url, strategy=browser_strategy, timeout=timeout,
        ephemeral=(browser_strategy == "playwright"),
        wait_for_manual_verify=wait_for_manual_verify,
    )
    raw = result.to_dict()
    status = str(raw.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"wechat-reader status={status}: {raw.get('hint') or ''}")
    images: list[str] = []
    html = raw.get("html")
    if isinstance(html, str) and html:
        p = ImageParser()
        p.feed(html)
        images = p.images
    return {
        "status": "ok",
        "extractor": f"wechat-reader:{raw.get('metadata', {}).get('runtime_strategy') or browser_strategy}",
        "title": raw.get("title") or "",
        "author": raw.get("author") or raw.get("account_name") or None,
        "published_at": raw.get("publish_time") or None,
        "url": raw.get("url") or url,
        "content": raw.get("content") or "",
        "images": images,
        "browser_metadata": raw.get("metadata") or {},
    }


def render_markdown(result: dict[str, Any]) -> str:
    if result.get("status") != "ok":
        lines = ["# WeChat extraction blocked", "", f"- URL: {result.get('url', '')}", ""]
        for item in result.get("attempts") or []:
            lines.append(f"- {item.get('extractor')}: {item.get('status')} — {item.get('message', '')}")
        return "\n".join(lines) + "\n"
    return "\n".join([
        f"# {result.get('title') or 'Untitled'}", "",
        f"- Source: {result.get('url') or ''}",
        f"- Author: {result.get('author') or ''}",
        f"- Published: {result.get('published_at') or ''}",
        f"- Extractor: {result.get('extractor') or ''}", "",
        str(result.get("content") or ""), "",
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--strategy", choices=("auto", "direct", "browser"), default="auto")
    ap.add_argument("--browser-strategy", choices=("auto", "attach", "launch", "playwright"), default="auto")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--wait-for-manual-verify", type=int, default=0)
    ap.add_argument("--out-json")
    ap.add_argument("--out-md")
    ap.add_argument("--fail-on-blocked", action="store_true")
    args = ap.parse_args()
    validate_url(args.url)
    attempts: list[dict[str, str]] = []
    result: dict[str, Any] | None = None

    if args.strategy in {"auto", "direct"}:
        try:
            result = direct_parse(direct_download(args.url, args.timeout), args.url)
        except Exception as exc:
            attempts.append({"extractor": "direct-http", "status": "failed", "message": str(exc)})

    if result is None and args.strategy in {"auto", "browser"}:
        try:
            result = extract_browser(args.url, args.timeout, args.browser_strategy, args.wait_for_manual_verify)
        except Exception as exc:
            message = str(exc)
            status = "captcha_required" if "captcha" in message.lower() or "验证" in message else "failed"
            attempts.append({"extractor": "wechat-reader", "status": status, "message": message})

    if result is None:
        result = {
            "status": "blocked", "extractor": None, "title": "", "author": None,
            "published_at": None, "url": args.url, "content": "", "images": [],
            "attempts": attempts, "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        result["attempts"] = attempts
        result["fetched_at"] = datetime.now(timezone.utc).isoformat()

    if args.out_json:
        path = Path(args.out_json); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_md:
        path = Path(args.out_md); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(result), encoding="utf-8")

    print(json.dumps({
        "status": result.get("status"), "extractor": result.get("extractor"),
        "title": result.get("title"), "author": result.get("author"),
        "content_chars": len(str(result.get("content") or "")),
        "image_count": len(result.get("images") or []), "attempts": attempts,
    }, ensure_ascii=False, indent=2))
    return 2 if result.get("status") != "ok" and args.fail_on_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
