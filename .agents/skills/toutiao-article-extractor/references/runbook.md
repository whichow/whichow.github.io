# Toutiao extractor deployed runbook

## Deployed implementation

Repository: `whichow/whichow.github.io`

Working branch: `toutiao-article-extract-h3-66s`

Primary files:

- `.github/toutiao-extract/request.json` — the only file that normally needs to change per article.
- `.github/workflows/toutiao-article-extract-h3-66s.yml` — GitHub Actions workflow.
- `tools/toutiao_article_extract.py` — resolves short links, parses Toutiao SSR/RENDER_DATA, extracts text, source URL and direct images, checks legacy detail APIs, and can use RedFox.
- `tools/toutiao_mirror_extract.py` — mirror fallback; supports normal article DOMs and Next.js `__NEXT_DATA__`; can download all images and create `article_images.zip`.
- `extracted/toutiao-h3-66s/result.json` — latest persisted primary metadata.
- `extracted/toutiao-h3-66s/mirror_images.json` — latest persisted mirror metadata when a mirror was used.

The workflow artifact contains the complete `output/` directory and is retained for 3 days.

## Normal request format

Update `.github/toutiao-extract/request.json` on branch
`toutiao-article-extract-h3-66s`:

```json
{
  "url": "https://m.toutiao.com/is/SHORT_ID/",
  "mirror_url": "",
  "skip_redfox": false,
  "download_images": true,
  "note": "First run: leave mirror_url empty."
}
```

A commit touching that file triggers the Action automatically.

For a new article, always clear a previous article's `mirror_url`; never reuse
a mirror across titles.

## Primary extraction decision tree

1. Resolve the short URL to the canonical article ID.
2. Fetch desktop and mobile article pages.
3. Parse DOM and `RENDER_DATA`.
4. Extract title, author, paragraphs, image URLs, and original-source URL.
5. Query legacy Toutiao detail APIs:
   - `https://m.toutiao.com/i<ARTICLE_ID>/info/`
   - `https://m.toutiao.com/pwa/api/wxapp/info/<ARTICLE_ID>/`
6. If the Toutiao article exposes a public WeChat source URL, try it.
7. If the public WeChat page is CAPTCHA-protected and RedFox is enabled, query
   the configured RedFox article database.
8. Persist `result.json` and `article.md`.

Interpret `image_count: 0` as "no image URL recovered from the primary
pipeline", not as proof that the article has no images.

## Image fallback when image_count == 0

Use the extracted exact title and author/source.

Search the public web for the **exact title**, preferably combined with the
source name. A mirror is acceptable only when all practical signals match:

- same or essentially identical title;
- same source/author when available;
- same paragraph ordering/content;
- publication timing is plausible.

Do not fill gaps with visually similar or topic-similar web images.

Once an exact-content mirror is found, update only:

```json
{
  "mirror_url": "https://exact-mirror.example/article/...",
  "skip_redfox": true
}
```

Keep the same `url`. Commit `request.json` again.

The mirror extractor:

- checks ordinary article DOMs;
- checks Next.js `__NEXT_DATA__`;
- selects embedded HTML with the strongest inline-image signal;
- preserves image order;
- attempts the underlying asset without resize/tracking query first;
- falls back to the exact mirror URL when the origin requires signatures;
- preserves GIF files rather than converting them to stills;
- writes `mirror_images.json`;
- downloads files into `output/images/`;
- creates `output/article_images.zip`.

## Verification checklist

Before telling the user that images were extracted:

1. Confirm the Action step completed successfully.
2. Check `result.json.image_count` and/or
   `mirror_images.json.downloaded_count`.
3. Confirm the artifact actually contains image files, not only image URLs.
4. Preserve source order by numeric names such as `01.png`, `02.jpg`, etc.
5. Keep GIFs animated.
6. If a CDN filename extension disagrees with Content-Type, prefer the actual
   Content-Type when packaging.
7. Do not claim "all images" if any download failed.
8. When returning files from ChatGPT, provide clickable `sandbox:/mnt/data/...`
   links rather than bare `/mnt/data/...` paths.

## Known 2026-09-26 test case

Toutiao short link:
`https://m.toutiao.com/is/8EuPXqpA--8/`

Canonical article ID:
`7689650567643152930`

Title:
`新时代「擦边三件套」，盯上缺钱的女孩`

Source:
`凤凰WEEKLY`

Observed behavior:

- Toutiao `RENDER_DATA` contained the full text but stripped inline `<img>`
  nodes.
- It exposed the original WeChat source URL.
- GitHub Runner access to the WeChat URL was redirected to a CAPTCHA page.
- RedFox had the account but had not yet indexed that same-day article.
- Toutiao legacy detail APIs returned JSON but did not expose usable image URLs.
- An exact-content Yeeyi mirror stored the full article HTML inside
  `__NEXT_DATA__.props.pageProps.newsDetail.newsInfo.content`.
- The mirror contained 22 inline images.
- 22/22 were downloaded: 19 static images and 3 animated GIFs.

This case is the reason the skill must not stop at the first `image_count=0`.
