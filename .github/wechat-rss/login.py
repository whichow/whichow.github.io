#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".state"
PUBLIC_DIR = ROOT / "wechat-rss"
VENDOR_DIR = ROOT / ".vendor" / "wechrss"
STATE_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(VENDOR_DIR))

from service import AppDB, CredentialStore  # type: ignore
from weread_auth import (  # type: ignore
    QRDeclinedError,
    QRExpiredError,
    WeReadAuthClient,
)

ATTEMPTS = max(1, int(os.getenv("LOGIN_QR_ATTEMPTS", "6")))
POLL_WINDOW = max(120, int(os.getenv("LOGIN_QR_WINDOW", "230")))


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=check, text=True, capture_output=False)


def git_publish(message: str) -> None:
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "add", "wechat-rss")
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=ROOT, text=True
    )
    if diff.returncode == 0:
        return
    run("git", "commit", "-m", message)
    for attempt in range(3):
        push = subprocess.run(["git", "push"], cwd=ROOT, text=True)
        if push.returncode == 0:
            return
        if attempt == 2:
            raise RuntimeError("无法把临时登录二维码推送到仓库")
        run("git", "pull", "--rebase")
        time.sleep(2)


def public_urls() -> tuple[str, str]:
    repository = os.getenv("GITHUB_REPOSITORY", "whichow/whichow.github.io")
    owner, repo = repository.split("/", 1)
    branch = os.getenv("GITHUB_REF_NAME", "master")
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/wechat-rss/login.png"
    if repo.lower() == f"{owner.lower()}.github.io":
        page = f"https://{owner}.github.io/wechat-rss/login.html"
    else:
        page = f"https://{owner}.github.io/{repo}/wechat-rss/login.html"
    return raw, page


def write_login_page(data_uri: str, attempt: int) -> None:
    prefix = "data:image/png;base64,"
    if not data_uri.startswith(prefix):
        raise RuntimeError("二维码格式异常")
    (PUBLIC_DIR / "login.png").write_bytes(base64.b64decode(data_uri[len(prefix):]))
    raw, page = public_urls()
    html = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信公众号 RSS 登录</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:680px;margin:48px auto;padding:0 20px;line-height:1.7;color:#182026}}
.card{{border:1px solid #ddd;border-radius:18px;padding:28px;text-align:center;box-shadow:0 8px 30px #0000000a}}
img{{width:min(360px,88vw);height:auto;image-rendering:auto}}
small{{color:#667085}} code{{word-break:break-all}}
</style>
<div class="card">
<h1>微信读书扫码登录</h1>
<p>这是 GitHub Actions 生成的临时二维码（第 {attempt}/{ATTEMPTS} 轮）。</p>
<img src="./login.png?v={int(time.time())}" alt="微信登录二维码">
<p>使用微信扫码并在手机上确认。二维码过期时页面会自动换成新二维码。</p>
<small>凭证不会提交到 Git 仓库，只会保存在 GitHub Actions 的私有构建 Artifact 中。</small>
</div>
<script>setTimeout(()=>location.reload(),15000)</script>
<!-- raw: {raw} page: {page} -->
"""
    (PUBLIC_DIR / "login.html").write_text(html, encoding="utf-8")
    git_publish("chore: publish temporary WeChat login QR [skip ci]")


def cleanup_login(success: bool, message: str = "") -> None:
    for name in ("login.png", "login.html"):
        p = PUBLIC_DIR / name
        if p.exists():
            p.unlink()
    index = PUBLIC_DIR / "index.html"
    if success and not index.exists():
        index.write_text(
            """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>微信公众号 RSS</title><style>body{font-family:system-ui;max-width:760px;margin:60px auto;padding:0 20px;line-height:1.8}</style>
<h1>微信公众号 RSS</h1><p>微信读书登录已经完成。</p>
<p>下一步运行 <b>WeChat RSS Sync</b> 工作流，在 <code>source</code> 中粘贴任意一篇目标公众号文章链接，即可添加并生成 RSS。</p>""",
            encoding="utf-8",
        )
    if not success:
        (PUBLIC_DIR / "login-expired.html").write_text(
            f"<!doctype html><meta charset='utf-8'><h1>登录未完成</h1><p>{message}</p><p>重新运行 WeChat RSS Login 工作流即可。</p>",
            encoding="utf-8",
        )
    git_publish("chore: finish WeChat login session [skip ci]")


def append_summary(text: str) -> None:
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main() -> int:
    auth = WeReadAuthClient(timeout=25)
    raw_url, page_url = public_urls()
    append_summary(
        "## 微信扫码登录\n\n"
        f"- 页面：{page_url}\n"
        f"- 原始二维码：{raw_url}\n\n"
        "工作流会等待扫码，并在二维码过期后自动刷新。"
    )

    last_error = "二维码未确认"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            qr = auth.request_qr()
            write_login_page(qr.qr_data_uri, attempt)
            print(f"[login] QR ready: {page_url}")
            print(f"[login] raw QR:  {raw_url}")
            deadline = time.time() + POLL_WINDOW
            last_code: int | None = None

            while time.time() < deadline:
                try:
                    poll = auth.poll_qr_once(qr.uuid, last=last_code, timeout=20)
                except QRExpiredError:
                    last_error = "二维码已过期"
                    break
                last_code = poll.errcode
                if poll.status == "waiting":
                    continue
                if poll.status == "scanned":
                    print("[login] QR scanned, waiting for confirmation...")
                    continue
                if poll.status == "confirmed":
                    print("[login] confirmed, exchanging WeRead session...")
                    credentials = auth.exchange_qr(poll.wx_code)
                    init = auth.initialize_feature(credentials)
                    if init.guest_token:
                        credentials.guestToken = init.guest_token
                    if init.sync_key:
                        credentials.syncKey = init.sync_key

                    store = CredentialStore(STATE_DIR / "credentials.json")
                    store.save_record(credentials)
                    AppDB(STATE_DIR / "wechat_mp.db")
                    cleanup_login(True)
                    append_summary(
                        f"\n✅ 登录成功：`{credentials.name or credentials.vid}`。\n"
                        "现在运行 **WeChat RSS Sync**，粘贴一篇公众号文章链接即可。"
                    )
                    print("[login] success")
                    return 0

            last_error = "本轮二维码等待超时"
        except QRDeclinedError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
            print(f"[login] attempt {attempt} failed: {exc}", file=sys.stderr)

        if attempt < ATTEMPTS:
            print("[login] generating a fresh QR...")
            time.sleep(2)

    cleanup_login(False, last_error)
    append_summary(f"\n❌ 登录未完成：{last_error}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
