# WeChat Article Extractor

免费开源的微信公众号单篇文章提取工具，部署在本仓库 GitHub Actions + GitHub Pages 中。

## 提取链

1. Direct HTTP parser：基于 XUMUMI/read-wechat-articles 的公开页面解析思路（MIT）。
2. Browser fallback：使用 xiguawang/wechat-reader（MIT），在 Playwright/真实 Chrome 会话中读取文章。
3. 不使用 RedFox，不要求微信读书，不自动解验证码，也不绕过微信访问控制。

GitHub Actions 云端运行时，如果微信要求“环境异常/去验证”，结果会明确标记为 blocked / captcha_required。在桌面本机运行时，可用 wechat-reader 的 auto / attach 模式复用用户已经验证过的 Chrome 会话。

## 云端使用

GitHub → Actions → WeChat Article Extract → Run workflow，输入公开的 https://mp.weixin.qq.com/... 链接。

也可以更新 requests/wechat-article-url.txt，提交后会自动运行。

完整正文只保存为 1 天的 Actions Artifact；GitHub Pages 只公开状态、标题、短摘要和诊断信息，避免把第三方全文永久重新发布到公开仓库。

## 本机使用

    python -m pip install "git+https://github.com/xiguawang/wechat-reader.git@2d590dd74b2f5ce9f2ac716a5b5571df34ea1844"
    python -m playwright install chromium

    python tools/wechat_article_extract.py \
      "https://mp.weixin.qq.com/s/..." \
      --strategy auto \
      --browser-strategy auto \
      --wait-for-manual-verify 120 \
      --out-json result.json \
      --out-md article.md

如果直接 HTTP 被拦，wechat-reader 会尝试连接/启动真实浏览器。需要微信验证时，由用户在浏览器里正常完成验证，然后再次读取。

## 来源与许可证

- XUMUMI/read-wechat-articles — MIT
- xiguawang/wechat-reader — MIT

第三方许可证说明见 tools/THIRD_PARTY_WECHAT_EXTRACTOR_LICENSES.md。
