# Repository agent instructions

Repository-local reusable workflows live under `.agents/skills/`.

When a request contains a 今日头条 / Toutiao share link, `m.toutiao.com/is/...`,
`toutiao.com/article/...`, or asks to extract/recover a Toutiao article's
正文、配图、原图或 GIF, read and follow:

`.agents/skills/toutiao-article-extractor/SKILL.md`

Do not start that workflow by treating the article as an ordinary web-search
question; the repository already contains a deployed extractor and image
fallback pipeline.
