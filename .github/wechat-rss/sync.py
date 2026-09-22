#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "wechat-rss"
DATA_DIR = PUBLIC_DIR / "data"
RSS_DIR = PUBLIC_DIR / "rss"
SOURCES_FILE = PUBLIC_DIR / "sources.json"

SOGOU_HOST = "https://weixin.sogou.com"
SOGOU_SEARCH = f"{SOGOU_HOST}/weixin"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
BLOCK_MARKERS = (
    "请输入验证码",
    "访问过于频繁",
    "您的访问过于频繁",
    "异常访问",
    "antispider",
    "seccode",
)

ADD_SOURCE = os.getenv("ADD_SOURCE", "").strip()
ADD_NAME = os.getenv("ADD_NAME", "").strip()
MAX_ITEMS = max(20, min(int(os.getenv("MAX_ITEMS", "120")), 500))
REQUEST_TIMEOUT = max(5, int(os.getenv("REQUEST_TIMEOUT", "20")))


def page_base_url() -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "whichow/whichow.github.io")
    owner, repo = repository.split("/", 1)
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/wechat-rss"
    return f"https://{owner}.github.io/{repo}/wechat-rss"


def slug_for(query: str) -> str:
    return hashlib.sha1(query.encode("utf-8")).hexdigest()[:12]


def load_sources() -> list[dict]:
    if not SOURCES_FILE.exists():
        return []
    try:
        data = json.loads(SOURCES_FILE.read_text("utf-8"))
        sources = data.get("sources", []) if isinstance(data, dict) else []
        return [
            x for x in sources
            if isinstance(x, dict)
            and (
                str(x.get("query", "")).strip()
                or str(x.get("seed_url", "")).strip()
            )
        ]
    except Exception:
        return []


def save_sources(sources: list[dict]) -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_FILE.write_text(
        json.dumps({"sources": sources}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_wechat_article_url(value: str) -> bool:
    value = value.strip()
    return value.startswith(("https://mp.weixin.qq.com/s", "http://mp.weixin.qq.com/s"))


def resolve_article_source(url: str) -> tuple[str, str]:
    """Resolve a public WeChat article URL to (account_name, article_title).

    No login, cookies, CAPTCHA solving, or browser automation is used.
    """
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://mp.weixin.qq.com/",
        },
    )
    response.raise_for_status()
    text = response.text
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in BLOCK_MARKERS):
        raise RuntimeError("微信文章公开页要求验证码或限制访问，无法从该链接识别公众号")

    soup = BeautifulSoup(text, "html.parser")
    account_name = ""
    for selector in (
        "#js_name",
        ".rich_media_meta_nickname",
        "#js_wx_follow_nickname",
    ):
        node = soup.select_one(selector)
        if node:
            account_name = node.get_text(" ", strip=True)
            if account_name:
                break

    if not account_name:
        meta = soup.find("meta", attrs={"property": "og:article:author"})
        if meta and meta.get("content"):
            account_name = str(meta.get("content") or "").strip()

    if not account_name:
        patterns = (
            r'(?:var\s+)?nickname\s*=\s*["\'](.+?)["\']\s*;',
            r'window\.nickname\s*=\s*["\'](.+?)["\']\s*;',
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                account_name = html.unescape(match.group(1)).strip()
                if account_name:
                    break

    title = ""
    title_node = soup.select_one("#activity-name, h1.rich_media_title")
    if title_node:
        title = title_node.get_text(" ", strip=True)
    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            title = str(meta.get("content") or "").strip()

    if not account_name:
        raise RuntimeError("已打开微信文章，但公开页面里没有解析到公众号名称")
    return account_name, title


def normalize_source(source: dict) -> tuple[str, str]:
    """Return (query, display_name), resolving seed article URLs when needed."""
    query = str(source.get("query") or "").strip()
    seed_url = str(source.get("seed_url") or "").strip()
    display = str(source.get("name") or "").strip()

    if is_wechat_article_url(query) and not seed_url:
        seed_url = query
        source["seed_url"] = seed_url
        source["query"] = ""
        query = ""

    if not query and seed_url:
        account_name, article_title = resolve_article_source(seed_url)
        query = account_name
        source["query"] = query
        source["resolved_from"] = seed_url
        if article_title:
            source["seed_title"] = article_title
        if not display:
            source["name"] = account_name
            display = account_name
        print(f"[source] resolved article URL -> {account_name}")

    if not query:
        raise RuntimeError("公众号订阅缺少可搜索的名称或微信号")
    return query, display or query


def add_source(sources: list[dict]) -> list[dict]:
    if not ADD_SOURCE:
        return sources
    raw = ADD_SOURCE.strip()
    key = raw.lower()
    for item in sources:
        existing = str(item.get("seed_url") or item.get("query") or "").strip().lower()
        if existing == key:
            if ADD_NAME:
                item["name"] = ADD_NAME
            item["enabled"] = True
            save_sources(sources)
            print(f"[source] already exists: {raw}")
            return sources

    if is_wechat_article_url(raw):
        sources.append({"query": "", "seed_url": raw, "name": ADD_NAME, "enabled": True})
    else:
        sources.append({"query": raw, "name": ADD_NAME, "enabled": True})
    save_sources(sources)
    print(f"[source] added: {raw}")
    return sources


def parse_timestamp(script_text: str) -> int:
    match = re.search(r"timeConvert\(['\"]?(\d+)['\"]?\)", script_text or "")
    return int(match.group(1)) if match else 0


def resolve_sogou_link(session: requests.Session, href: str) -> str:
    url = urljoin(SOGOU_HOST, href)
    try:
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            headers={"Referer": SOGOU_SEARCH},
        )
        location = response.headers.get("Location", "").strip()
        if location:
            target = urljoin(url, location)
            if target.startswith(("https://mp.weixin.qq.com/", "http://mp.weixin.qq.com/")):
                return target
            # One conservative extra redirect hop. No cookies, CAPTCHA handling,
            # proxy rotation, or access-control bypass.
            second = session.get(
                target,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                headers={"Referer": url},
            )
            location2 = second.headers.get("Location", "").strip()
            if location2:
                target2 = urljoin(target, location2)
                if target2.startswith(("https://mp.weixin.qq.com/", "http://mp.weixin.qq.com/")):
                    return target2
    except requests.RequestException:
        pass
    return url


def fetch_sogou(query: str) -> tuple[list[dict], str, str]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    response = session.get(
        SOGOU_SEARCH,
        params={
            "type": "2",
            "query": query,
            "ie": "utf8",
            "s_from": "input",
            "page": "1",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    text = response.text
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in BLOCK_MARKERS):
        raise RuntimeError("搜狗微信要求验证码或限制访问；本任务不会绕过验证，保留旧数据等待下次同步")

    soup = BeautifulSoup(text, "html.parser")
    nodes = soup.select("ul.news-list > li")
    if not nodes:
        raise RuntimeError("搜狗微信没有返回文章结果；请确认输入的是准确公众号名称或微信号")

    items: list[dict] = []
    account_name = ""
    for node in nodes:
        anchor = node.select_one("h3 > a")
        if anchor is None:
            continue
        title = anchor.get_text(" ", strip=True)
        href = str(anchor.get("href") or "").strip()
        if not title or not href:
            continue

        description_node = node.select_one("p.txt-info")
        description = description_node.get_text(" ", strip=True) if description_node else ""

        author_node = node.select_one("span.all-time-y2")
        author = author_node.get_text(" ", strip=True) if author_node else ""
        if author and not account_name:
            account_name = author

        script_node = node.select_one("span.s2 script")
        publish_at = parse_timestamp(script_node.get_text(" ", strip=True) if script_node else "")

        link = resolve_sogou_link(session, href)
        guid = link or urljoin(SOGOU_HOST, href)
        items.append(
            {
                "guid": guid,
                "title": title,
                "description": description,
                "author": author,
                "publish_at": publish_at,
                "url": link,
                "sogou_url": urljoin(SOGOU_HOST, href),
                "fetched_at": int(time.time()),
            }
        )

    if not items:
        raise RuntimeError("搜狗微信页面已返回，但没有解析到有效文章")
    return items, account_name or query, response.url


def load_old_items(slug: str) -> list[dict]:
    path = DATA_DIR / f"{slug}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text("utf-8"))
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return [x for x in items if isinstance(x, dict)]
    except Exception:
        return []


def merge_items(new_items: list[dict], old_items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in old_items + new_items:
        key = str(item.get("guid") or "").strip()
        if not key:
            key = hashlib.sha1(
                (str(item.get("title", "")) + "|" + str(item.get("publish_at", 0))).encode("utf-8")
            ).hexdigest()
        merged[key] = item
    return sorted(
        merged.values(),
        key=lambda x: (int(x.get("publish_at") or 0), int(x.get("fetched_at") or 0)),
        reverse=True,
    )[:MAX_ITEMS]


def write_rss(path: Path, title: str, items: list[dict], link: str) -> None:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = f"{title} - GitHub Actions 静态 RSS"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
    for item in items:
        entry = ET.SubElement(channel, "item")
        ET.SubElement(entry, "title").text = str(item.get("title") or "")
        ET.SubElement(entry, "link").text = str(item.get("url") or item.get("sogou_url") or "")
        ET.SubElement(entry, "guid", {"isPermaLink": "false"}).text = str(item.get("guid") or "")
        ts = int(item.get("publish_at") or 0)
        if ts:
            ET.SubElement(entry, "pubDate").text = format_datetime(
                datetime.fromtimestamp(ts, timezone.utc)
            )
        ET.SubElement(entry, "description").text = str(item.get("description") or "")
        author = str(item.get("author") or "")
        if author:
            ET.SubElement(entry, "author").text = author
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(rss).write(path, encoding="utf-8", xml_declaration=True)


def fmt_time(ts: int) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def render_index(source_outputs: list[dict], all_feed: str) -> str:
    cards = []
    recent: list[tuple[int, str, dict]] = []
    for src in source_outputs:
        status = src["status"]
        status_label = "正常" if status == "ok" else "暂时受限"
        status_class = "ok" if status == "ok" else "warn"
        cards.append(
            f"""<section class="card">
<div class="row"><div><h2>{html.escape(src["name"])}</h2><code>{html.escape(src["query"])}</code></div>
<span class="pill {status_class}">{status_label}</span></div>
<p>{len(src["items"])} 篇已保存 · <a href="{html.escape(src["feed"])}">独立 RSS</a></p>
{f'<p class="error">{html.escape(src["message"])}</p>' if src["message"] else ''}
</section>"""
        )
        for item in src["items"][:10]:
            recent.append((int(item.get("publish_at") or 0), src["name"], item))
    recent.sort(key=lambda x: x[0], reverse=True)
    recent_html = "\n".join(
        f"""<article><a href="{html.escape(str(item.get("url") or item.get("sogou_url") or ""))}" target="_blank" rel="noreferrer">{html.escape(str(item.get("title") or ""))}</a>
<small>{html.escape(name)} · {html.escape(fmt_time(int(item.get("publish_at") or 0)))}</small></article>"""
        for _, name, item in recent[:50]
    )
    if not cards:
        cards.append(
            """<section class="card"><h2>还没有公众号</h2>
<p>GitHub → Actions → <b>WeChat RSS Sync</b> → Run workflow，在 <code>source</code> 中输入公众号准确名称或微信号即可。</p></section>"""
        )

    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>微信公众号 RSS</title>
<style>
:root{{--bg:#f7f8fa;--card:#fff;--text:#182026;--muted:#667085;--line:#e4e7ec}}
@media(prefers-color-scheme:dark){{:root{{--bg:#101214;--card:#171a1d;--text:#f2f4f7;--muted:#98a2b3;--line:#344054}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.6}}
main{{max-width:900px;margin:auto;padding:48px 20px 90px}}a{{color:#1570ef;text-decoration:none}}h1{{font-size:clamp(30px,5vw,46px);margin:0 0 8px}}h2{{margin:0;font-size:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px}}
.row{{display:flex;justify-content:space-between;gap:16px}}code,small{{color:var(--muted)}}.pill{{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:3px 9px}}.ok{{color:#12b76a}}.warn,.error{{color:#f79009}}
.recent{{margin-top:34px}}article{{padding:14px 0;border-bottom:1px solid var(--line)}}article a{{font-weight:650}}article small{{display:block;margin-top:4px}}
</style><main><header><h1>微信公众号 RSS</h1>
<p>GitHub Actions · 搜狗微信公开检索 · 无微信读书 · 无扫码 · 无登录态</p>
<p><a href="{html.escape(all_feed)}">订阅全部公众号 RSS</a></p></header>
<div class="grid">{''.join(cards)}</div>
<section class="recent"><h2>最近文章</h2>{recent_html or '<p>暂无文章。</p>'}</section>
<footer><small>只整理公开搜索结果中的标题、摘要、发布时间和原文/跳转链接。遇到验证码或访问限制会停止，不绕过验证。</small></footer>
</main></html>"""


def main() -> int:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RSS_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / ".nojekyll").write_text("", encoding="utf-8")

    sources = add_source(load_sources())
    base = page_base_url()
    outputs: list[dict] = []
    all_items: dict[str, dict] = {}

    for source in sources:
        if not bool(source.get("enabled", True)):
            continue
        try:
            query, display = normalize_source(source)
            save_sources(sources)
        except Exception as exc:
            query = str(source.get("query") or source.get("seed_url") or "").strip()
            display = str(source.get("name") or query or "未识别公众号").strip()
            slug = slug_for(query or display)
            old_items = load_old_items(slug)
            message = str(exc)
            print(f"[source] {message}", file=sys.stderr)
            payload = {
                "query": query,
                "name": display,
                "status": "blocked",
                "message": message,
                "search_url": "",
                "updated_at": int(time.time()),
                "items": old_items,
            }
            (DATA_DIR / f"{slug}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            feed = f"{base}/rss/{slug}.xml"
            write_rss(RSS_DIR / f"{slug}.xml", display, old_items, feed)
            outputs.append({**payload, "feed": feed})
            continue

        slug = slug_for(query)
        old_items = load_old_items(slug)
        status = "ok"
        message = ""
        search_url = ""
        parsed_name = display or query
        try:
            new_items, detected_name, search_url = fetch_sogou(query)
            if not display:
                parsed_name = detected_name
            items = merge_items(new_items, old_items)
            print(f"[sync] {query}: +{len(new_items)} fetched, {len(items)} stored")
        except Exception as exc:
            status = "blocked"
            message = str(exc)
            items = old_items
            print(f"[sync] {query}: {message}", file=sys.stderr)

        payload = {
            "query": query,
            "name": parsed_name,
            "status": status,
            "message": message,
            "search_url": search_url,
            "updated_at": int(time.time()),
            "items": items,
        }
        (DATA_DIR / f"{slug}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        feed = f"{base}/rss/{slug}.xml"
        write_rss(RSS_DIR / f"{slug}.xml", parsed_name, items, feed)
        outputs.append({**payload, "feed": feed})
        for item in items:
            key = str(item.get("guid") or "")
            if key:
                all_items[key] = item

    merged_all = sorted(
        all_items.values(),
        key=lambda x: (int(x.get("publish_at") or 0), int(x.get("fetched_at") or 0)),
        reverse=True,
    )[:300]
    all_feed = f"{base}/rss/all.xml"
    write_rss(RSS_DIR / "all.xml", "微信公众号 RSS 汇总", merged_all, all_feed)
    (PUBLIC_DIR / "data.json").write_text(
        json.dumps(
            {"updated_at": int(time.time()), "all_feed": all_feed, "sources": outputs},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (PUBLIC_DIR / "index.html").write_text(render_index(outputs, all_feed), encoding="utf-8")

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## 微信公众号 RSS 同步\n\n")
            f.write("数据源：搜狗微信公开检索（不使用微信读书，不需要扫码）。\n\n")
            for src in outputs:
                f.write(f"- **{src['name']}**：`{src['status']}`，保存 {len(src['items'])} 篇\n")
            f.write(f"\n站点：{base}/\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
