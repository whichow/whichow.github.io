# GitHub Actions 微信公众号 RSS

这个目录把 `johamwon/wechrss` 的核心同步能力改造成 GitHub Actions 任务：

- `WeChat RSS Login`：手动/首次扫码登录微信读书，凭证只保存在 GitHub Actions Artifact，不提交到仓库。
- `WeChat RSS Sync`：每 6 小时同步一次；也可以手动运行并在 `source` 输入一篇公众号文章链接来添加新公众号。
- 公共输出目录：`/wechat-rss/`
  - `index.html`：静态文章列表
  - `rss/all.xml`：全部公众号汇总 RSS
  - `rss/feed-<id>.xml`：单公众号 RSS
  - `data.json`：公开元数据

## 安全设计

`credentials.json` 与 SQLite 状态库仅存在于 Actions Artifact 中。公开仓库只保存生成后的标题、时间、摘要、封面、原文链接与 RSS；不会自动抓取正文。

如果微信读书返回风控、验证码或登录失效，任务会停止/标记状态，不会尝试绕过平台控制。

## 上游

核心逻辑固定到 `johamwon/wechrss` commit：

`a99675f7ef1f3d457991d441a9124d3f6666bd45`

上游项目采用 MIT License。
