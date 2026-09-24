#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Toutiao article extractor derived from NanmiCoder/NewsCrawler's Toutiao parser,
extended for m.toutiao.com short links and modern RENDER_DATA/SSR pages.

Personal/research extraction only.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from parsel import Selector

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
ARTICLE_ID_RE = re.compile(r"/article/(\d+)")
RENDER_RE = re.compile(
    r'<script[^>]*\bid=["\']RENDER_DATA["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

def session():
    return crequests.Session() if crequests is not None else requests.Session()

def http_get(s, url: str, *, mobile: bool = False, referer: str | None = None):
    headers = {
        "User-Agent": UA_MOBILE if mobile else UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    if referer:
        headers["Referer"] = referer
    kwargs = {"headers": headers, "allow_redirects": True, "timeout": 40}
    if crequests is not None and s.__class__.__module__.startswith("curl_cffi"):
        kwargs["impersonate"] = "chrome"
    return s.get(url, **kwargs)

def resolve_short(s, url: str):
    r = http_get(s, url, mobile=True)
    chain = []
    for h in list(getattr(r, "history", []) or []) + [r]:
        chain.append({
            "status": getattr(h, "status_code", None),
            "url": str(getattr(h, "url", "")),
            "location": getattr(h, "headers", {}).get("location") if getattr(h, "headers", None) else None,
        })
    return str(r.url), r.text, chain

def parse_render_data(page: str):
    m = RENDER_RE.search(page)
    if not m:
        return None
    raw = html_lib.unescape(m.group(1).strip())
    for value in (raw, unquote(raw)):
        try:
            return json.loads(value)
        except Exception:
            pass
    return None

def walk(obj: Any, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (str(i),))
    else:
        yield path, obj
        if isinstance(obj, str):
            st = obj.strip()
            if len(st) > 2 and st[0] in "[{":
                try:
                    nested = json.loads(st)
                    yield from walk(nested, path + ("<json>",))
                except Exception:
                    pass

def get_article_id(*texts: str):
    for text in texts:
        if not text:
            continue
        m = ARTICLE_ID_RE.search(text)
        if m:
            return m.group(1)
    patterns = [
        r'["\'](?:article_id|group_id|item_id)["\']\s*[:=]\s*["\']?(\d{15,20})',
        r'\b(7\d{18})\b',
    ]
    for text in texts:
        if not text:
            continue
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1)
    return None

def text_of(node) -> str:
    return " ".join(x.strip() for x in node.xpath(".//text()").getall() if x.strip()).strip()

def parse_dom(page: str):
    sel = Selector(text=page)
    title = (
        sel.xpath("//h1/text()").get()
        or sel.xpath('//meta[@property="og:title"]/@content').get()
        or sel.xpath("//title/text()").get()
        or ""
    ).strip()
    author = (
        sel.xpath("//div[contains(@class,'article-meta')]//span[contains(@class,'name')]//a/text()").get()
        or sel.xpath('//meta[@name="author"]/@content').get()
        or ""
    ).strip()
    publish_time = (
        sel.xpath("//div[contains(@class,'article-meta')]/span[1]/text()").get()
        or sel.xpath('//meta[@property="article:published_time"]/@content').get()
        or ""
    ).strip()

    paragraphs = []
    images = []
    article_nodes = sel.xpath("//article")
    if article_nodes:
        for p in article_nodes.xpath(".//p"):
            t = text_of(p)
            if t:
                paragraphs.append(t)
        images = [u.strip() for u in article_nodes.xpath(".//img/@src").getall() if u.strip()]
        if not images:
            images = [u.strip() for u in article_nodes.xpath(".//img/@data-src").getall() if u.strip()]
    return title, author, publish_time, paragraphs, images

def parse_fragment(html_fragment: str):
    sel = Selector(text=html_fragment)
    paragraphs = []
    for p in sel.xpath("//p"):
        t = text_of(p)
        if t:
            paragraphs.append(t)
    if not paragraphs:
        body_text = " ".join(x.strip() for x in sel.xpath("//text()").getall() if x.strip()).strip()
        if body_text:
            # Split conservative blocks; keep source wording intact.
            paragraphs = [x.strip() for x in re.split(r"\n{2,}|(?<=[。！？])\s+", body_text) if x.strip()]
    images = [u.strip() for u in sel.xpath("//img/@src | //img/@data-src").getall() if u.strip()]
    return paragraphs, images

def parse_render_article(data: Any):
    if data is None:
        return {"title": "", "author": "", "publish_time": "", "paragraphs": [], "images": [], "candidates": []}

    title_candidates = []
    author_candidates = []
    time_candidates = []
    content_candidates = []

    for path, value in walk(data):
        if not isinstance(value, (str, int, float)):
            continue
        p = ".".join(path).lower()
        key = path[-1].lower() if path else ""
        sv = str(value).strip()
        if not sv:
            continue
        if key in {"title", "article_title"} and len(sv) < 300:
            title_candidates.append((p, sv))
        if key in {"author_name", "author", "name", "screen_name", "user_name"} and len(sv) < 120:
            author_candidates.append((p, sv))
        if key in {"publish_time", "publish_time_str", "create_time", "datetime"} and len(sv) < 120:
            time_candidates.append((p, sv))
        if key in {"content", "article_content", "content_html", "articlecontent"} or p.endswith(".content"):
            if len(sv) > 200:
                score = len(sv)
                low = sv.lower()
                if "<p" in low:
                    score += 5000
                if "<article" in low:
                    score += 5000
                if "article" in p:
                    score += 3000
                content_candidates.append((score, p, sv))

    content_candidates.sort(reverse=True)
    paragraphs, images = ([], [])
    chosen = None
    for score, p, value in content_candidates[:20]:
        ps, ims = parse_fragment(html_lib.unescape(value))
        if len("".join(ps)) > len("".join(paragraphs)):
            paragraphs, images = ps, ims
            chosen = {"path": p, "score": score, "chars": len(value)}

    def choose(cands):
        if not cands:
            return ""
        cands.sort(key=lambda x: (("article" in x[0]) + ("detail" in x[0]), len(x[1])), reverse=True)
        return cands[0][1]

    return {
        "title": choose(title_candidates),
        "author": choose(author_candidates),
        "publish_time": choose(time_candidates),
        "paragraphs": paragraphs,
        "images": images,
        "content_candidate": chosen,
        "candidates": [{"path": p, "chars": len(v), "score": s} for s, p, v in content_candidates[:10]],
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    s = session()
    report = {"input_url": args.url, "errors": [], "source_project": "NanmiCoder/NewsCrawler"}

    try:
        resolved, short_html, chain = resolve_short(s, args.url)
        report["resolved_url"] = resolved
        report["redirect_chain"] = chain
        (out / "shortlink_response.html").write_text(short_html, encoding="utf-8", errors="ignore")
    except Exception as e:
        resolved, short_html = args.url, ""
        report["errors"].append(f"shortlink resolve failed: {type(e).__name__}: {e}")

    article_id = get_article_id(resolved, short_html, args.url)
    report["article_id"] = article_id
    if not article_id:
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    canonical = f"https://www.toutiao.com/article/{article_id}/"
    report["canonical_url"] = canonical

    pages = [("shortlink_response.html", short_html)]
    for mobile in (False, True):
        try:
            r = http_get(s, canonical, mobile=mobile, referer="https://www.toutiao.com/")
            name = "article_mobile.html" if mobile else "article_desktop.html"
            (out / name).write_text(r.text, encoding="utf-8", errors="ignore")
            pages.append((name, r.text))
            report.setdefault("fetches", []).append({
                "name": name,
                "status": r.status_code,
                "final_url": str(r.url),
                "bytes": len(r.content),
            })
        except Exception as e:
            report["errors"].append(f"fetch mobile={mobile} failed: {type(e).__name__}: {e}")

    best = {"title": "", "author": "", "publish_time": "", "paragraphs": [], "images": [], "source": ""}
    render_found = False
    for name, page in pages:
        if not page:
            continue
        title, author, publish_time, paragraphs, images = parse_dom(page)
        if len("".join(paragraphs)) > len("".join(best["paragraphs"])):
            best = {
                "title": title, "author": author, "publish_time": publish_time,
                "paragraphs": paragraphs, "images": images, "source": name + ":dom"
            }

        data = parse_render_data(page)
        if data is not None:
            render_found = True
            safe = name.replace(".html", "")
            (out / f"{safe}.render_data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            rd = parse_render_article(data)
            report.setdefault("render_candidates", {})[name] = {
                "content_candidate": rd.get("content_candidate"),
                "candidates": rd.get("candidates", []),
            }
            if len("".join(rd["paragraphs"])) > len("".join(best["paragraphs"])):
                best = {
                    "title": rd["title"] or title,
                    "author": rd["author"] or author,
                    "publish_time": rd["publish_time"] or publish_time,
                    "paragraphs": rd["paragraphs"],
                    "images": rd["images"] or images,
                    "source": name + ":render_data",
                }

    # Last fallback: title/meta from any page even if no body parsed.
    if not best["title"]:
        for name, page in pages:
            if page:
                t, a, pt, _, _ = parse_dom(page)
                if t:
                    best["title"], best["author"], best["publish_time"] = t, a, pt
                    break

    report["render_data_found"] = render_found
    report.update(best)
    report["text_chars"] = len("\n".join(best["paragraphs"]))
    report["paragraph_count"] = len(best["paragraphs"])
    report["image_count"] = len(best["images"])

    md = []
    md.append(f"# {best['title'] or 'Toutiao article'}")
    md.append("")
    if best["author"]:
        md.append(f"- 作者：{best['author']}")
    if best["publish_time"]:
        md.append(f"- 发布时间：{best['publish_time']}")
    md.append(f"- 原文：{canonical}")
    md.append("")
    md.extend(best["paragraphs"])
    if best["images"]:
        md.append("")
        md.append("## 图片")
        md.extend(f"- {u}" for u in best["images"])

    (out / "article.md").write_text("\n\n".join(md), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("===== RESULT =====")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("===== ARTICLE =====")
    print((out / "article.md").read_text(encoding="utf-8"))

    return 0 if best["paragraphs"] else 3

if __name__ == "__main__":
    raise SystemExit(main())
