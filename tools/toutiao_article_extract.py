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
import os
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
        or sel.xpath("//span[contains(@class,'author-name')]/text()").get()
        or sel.xpath('//meta[@property="og:article:author"]/@content').get()
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

def _normalize_url(url: str) -> str:
    url = html_lib.unescape(str(url or "")).strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://mp.weixin.qq.com/"):
        return "https://" + url[len("http://"):]
    return url


def get_source_url(data: Any) -> str:
    if isinstance(data, dict):
        info = data.get("articleInfo") or data.get("articleinfo")
        if isinstance(info, dict):
            url = _normalize_url(info.get("url") or info.get("source_url") or "")
            if "mp.weixin.qq.com/s" in url:
                return url
    if data is not None:
        for _, value in walk(data):
            if isinstance(value, str) and "mp.weixin.qq.com/s" in value:
                return _normalize_url(value)
    return ""


def _dedupe_urls(urls):
    out = []
    seen = set()
    for url in urls:
        u = _normalize_url(url)
        if not u or u in seen:
            continue
        if u.startswith(("data:", "javascript:")):
            continue
        seen.add(u)
        out.append(u)
    return out


def parse_wechat_images(page: str):
    sel = Selector(text=page)
    roots = sel.xpath("//*[@id='js_content']")
    scope = roots if roots else sel
    images = []
    for attr in ("data-src", "src", "data-original", "data-backsrc"):
        images.extend(
            u.strip()
            for u in scope.xpath(f".//img/@{attr}").getall()
            if isinstance(u, str) and u.strip()
        )
    # Some public WeChat pages expose a cover image only in OG metadata.
    if not images:
        images.extend(
            u.strip()
            for u in sel.xpath('//meta[@property="og:image"]/@content').getall()
            if isinstance(u, str) and u.strip()
        )
    return _dedupe_urls(images)


REDFOX_BASE = os.getenv("REDFOX_BASE_URL", "https://redfox.hk").rstrip("/")


def _redfox_post(path: str, payload: dict):
    key = os.getenv("REDFOX_API_KEY", "").strip()
    if not key:
        raise RuntimeError("REDFOX_API_KEY not configured")
    r = requests.post(
        REDFOX_BASE + path,
        json=payload,
        timeout=40,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": key,
            "REDFOX_API_KEY": key,
            "User-Agent": UA_DESKTOP,
        },
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("RedFox returned non-object")
    code = int(data.get("code") or 0)
    if code not in (200, 2000):
        raise RuntimeError(str(data.get("msg") or data.get("message") or f"RedFox code={code}"))
    return data.get("data")


def _redfox_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "records", "data"):
            rows = data.get(key)
            if isinstance(rows, list):
                return rows
    return []


def _norm_text(value: str) -> str:
    return re.sub(r"\\s+", "", str(value or "")).casefold()


def redfox_article_detail(author: str, title: str):
    author = str(author or "").strip()
    title = str(title or "").strip()
    if not author or not title:
        raise RuntimeError("missing author/title for RedFox lookup")

    search = _redfox_post(
        "/story/api/gzh/data/searchUser",
        {"keyword": author, "offset": 0},
    )
    accounts = [x for x in _redfox_rows(search) if isinstance(x, dict)]
    if not accounts:
        raise RuntimeError(f"RedFox account not found: {author}")

    an = _norm_text(author)
    accounts.sort(
        key=lambda x: (
            int(_norm_text(x.get("accountName")) == an or _norm_text(x.get("account")) == an or _norm_text(x.get("wxId")) == an),
            int(_norm_text(x.get("accountName")).startswith(an) or _norm_text(x.get("account")).startswith(an)),
        ),
        reverse=True,
    )
    account = accounts[0]
    identity = {}
    if str(account.get("wxId") or "").strip():
        identity["wxId"] = str(account.get("wxId")).strip()
    elif str(account.get("bizInfo") or "").strip():
        identity["bizInfo"] = str(account.get("bizInfo")).strip()
    elif str(account.get("account") or "").strip():
        identity["account"] = str(account.get("account")).strip()
    if not identity:
        raise RuntimeError("RedFox account record has no query identifier")

    target = _norm_text(title)
    matched = None
    candidates = []
    for offset in range(0, 201, 20):
        payload = {
            "source": "Toutiao article extractor",
            "sortType": "2",
            "offset": offset,
            **identity,
        }
        listing = _redfox_post("/story/api/gzh/data/queryWorkList", payload)
        rows = [x for x in _redfox_rows(listing) if isinstance(x, dict)]
        if not rows:
            break
        candidates.extend(rows)
        for row in rows:
            rt = _norm_text(row.get("title"))
            if rt == target or (rt and target and (rt in target or target in rt)):
                matched = row
                break
        if matched:
            break
        if len(rows) < 20:
            break

    if not matched and candidates:
        # Reprints occasionally alter punctuation/subtitles. Choose only a very
        # close title match rather than silently accepting an unrelated work.
        import difflib
        scored = sorted(
            ((difflib.SequenceMatcher(None, target, _norm_text(x.get("title"))).ratio(), x) for x in candidates),
            key=lambda z: z[0],
            reverse=True,
        )
        if scored and scored[0][0] >= 0.72:
            matched = scored[0][1]

    if not matched:
        sample = [str(x.get("title") or "") for x in candidates[:8]]
        raise RuntimeError(f"RedFox article not found; recent titles={sample}")

    work_uuid = str(matched.get("workUuid") or matched.get("uuid") or matched.get("id") or "").strip()
    if not work_uuid:
        raise RuntimeError("RedFox article has no workUuid")

    detail = _redfox_post(
        "/story/api/gzh/data/workDetail",
        {"source": "Toutiao article extractor", "workUuid": work_uuid},
    )
    if isinstance(detail, list):
        detail = detail[0] if detail else {}
    if not isinstance(detail, dict):
        raise RuntimeError("RedFox workDetail returned unexpected data")
    return detail, work_uuid, account


def extract_images_from_detail(detail: Any):
    images = []

    def add(value):
        if not isinstance(value, str):
            return
        value = html_lib.unescape(value).replace(r"\\/", "/").strip()
        if not value:
            return

        low = value.lower()
        if "<img" in low or "data-src" in low:
            try:
                _, ims = parse_fragment(value)
                images.extend(ims)
            except Exception:
                pass
            try:
                sel = Selector(text=value)
                for attr in ("data-src", "src", "data-original", "data-backsrc"):
                    images.extend(
                        x.strip() for x in sel.xpath(f"//img/@{attr}").getall()
                        if isinstance(x, str) and x.strip()
                    )
            except Exception:
                pass

        images.extend(
            m.group(1).strip()
            for m in re.finditer(r"!\\[[^\\]]*\\]\\((https?://[^)\\s]+)\\)", value)
        )

        for m in re.finditer(r"https?://[^\\s\\\"'<>\\)]+", value):
            u = m.group(0).rstrip(".,;")
            ul = u.lower()
            if (
                any(host in ul for host in (
                    "mmbiz.qpic.cn", "mmbiz.qlogo.cn", "mmbiz.qpic", "toutiaoimg.com",
                    "byteimg.com", "tos-cn-", "imagex", "qpic.cn",
                ))
                or re.search(r"\\.(?:jpe?g|png|webp|gif)(?:\\?|$)", ul)
            ):
                images.append(u)

    def visit(obj, key=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                if isinstance(v, str) and any(t in kl for t in ("image", "img", "pic", "cover", "content", "html")):
                    add(v)
                visit(v, kl)
        elif isinstance(obj, list):
            for v in obj:
                visit(v, key)
        elif isinstance(obj, str):
            add(obj)

    visit(detail)
    return _dedupe_urls(images)


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
    source_url = ""
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
            if not source_url:
                source_url = get_source_url(data)
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

    # Older mobile and PWA detail APIs sometimes retain inline images even
    # when the public SSR article body has had its <img> nodes removed.
    detail_api_images = []
    detail_api_fetches = []
    detail_api_urls = [
        f"https://m.toutiao.com/i{article_id}/info/",
        f"https://m.toutiao.com/pwa/api/wxapp/info/{article_id}/",
    ]
    for api_url in detail_api_urls:
        try:
            ar = http_get(s, api_url, mobile=True, referer=canonical)
            info = {
                "url": api_url,
                "status": ar.status_code,
                "final_url": str(ar.url),
                "bytes": len(ar.content),
            }
            try:
                payload = ar.json()
            except Exception:
                try:
                    payload = json.loads(ar.text)
                except Exception:
                    payload = None
            if payload is not None:
                safe_name = "detail_api_" + str(len(detail_api_fetches) + 1) + ".json"
                (out / safe_name).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                ims = extract_images_from_detail(payload)
                detail_api_images.extend(ims)
                info["image_count"] = len(ims)
                if isinstance(payload, dict):
                    info["top_keys"] = list(payload.keys())[:30]
            detail_api_fetches.append(info)
        except Exception as e:
            detail_api_fetches.append({"url": api_url, "error": f"{type(e).__name__}: {e}"})

    report["detail_api_fetches"] = detail_api_fetches
    detail_api_images = _dedupe_urls(detail_api_images)
    report["detail_api_image_count"] = len(detail_api_images)
    if detail_api_images:
        best["images"] = _dedupe_urls(list(best.get("images") or []) + detail_api_images)

    # Toutiao reprints can strip inline image nodes from articleInfo.content.
    # If RENDER_DATA exposes the original WeChat source, fetch that public page
    # and recover its inline images.
    source_images = []
    if source_url:
        report["source_url"] = source_url
        try:
            wr = http_get(s, source_url, mobile=True, referer="https://mp.weixin.qq.com/")
            (out / "source_article.html").write_text(wr.text, encoding="utf-8", errors="ignore")
            source_images = parse_wechat_images(wr.text)
            report["source_fetch"] = {
                "status": wr.status_code,
                "final_url": str(wr.url),
                "bytes": len(wr.content),
                "image_count": len(source_images),
            }
        except Exception as e:
            report["errors"].append(f"source fetch failed: {type(e).__name__}: {e}")

    if source_images:
        best["images"] = _dedupe_urls(list(best.get("images") or []) + source_images)

    # If the direct WeChat page is protected by a CAPTCHA, fall back to the
    # already-configured RedFox public article database and recover the full
    # work detail by account + exact title.
    if source_url and not source_images and os.getenv("REDFOX_API_KEY", "").strip() and os.getenv("SKIP_REDFOX", "").strip() != "1":
        try:
            detail, work_uuid, account = redfox_article_detail(best.get("author"), best.get("title"))
            (out / "redfox_work_detail.json").write_text(
                json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            redfox_images = extract_images_from_detail(detail)
            report["redfox_work_uuid"] = work_uuid
            report["redfox_account"] = {
                "account": account.get("account"),
                "accountName": account.get("accountName"),
                "wxId": account.get("wxId"),
            }
            report["redfox_image_count"] = len(redfox_images)
            if redfox_images:
                best["images"] = _dedupe_urls(list(best.get("images") or []) + redfox_images)
        except Exception as e:
            report["errors"].append(f"RedFox fallback failed: {type(e).__name__}: {e}")

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
