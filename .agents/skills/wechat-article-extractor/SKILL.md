---
name: wechat-article-extractor
description: Extract a public WeChat Official Account article from an mp.weixin.qq.com link using the repository's free/open-source pipeline.
---

# WeChat Article Extractor

Use this skill when the user provides an mp.weixin.qq.com article URL or asks to extract/read a WeChat Official Account article.

## Repository pipeline

- Entry script: tools/wechat_article_extract.py
- Cloud workflow: .github/workflows/wechat-article-extract.yml
- Chat-trigger request file: requests/wechat-article-url.txt
- Public status page: wechat-extract/index.html
- Latest safe metadata: wechat-extract/latest.json

The extractor does not use RedFox. It tries:
1. Direct public HTTP parsing.
2. xiguawang/wechat-reader browser extraction.

Do not bypass CAPTCHAs or access controls. If WeChat requires verification, report that state. On a user-controlled desktop, prefer wechat-reader attach/auto mode so the user can complete normal verification in Chrome.

## When operating through GitHub

1. Write the exact article URL, and only that URL plus a newline, to requests/wechat-article-url.txt.
2. Wait for the WeChat Article Extract workflow triggered by that commit.
3. Inspect the workflow result.
4. Use the workflow artifact for the full extracted JSON/Markdown. The Pages metadata intentionally contains only a short excerpt.
5. Summarize or analyze the article for the user; do not reproduce long copyrighted text verbatim.

## Local command

    python tools/wechat_article_extract.py "https://mp.weixin.qq.com/s/..." \
      --strategy auto \
      --browser-strategy auto \
      --wait-for-manual-verify 120 \
      --out-json result.json \
      --out-md article.md
