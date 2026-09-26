---
name: toutiao-article-extractor
description: Extract the exact article text and all inline images/GIFs from 今日头条 / Toutiao share links, including m.toutiao.com/is short links and toutiao.com/article URLs. Use whenever the user sends a Toutiao share message/link or asks to提取、恢复、下载头条文章正文、配图、原图、动图/GIF. Prefer the already-deployed GitHub extractor before generic web browsing, and continue through the documented mirror fallback when the primary result says image_count=0.
license: MIT
compatibility: Requires access to the GitHub repository whichow/whichow.github.io or an equivalent checkout of its toutiao-article-extract-h3-66s branch.
metadata:
  author: whichow
  version: "1.0.0"
  category: web-extraction
---

# Toutiao article extractor

Use the existing deployed extractor. Do not rebuild the workflow from scratch
and do not treat a Toutiao share link as an ordinary search/summarization task.

Read [references/runbook.md](references/runbook.md) for exact deployed paths,
fallbacks, and verification rules.

## Trigger

Activate for any of the following:

- a copied 今日头条 / 头条极速版 share message;
- a URL containing `m.toutiao.com/is/`;
- a URL containing `toutiao.com/article/`;
- a Toutiao article ID plus a request for the article;
- requests such as “把里面图片提取出来”, “提取原图”, “正文和图片都要”,
  “GIF 也保留”, or “之前部署的头条提取”.

## Required workflow

1. Go first to repository `whichow/whichow.github.io`, branch
   `toutiao-article-extract-h3-66s`.
2. For a new article, update
   `.github/toutiao-extract/request.json`:
   - set `url` to the user's exact Toutiao URL;
   - set `mirror_url` to an empty string on the first run;
   - normally set `skip_redfox` to `false`;
   - keep `download_images` true when the user wants images.
3. Commit that file. Its commit is the normal trigger for the existing GitHub
   Action; do not edit the workflow just to change the article URL.
4. Track the Action associated with that request and read:
   - `extracted/toutiao-h3-66s/result.json`;
   - `extracted/toutiao-h3-66s/article.md`;
   - the workflow artifact when file bytes are needed.
5. If primary `image_count > 0`, verify the artifact contains those files
   before reporting success.
6. If primary `image_count == 0`, **do not conclude that the article has no
   images**. Follow the image fallback in the runbook:
   - inspect the exact title, source, source URL and errors;
   - search for an exact-title/same-source public mirror;
   - verify that its text matches this article;
   - put only that verified mirror into `request.json.mirror_url`;
   - set `skip_redfox` true when RedFox is known stale for this same article;
   - commit `request.json` again and use the mirror extractor output.
7. Use `mirror_images.json.downloaded_count` plus the actual artifact contents
   to verify the final count. Preserve order and preserve animated GIFs.
8. When delivering generated/downloaded files from ChatGPT, give clickable
   `sandbox:/mnt/data/...` links. Never give the user only an inaccessible
   local `/mnt/data/...` path.

## Non-negotiable rules

- Never fabricate a missing image or substitute a merely similar web image.
- Do not say “all images extracted” until image bytes have actually downloaded.
- Do not use search-result thumbnails as article images.
- Do not ask the user for screenshots until the deployed primary and mirror
  fallbacks have genuinely been exhausted.
- A source page redirected to CAPTCHA means “source blocked from this runner”,
  not “article has no images”.
- If a mirror is used, tell the user that image bytes came from a verified
  exact-content mirror while the article identity came from the Toutiao
  extraction.
- If some images fail, report the successful/failed counts explicitly instead
  of silently dropping failures.

## Expected successful output

Return, as appropriate:

- exact article title/source/article ID;
- extracted text or a concise summary when requested;
- image count;
- static-image/GIF breakdown when known;
- a packaged ZIP containing images in article order;
- an optional contact sheet for static preview;
- concise provenance when a fallback mirror was necessary.
