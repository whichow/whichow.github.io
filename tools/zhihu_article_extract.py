#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html as html_lib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from markdownify import markdownify as to_markdown
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/117.0.0.0 Safari/537.36"
)
ARTICLE_RE = re.compile(r"^/p/(\d{5,32})/?$")


def parse_article_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    if parsed.hostname != "zhuanlan.zhihu.com":
        raise ValueError("Only zhuanlan.zhihu.com article URLs are supported")
    match = ARTICLE_RE.match(parsed.path)
    if not match:
        raise ValueError("Expected a Zhihu article URL like https://zhuanlan.zhihu.com/p/123")
    article_id = match.group(1)
    return article_id, f"https://zhuanlan.zhihu.com/p/{article_id}"


async def extract(url: str, out_dir: Path) -> dict:
    article_id, canonical = parse_article_url(url)
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "source_url": url,
        "canonical_url": canonical,
        "article_id": article_id,
        "extractor": "playwright-stealth / ZhiArchive-compatible DOM strategy",
        "success": False,
    }

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            locale="zh-CN",
            user_agent=UA,
            viewport={"width": 1440, "height": 1200},
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.zhihu.com/",
            },
        )
        page = await context.new_page()
        try:
            response = await page.goto(
                canonical,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            result["http_status"] = response.status if response else None
            await page.wait_for_timeout(5_000)
            result["final_url"] = page.url
            result["page_title"] = await page.title()

            page_html = await page.content()
            (out_dir / "page.html").write_text(page_html, encoding="utf-8")
            await page.screenshot(path=out_dir / "screenshot.png", full_page=False)

            title = ""
            try:
                title = (
                    await page.locator('meta[property="og:title"]').get_attribute("content")
                    or ""
                )
            except Exception:
                pass
            title = title.removesuffix(" - 知乎").strip() or result["page_title"].removesuffix(" - 知乎").strip()

            author = ""
            author_url = ""
            author_locator = page.locator(
                "div.Post-Author a.UserLink-link, div.AuthorInfo a.UserLink-link"
            ).first
            try:
                author_url = await author_locator.get_attribute("href", timeout=1500) or ""
                author = (await author_locator.inner_text(timeout=1500)).strip()
            except Exception:
                pass

            root = page.locator("article.Post-Main, .Post-Main").first
            content_text = ""
            content_html = ""
            extraction_method = ""

            if await root.count():
                rich = root.locator(".RichText.ztext").first
                node = rich if await rich.count() else root
                content_text = (await node.inner_text()).strip()
                content_html = (await node.inner_html()).strip()
                extraction_method = "rendered_dom"

            if not content_text:
                initial = page.locator("#js-initialData").first
                if await initial.count():
                    raw = await initial.text_content() or ""
                    try:
                        payload = json.loads(html_lib.unescape(raw))
                        article = (
                            payload.get("initialState", {})
                            .get("entities", {})
                            .get("articles", {})
                            .get(article_id)
                        )
                    except Exception:
                        article = None
                    if isinstance(article, dict):
                        content_html = str(article.get("content") or "")
                        if content_html:
                            content_text = await page.evaluate(
                                """
                                (markup) => {
                                  const node = document.createElement("div");
                                  node.innerHTML = markup;
                                  node.querySelectorAll("script,style,noscript").forEach(x => x.remove());
                                  return (node.innerText || node.textContent || "").trim();
                                }
                                """,
                                content_html,
                            )
                            title = str(article.get("title") or title).strip()
                            raw_author = article.get("author")
                            if isinstance(raw_author, dict):
                                author = str(raw_author.get("name") or author).strip()
                                author_url = str(raw_author.get("url") or author_url).strip()
                            extraction_method = "js_initial_data"

            result.update(
                {
                    "title": title,
                    "author": author,
                    "author_url": author_url,
                    "extraction_method": extraction_method,
                    "text_length": len(content_text),
                    "html_length": len(content_html),
                }
            )

            body_preview = ""
            try:
                body_preview = (await page.locator("body").inner_text())[:3000]
            except Exception:
                pass
            result["body_preview"] = body_preview

            if content_text:
                result["success"] = True
                (out_dir / "content.txt").write_text(content_text, encoding="utf-8")
                (out_dir / "content.html").write_text(content_html, encoding="utf-8")
                markdown_body = to_markdown(content_html, heading_style="ATX").strip()
                header = f"# {title}\n\n"
                if author:
                    header += f"作者：{author}\n\n"
                header += f"来源：{canonical}\n\n"
                (out_dir / "result.md").write_text(
                    header + (markdown_body or content_text) + "\n",
                    encoding="utf-8",
                )
            else:
                result["error"] = "Zhihu article content root and hydration content were not found."
        finally:
            await context.close()
            await browser.close()

    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Extract a public Zhihu Zhuanlan article with Chromium.")
    parser.add_argument("url", help="Zhihu Zhuanlan article URL")
    parser.add_argument("--out", default="output", help="Output directory")
    args = parser.parse_args()

    result = await extract(args.url, Path(args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("success"):
        print(f"Extracted: {result.get('title', '')} ({result.get('text_length', 0)} chars)")
        return 0
    return 2


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
