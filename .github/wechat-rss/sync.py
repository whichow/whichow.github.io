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

    if account_name or title:
        return account_name, title

    # Public permanent links can return a JS shell to plain HTTP clients.
    # Render once in a normal headless browser. We do not solve CAPTCHAs,
    # inject login state, rotate proxies, or bypass any verification page.
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("公开页面只返回了脚本壳，且 Playwright 未安装") from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN")
                page = context.new_page()
                response2 = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=REQUEST_TIMEOUT * 1000,
                )
                if response2 and response2.status >= 400:
                    raise RuntimeError(f"微信文章页面返回 HTTP {response2.status}")
                page.wait_for_timeout(1500)
                body_text = page.locator("body").inner_text(timeout=5000)
                if any(marker.lower() in body_text.lower() for marker in BLOCK_MARKERS):
                    raise RuntimeError("微信文章公开页要求验证码或限制访问，未尝试绕过")
                values = page.evaluate(
                    """() => ({
                      account:
                        document.querySelector('#js_name')?.textContent?.trim() ||
                        document.querySelector('.rich_media_meta_nickname')?.textContent?.trim() ||
                        document.querySelector('#js_wx_follow_nickname')?.textContent?.trim() ||
                        (window.nickname || ''),
                      title:
                        document.querySelector('#activity-name')?.textContent?.trim() ||
                        document.querySelector('h1.rich_media_title')?.textContent?.trim() ||
                        document.querySelector('meta[property="og:title"]')?.content ||
                        document.title || ''
                    })"""
                )
            finally:
                browser.close()
        if isinstance(values, dict):
            account_name = str(values.get("account") or "").strip()
            title = str(values.get("title") or "").strip()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"浏览器打开公开微信文章失败: {exc}") from exc

    if not account_name and not title:
        raise RuntimeError("已打开微信文章，但公开页面仍未解析到公众号名称或文章标题")
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
        if article_title:
            source["seed_title"] = article_title

        # Some current WeChat permanent-link pages expose the article title but
        # no account nickname in the static HTML. In that case use the public
        # Sogou article search once to recover the author/account name, then
        # persist that account name for all future scheduled syncs.
        if not account_name and article_title:
            seed_items, detected_name, _ = fetch_sogou(article_title)
            exact = next(
                (
                    item for item in seed_items
                    if str(item.get("title") or "").strip() == article_title.strip()
                    and str(item.get("author") or "").strip()
                ),
                None,
            )
            account_name = (
                str(exact.get("author") or "").strip()
                if exact
                else str(detected_name or "").strip()
            )

        if not account_name:
            raise RuntimeError("能打开文章，但无法从公开页面或搜狗公开检索识别公众号名称")

        query = account_name
        source["query"] = query
        source["resolved_from"] = seed_url
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


def _norm_author(value: str) -> str:
    return re.sub(r"\s+", "", (value or "")).casefold()


def _normalize_wechat_url(value: str) -> str:
    value = html.unescape(str(value or "")).strip()
    value = value.replace(r"\/","/").replace(r"\x26","&").replace(r"\u0026","&")
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("/"):
        return "https://mp.weixin.qq.com" + value
    return value


def fetch_profile_history(
    session: requests.Session,
    profile_url: str,
    account_name: str,
) -> list[dict]:
    if not profile_url:
        return []
    url = urljoin(SOGOU_HOST, profile_url)
    try:
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={"Referer": SOGOU_SEARCH},
        )
        response.raise_for_status()
    except requests.RequestException:
        return []

    text = response.text
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in BLOCK_MARKERS):
        return []

    # Sogou's public-account history page embeds the recent message list in
    # `var msgList = {...};`. This is public page data; no login state or
    # CAPTCHA handling is used.
    match = re.search(r"var\s+msgList\s*=\s*(.*?)\}\}\]\};", text, flags=re.S)
    if not match:
        return []
    raw = match.group(1) + "}}]}"
    try:
        payload = json.loads(raw)
    except Exception:
        return []

    result: list[dict] = []
    for group in payload.get("list") or []:
        if not isinstance(group, dict):
            continue
        comm = group.get("comm_msg_info") if isinstance(group.get("comm_msg_info"), dict) else {}
        ext = group.get("app_msg_ext_info") if isinstance(group.get("app_msg_ext_info"), dict) else {}
        publish_at = int(comm.get("datetime") or 0)

        candidates = [ext]
        multi = ext.get("multi_app_msg_item_list")
        if isinstance(multi, list):
            candidates.extend(x for x in multi if isinstance(x, dict))

        for article in candidates:
            title = str(article.get("title") or "").strip()
            link = _normalize_wechat_url(article.get("content_url") or "")
            if not title or not link:
                continue
            cover = _normalize_wechat_url(article.get("cover") or "")
            result.append(
                {
                    "guid": link,
                    "title": title,
                    "description": str(article.get("digest") or "").strip(),
                    "author": account_name,
                    "publish_at": publish_at,
                    "url": link,
                    "sogou_url": url,
                    "cover_url": cover,
                    "fetched_at": int(time.time()),
                }
            )

    result.sort(key=lambda x: int(x.get("publish_at") or 0), reverse=True)
    return result


REDFOX_BASE = os.getenv("REDFOX_BASE_URL", "https://redfox.hk").rstrip("/")
REDFOX_API_KEY = os.getenv("REDFOX_API_KEY", "").strip()


def _parse_redfox_time(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    if text.isdigit():
        n = int(text)
        return n // 1000 if n > 10_000_000_000 else n
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    return 0


def _redfox_post(path: str, payload: dict) -> dict:
    if not REDFOX_API_KEY:
        raise RuntimeError("REDFOX_API_KEY 未配置")
    response = requests.post(
        REDFOX_BASE + path,
        json=payload,
        timeout=REQUEST_TIMEOUT,
        headers={
            "REDFOX_API_KEY": REDFOX_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("RedFox 返回格式异常")
    code = int(data.get("code") or 0)
    if code not in (200, 2000):
        raise RuntimeError(str(data.get("msg") or data.get("message") or f"RedFox code={code}"))
    payload_data = data.get("data")
    return payload_data if isinstance(payload_data, dict) else {}


def _redfox_match_account(query: str, source: dict) -> dict:
    cached = source.get("redfox") if isinstance(source.get("redfox"), dict) else {}
    if cached and any(cached.get(k) for k in ("wxId", "bizInfo", "account")):
        return cached

    search = _redfox_post(
        "/story/api/gzh/data/searchUser",
        {"keyword": query, "offset": 0},
    )
    rows = search.get("list") or []
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("RedFox 没有搜索到这个公众号")

    qn = _norm_author(query)

    def score(row: dict) -> tuple[int, int]:
        account_name = _norm_author(str(row.get("accountName") or ""))
        account = _norm_author(str(row.get("account") or ""))
        wx_id = _norm_author(str(row.get("wxId") or ""))
        exact = int(account_name == qn or account == qn or wx_id == qn)
        starts = int(account_name.startswith(qn) or account.startswith(qn))
        return (exact, starts)

    candidates = [row for row in rows if isinstance(row, dict)]
    candidates.sort(key=score, reverse=True)
    best = candidates[0]
    if score(best)[0] == 0 and len(candidates) > 1:
        # For a nickname-like query, do not silently bind to a loosely related account.
        raise RuntimeError("RedFox 搜索到了多个相近公众号，但没有精确匹配")

    record = {
        "account": str(best.get("account") or "").strip(),
        "accountName": str(best.get("accountName") or "").strip(),
        "wxId": str(best.get("wxId") or "").strip(),
        "bizInfo": str(best.get("bizInfo") or "").strip(),
    }
    source["redfox"] = record
    if record["accountName"] and not str(source.get("name") or "").strip():
        source["name"] = record["accountName"]
    return record


def fetch_redfox(query: str, source: dict) -> tuple[list[dict], str, str]:
    account = _redfox_match_account(query, source)
    request_payload: dict = {"offset": 0, "sortType": "2"}
    if account.get("wxId"):
        request_payload["wxId"] = account["wxId"]
    elif account.get("bizInfo"):
        request_payload["bizInfo"] = account["bizInfo"]
    elif account.get("account"):
        request_payload["account"] = account["account"]
    else:
        raise RuntimeError("RedFox 账号信息缺少可查询标识")

    data = _redfox_post("/story/api/gzh/data/queryWorkList", request_payload)
    rows = data.get("list") or []
    if not isinstance(rows, list):
        rows = []

    items: list[dict] = []
    display_name = str(account.get("accountName") or query).strip()
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        url = str(row.get("workUrl") or "").strip()
        if not title:
            continue
        work_uuid = str(row.get("workUuid") or "").strip()
        guid = work_uuid or url or hashlib.sha1(
            (title + "|" + str(row.get("publishTime") or "")).encode("utf-8")
        ).hexdigest()
        items.append(
            {
                "guid": guid,
                "title": title,
                "description": str(row.get("summary") or "").strip(),
                "author": str(row.get("author") or display_name).strip(),
                "publish_at": _parse_redfox_time(row.get("publishTime")),
                "url": url,
                "cover_url": str(row.get("coverUrl") or "").strip(),
                "read_count": row.get("readCount"),
                "like_count": row.get("likeCount"),
                "fetched_at": int(time.time()),
                "source": "redfox",
            }
        )

    if not items:
        raise RuntimeError("RedFox 没有返回公众号文章")
    items.sort(key=lambda x: int(x.get("publish_at") or 0), reverse=True)
    return items, display_name, REDFOX_BASE


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
        author_anchor = author_node.find_parent("a") if author_node else None
        profile_url = str(author_anchor.get("href") or "").strip() if author_anchor else ""
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
                "profile_url": profile_url,
                "fetched_at": int(time.time()),
            }
        )

    if not items:
        raise RuntimeError("搜狗微信页面已返回，但没有解析到有效文章")

    # A keyword search can include other accounts merely mentioning the query.
    # When at least one exact author match exists, use the account's own result
    # and, when available, expand its public history page into recent posts.
    expected = _norm_author(query)
    exact_items = [
        item for item in items
        if _norm_author(str(item.get("author") or "")) == expected
    ]
    if exact_items:
        profile_url = next(
            (str(item.get("profile_url") or "") for item in exact_items if item.get("profile_url")),
            "",
        )
        history = fetch_profile_history(session, profile_url, exact_items[0]["author"])
        if history:
            return history, exact_items[0]["author"], response.url
        return exact_items, exact_items[0]["author"], response.url

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


def merge_items(
    new_items: list[dict],
    old_items: list[dict],
    expected_author: str = "",
) -> list[dict]:
    if expected_author:
        expected = _norm_author(expected_author)
        exact_new = [
            item for item in new_items
            if _norm_author(str(item.get("author") or "")) == expected
        ]
        if exact_new:
            new_items = exact_new
            old_items = [
                item for item in old_items
                if _norm_author(str(item.get("author") or "")) == expected
            ]

    merged: dict[str, dict] = {}
    for item in old_items + new_items:
        title = str(item.get("title") or "").strip()
        author = str(item.get("author") or "").strip()
        publish_at = int(item.get("publish_at") or 0)
        # Sogou redirect URLs contain short-lived tokens, so they are not stable
        # identifiers across runs. Prefer semantic identity for de-duplication.
        if title and publish_at:
            key = hashlib.sha1(
                f"{_norm_author(author)}|{title}|{publish_at}".encode("utf-8")
            ).hexdigest()
        else:
            key = str(item.get("guid") or "").strip()
            if not key:
                key = hashlib.sha1(
                    (title + "|" + str(publish_at)).encode("utf-8")
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
<p>GitHub Actions · RedFox 优先 / 搜狗公开检索兜底 · 无微信读书 · 无扫码 · 无微信登录态</p>
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
            if REDFOX_API_KEY:
                try:
                    new_items, detected_name, search_url = fetch_redfox(query, source)
                    source["last_backend"] = "redfox"
                    save_sources(sources)
                except Exception as redfox_exc:
                    print(f"[redfox] {query}: {redfox_exc}; fallback to Sogou", file=sys.stderr)
                    new_items, detected_name, search_url = fetch_sogou(query)
                    source["last_backend"] = "sogou-fallback"
                    source["last_redfox_error"] = str(redfox_exc)
                    save_sources(sources)
            else:
                new_items, detected_name, search_url = fetch_sogou(query)
                source["last_backend"] = "sogou"
                save_sources(sources)

            if not display:
                parsed_name = detected_name
            items = merge_items(new_items, old_items, expected_author=query)
            print(
                f"[sync] {query}: backend={source.get('last_backend')}, "
                f"+{len(new_items)} fetched, {len(items)} stored"
            )
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
