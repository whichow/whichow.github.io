# GitHub Actions 微信公众号 RSS（免扫码版）

当前方案**不使用微信读书、不需要微信扫码、不保存微信登录态**。

数据源为搜狗微信公开检索页面。GitHub Actions 每 6 小时运行一次，整理公开搜索结果中的：

- 标题
- 摘要
- 发布时间
- 公众号名称
- 微信原文链接（能从公开跳转解析到时）或搜狗公开跳转链接

生成：

- `wechat-rss/index.html`：静态文章列表
- `wechat-rss/rss/all.xml`：全部公众号汇总 RSS
- `wechat-rss/rss/<id>.xml`：单公众号 RSS
- `wechat-rss/data/<id>.json`：历史元数据缓存

## 添加公众号

GitHub → Actions → **WeChat RSS Sync** → **Run workflow**。

在 `source` 输入公众号**准确名称或微信号**，例如某公众号的微信号；`name` 可选。

运行成功后，该订阅会写入 `wechat-rss/sources.json`，以后无需人工操作。

## 限制

搜狗微信存在反爬与验证码，因此这种完全免登录方案的稳定性不可能等同于有授权/商业数据接口的方案。脚本检测到验证码或限制页时会停止该源本轮同步并保留旧数据，**不会绕过验证码、轮换代理或规避访问控制**。

如果后续需要更稳定但仍然不扫码，可以再接 RedFoxHub 一类 API 数据源；那种方案只需要 API Key，不需要微信读书或微信登录。
