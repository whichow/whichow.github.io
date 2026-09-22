#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".state"
PUBLIC_DIR = ROOT / "wechat-rss"
VENDOR_DIR = ROOT / ".vendor" / "wechrss"
STATE_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(VENDOR_DIR))

from service import AppDB, CredentialStore, SyncService  # type: ignore
from wechat_mp_fetcher import FetcherError, render_rss  # type: ignore

REQUEST_INTERVAL = max(2.0, float(os.getenv("WEREAD_MIN_INTERVAL", "5")))
RSS_LIMIT = max(10, min(int(os.getenv("RSS_LIMIT", "50")), 200))
ADD_SOURCE = os.getenv("ADD_SOURCE", "").strip()
ADD_NAME = os.getenv("ADD_NAME", "").strip()


def page_base_url() -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "whichow/whichow.github.io")
    owner, repo = repository.split("/", 1)
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/wechat-rss"
    return f"https://{owner}.github.io/{repo}/wechat-rss"


def iso_ts(ts: int) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def jsafe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: jsafe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsafe(v) for v in value]
    return value


def write_outputs(db: AppDB, statuses: dict[int, dict[str, Any]]) -> None:
    base = page_base_url()
    rss_dir = PUBLIC_DIR / "rss"
    rss_dir.mkdir(parents=True, exist_ok=True)

    sources = db.list_sources()
    all_articles = []
    data_sources: list[dict[str, Any]] = []

    for source in sources:
        articles = db.get_articles(source.book_id, limit=source.rss_limit or RSS_LIMIT)
        all_articles.extend(articles)
        feed_name = f"feed-{source.id}.xml"
        (rss_dir / feed_name).write_bytes(
            render_rss(
                articles,
                feed_title=source.name or source.book_id,
                feed_link=f"{base}/",
            )
        )
        data_sources.append(
            {
                "id": source.id,
                "name": source.name or source.book_id,
                "book_id": source.book_id,
                "article_url": source.article_url,
                "feed": f"{base}/rss/{feed_name}",
                "last_sync_at": source.last_sync_at,
                "status": statuses.get(source.id, {}).get("status", source.last_status),
                "message": statuses.get(source.id, {}).get("message", source.last_error),
                "article_count": len(articles),
                "articles": [
                    {
                        "review_id": a.review_id,
                        "title": a.title,
                        "summary": a.summary,
                        "url": a.url,
                        "cover_url": a.cover_url,
                        "publish_at": a.publish_at,
                        "author": a.author,
                    }
                    for a in articles[:30]
                ],
            }
        )

    dedup = {}
    for a in all_articles:
        dedup[a.review_id] = a
    merged = sorted(dedup.values(), key=lambda a: a.publish_at, reverse=True)[:100]
    (rss_dir / "all.xml").write_bytes(
        render_rss(merged, feed_title="微信公众号 RSS 汇总", feed_link=f"{base}/")
    )

    payload = {
        "updated_at": int(datetime.now(timezone.utc).timestamp()),
        "base_url": base,
        "all_feed": f"{base}/rss/all.xml",
        "sources": data_sources,
    }
    (PUBLIC_DIR / "data.json").write_text(
        json.dumps(jsafe(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (PUBLIC_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (PUBLIC_DIR / "index.html").write_text(render_index(payload), encoding="utf-8")


def render_index(payload: dict[str, Any]) -> str:
    updated = iso_ts(payload["updated_at"])
    source_cards = []
    recent = []
    for source in payload["sources"]:
        status = source["status"] or "never"
        status_class = "ok" if status == "ok" else ("warn" if status in {"risk_control", "auth_expired"} else "muted")
        msg = source.get("message") or ""
        source_cards.append(
            f"""<section class="card">
<div class="row"><div><h2>{html.escape(source["name"])}</h2><code>{html.escape(source["book_id"])}</code></div>
<span class="pill {status_class}">{html.escape(status)}</span></div>
<p>{source["article_count"]} 篇已保存 · <a href="{html.escape(source["feed"])}">独立 RSS</a></p>
{f'<p class="error">{html.escape(msg)}</p>' if msg else ''}
</section>"""
        )
        for article in source["articles"][:8]:
            if not article["url"]:
                continue
            recent.append((article["publish_at"], source["name"], article))
    recent.sort(key=lambda x: x[0], reverse=True)
    recent_html = "\n".join(
        f"""<article><a href="{html.escape(item["url"])}" target="_blank" rel="noreferrer">{html.escape(item["title"])}</a>
<small>{html.escape(name)} · {html.escape(iso_ts(item["publish_at"]))}</small></article>"""
        for _, name, item in recent[:40]
    )
    if not source_cards:
        source_cards.append(
            """<section class="card"><h2>还没有公众号</h2>
<p>打开 GitHub → Actions → <b>WeChat RSS Sync</b> → Run workflow，在 <code>source</code> 中粘贴任意一篇目标公众号文章链接。</p></section>"""
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信公众号 RSS</title>
<style>
:root{{color-scheme:light dark;--bg:#f7f8fa;--card:#fff;--text:#182026;--muted:#667085;--line:#e4e7ec;--accent:#12b76a}}
@media(prefers-color-scheme:dark){{:root{{--bg:#101214;--card:#171a1d;--text:#f2f4f7;--muted:#98a2b3;--line:#344054}}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.6}}
main{{max-width:900px;margin:0 auto;padding:48px 20px 90px}} a{{color:#1570ef;text-decoration:none}} a:hover{{text-decoration:underline}}
header{{margin-bottom:28px}} h1{{font-size:clamp(30px,5vw,46px);margin:0 0 8px}} h2{{margin:0;font-size:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px}}
.row{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}} code{{font-size:12px;color:var(--muted)}}
.pill{{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:3px 9px}} .pill.ok{{color:#12b76a}} .pill.warn{{color:#f79009}}
.error{{color:#d92d20;font-size:13px}} .recent{{margin-top:34px}} article{{padding:14px 0;border-bottom:1px solid var(--line)}} article a{{font-weight:650}}
article small{{display:block;color:var(--muted);margin-top:4px}} footer{{margin-top:36px;color:var(--muted);font-size:13px}}
</style>
<main>
<header><h1>微信公众号 RSS</h1><p>GitHub Actions 定时同步 · 静态 RSS · 原文阅读</p>
<p><a href="{html.escape(payload["all_feed"])}">订阅全部公众号 RSS</a></p><small>最近更新：{html.escape(updated)}</small></header>
<div class="grid">{''.join(source_cards)}</div>
<section class="recent"><h2>最近文章</h2>{recent_html or '<p>暂无文章。</p>'}</section>
<footer>仅同步标题、时间、摘要、封面与原文链接；不自动抓取正文。遇到风控/验证码会停止，不绕过平台控制。</footer>
</main></html>"""


def add_source_if_requested(db: AppDB) -> None:
    if not ADD_SOURCE:
        return
    try:
        source = db.add_source(
            source_value=ADD_SOURCE,
            name=ADD_NAME,
            interval_minutes=360,
            fetch_content=False,
            rss_limit=RSS_LIMIT,
        )
        print(f"[sync] added source #{source.id}: {source.name or source.book_id}")
    except FetcherError as exc:
        if "已存在" in str(exc):
            print(f"[sync] source already exists: {exc}")
            return
        raise


def main() -> int:
    db_path = STATE_DIR / "wechat_mp.db"
    creds_path = STATE_DIR / "credentials.json"
    if not creds_path.exists():
        print("缺少登录状态。请先运行 WeChat RSS Login 工作流。", file=sys.stderr)
        return 3

    db = AppDB(db_path)
    add_source_if_requested(db)
    creds = CredentialStore(creds_path)
    service = SyncService(
        db,
        creds,
        request_interval=REQUEST_INTERVAL,
        timeout=25,
    )

    statuses: dict[int, dict[str, Any]] = {}
    for source in db.list_sources():
        result = service.sync_source(source.id)
        statuses[source.id] = {"status": result.status, "message": result.message}
        print(
            f"[sync] {source.name or source.book_id}: "
            f"status={result.status}, received={result.received}, new={result.new_count}"
        )

    write_outputs(db, statuses)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## 微信公众号 RSS 同步\n\n")
            if not statuses:
                f.write("还没有公众号。重新运行此工作流，并在 `source` 输入一篇公众号文章链接即可添加。\n")
            for source in db.list_sources():
                st = statuses.get(source.id, {})
                f.write(f"- **{source.name or source.book_id}**：`{st.get('status', source.last_status)}`\n")
            f.write(f"\n站点：{page_base_url()}/\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
