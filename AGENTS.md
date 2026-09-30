# Repository agent instructions

Repository-local reusable workflows live under `.agents/skills/`.

When a request contains a 今日头条 / Toutiao share link, `m.toutiao.com/is/...`,
`toutiao.com/article/...`, or asks to extract/recover a Toutiao article's
正文、配图、原图或 GIF, read and follow:

`.agents/skills/toutiao-article-extractor/SKILL.md`

Do not start that workflow by treating the article as an ordinary web-search
question; the repository already contains a deployed extractor and image
fallback pipeline.

When a request contains a WeChat Official Account article URL under
`mp.weixin.qq.com`, or asks to extract/read a 微信公众号文章, read and follow:

`.agents/skills/wechat-article-extractor/SKILL.md`

The deployed WeChat extractor is free/open-source first and does not depend on
RedFox. It may report normal WeChat verification/rate-limit states instead of
attempting to bypass them.
