#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, os, re, time, html
from pathlib import Path
from urllib.parse import urlparse
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"

NOTE_ID_RES = [
    re.compile(r"/explore/([0-9a-fA-F]{16,32})"),
    re.compile(r"/discovery/item/([0-9a-fA-F]{16,32})"),
    re.compile(r"noteId[\"'=:\s]+([0-9a-fA-F]{16,32})", re.I),
]

def resolve(url, out: Path):
    r = requests.get(url, headers={"User-Agent":UA}, allow_redirects=True, timeout=30)
    chain = [{"status":x.status_code,"url":x.url,"location":x.headers.get("location")} for x in list(r.history)+[r]]
    (out/"shortlink_response.html").write_text(r.text, encoding="utf-8", errors="ignore")
    return r.url, chain, r.text

def note_id_from(*texts):
    for t in texts:
        if not t: continue
        for rx in NOTE_ID_RES:
            m = rx.search(t)
            if m: return m.group(1)
    return ""

def score_url(url, mime, source):
    u = url.lower()
    s = 0
    if mime.startswith("video/"): s += 1000
    if "video" in source.lower(): s += 300
    if any(x in u for x in ["sns-video","video.xhscdn","xhscdn.com"]): s += 150
    if ".mp4" in u: s += 100
    if mime.startswith("image/"): s += 80
    if any(x in u for x in ["sns-img","ci.xiaohongshu.com","xhscdn.com"]): s += 50
    if any(x in u for x in ["avatar","logo","icon","emoji","favicon"]): s -= 500
    return s

def browser_extract(url, out: Path, report: dict):
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1440,1200")
    opts.add_argument("--lang=zh-CN")
    opts.set_capability("goog:loggingPrefs", {"performance":"ALL"})
    driver = webdriver.Chrome(options=opts)
    candidates, seen = [], set()
    def add(u, source="", mime=""):
        if not isinstance(u, str): return
        u = html.unescape(u.strip())
        if not u.startswith(("http://","https://")) or u.startswith("blob:") or u in seen: return
        seen.add(u)
        candidates.append({"url":u,"source":source,"mime":mime or ""})
    try:
        driver.get(url)
        time.sleep(10)
        report["browser_url"] = driver.current_url
        report["browser_title"] = driver.title
        src = driver.page_source
        (out/"page_browser.html").write_text(src, encoding="utf-8", errors="ignore")

        # metadata / description
        metas = driver.find_elements(By.TAG_NAME, "meta")
        meta_dump = {}
        for m in metas:
            name = m.get_attribute("name") or m.get_attribute("property") or ""
            content = m.get_attribute("content") or ""
            if name and content:
                meta_dump[name] = content
                if name.lower() in {"og:image","twitter:image","og:video","og:video:url"}:
                    add(content, "meta:"+name, "video/mp4" if "video" in name.lower() else "image/")
        report["meta"] = meta_dump
        report["description"] = meta_dump.get("description") or meta_dump.get("og:description") or ""
        report["title"] = meta_dump.get("og:title") or driver.title or ""

        # DOM media
        for i,v in enumerate(driver.find_elements(By.TAG_NAME,"video")):
            try:
                add(driver.execute_script("return arguments[0].currentSrc || ''", v), f"video[{i}].currentSrc", "video/")
                add(v.get_attribute("src"), f"video[{i}].src", "video/")
            except Exception: pass
        for i,img in enumerate(driver.find_elements(By.TAG_NAME,"img")):
            try:
                add(img.get_attribute("src"), f"img[{i}].src", "image/")
                srcset = img.get_attribute("srcset") or ""
                for part in srcset.split(","):
                    u = part.strip().split(" ")[0] if part.strip() else ""
                    add(u, f"img[{i}].srcset", "image/")
            except Exception: pass

        # performance resources
        try:
            resources = driver.execute_script("return performance.getEntriesByType('resource').map(x=>({name:x.name,initiatorType:x.initiatorType}));") or []
            for x in resources:
                u = x.get("name") or ""
                it = (x.get("initiatorType") or "").lower()
                low = u.lower()
                if it in {"video","img","image","media"} or "xhscdn" in low or ".mp4" in low:
                    add(u, "performance.resource", "video/" if it in {"video","media"} else "image/")
        except Exception:
            pass

        # performance network logs
        try:
            logs = driver.get_log("performance")
            for e in logs:
                try:
                    msg = json.loads(e["message"])["message"]
                    if msg.get("method") != "Network.responseReceived": continue
                    p = msg.get("params") or {}
                    resp = p.get("response") or {}
                    u = resp.get("url") or ""
                    mime = (resp.get("mimeType") or "").lower()
                    typ = (p.get("type") or "").lower()
                    low = u.lower()
                    if typ in {"media","image"} or mime.startswith(("video/","image/")) or "xhscdn" in low or ".mp4" in low:
                        add(u, "performance.log", mime or typ)
                except Exception:
                    pass
        except Exception:
            pass

        # JSON/script URL regex fallback
        for m in re.finditer(r'https?://[^"\'<>\\\s]+', src):
            u = html.unescape(m.group(0).replace("\\u002F","/").replace("\\/","/"))
            low = u.lower()
            if "xhscdn" in low or ".mp4" in low:
                add(u, "html.regex", "video/" if ".mp4" in low or "video" in low else "image/")
        report["note_id"] = report.get("note_id") or note_id_from(driver.current_url, src)
        cookies = driver.get_cookies()
        report["cookie_count"] = len(cookies)
        ua = driver.execute_script("return navigator.userAgent")
    finally:
        try: driver.quit()
        except Exception: pass

    # download candidates
    s = requests.Session()
    for c in cookies:
        try: s.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path","/"))
        except Exception: pass
    hdr = {"User-Agent":ua,"Referer":report.get("browser_url",url),"Accept":"*/*"}

    # dedupe, sort
    candidates.sort(key=lambda x: score_url(x["url"], x["mime"], x["source"]), reverse=True)
    report["candidates"] = candidates[:200]

    video_saved = False
    images_saved = []
    image_seen = set()
    for idx,c in enumerate(candidates):
        u, mime_hint = c["url"], c["mime"].lower()
        if video_saved and len(images_saved) >= 12: break
        try:
            r = s.get(u, headers=hdr, stream=True, timeout=45, allow_redirects=True)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code not in (200,206): continue
            is_video = ct.startswith("video/") or ".mp4" in u.lower() or "sns-video" in u.lower()
            is_image = ct.startswith("image/") and not any(x in u.lower() for x in ["avatar","logo","icon","emoji","favicon"])
            if is_video and not video_saved:
                p = out/"video.mp4"
                total = 0
                with p.open("wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        if chunk: f.write(chunk); total += len(chunk)
                if total > 100_000:
                    report["video_download"] = {"url":u,"bytes":total,"content_type":ct,"status":r.status_code,"source":c["source"]}
                    video_saved = True
                else:
                    p.unlink(missing_ok=True)
            elif is_image and not video_saved:
                key = u.split("?")[0]
                if key in image_seen: continue
                image_seen.add(key)
                ext = ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"
                p = out/f"image_{len(images_saved)+1:02d}{ext}"
                total = 0
                with p.open("wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        if chunk: f.write(chunk); total += len(chunk)
                if total > 20_000:
                    images_saved.append({"path":p.name,"url":u,"bytes":total,"content_type":ct,"source":c["source"]})
                else:
                    p.unlink(missing_ok=True)
        except Exception:
            continue
    report["images"] = images_saved
    return report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    report = {"input_url":a.url,"errors":[]}
    try:
        final, chain, html0 = resolve(a.url, out)
        report["resolved_url"] = final
        report["redirect_chain"] = chain
        report["note_id"] = note_id_from(final, html0)
    except Exception as e:
        final = a.url
        report["errors"].append(f"resolve: {type(e).__name__}: {e}")
    try:
        report = browser_extract(final, out, report)
    except Exception as e:
        report["errors"].append(f"browser: {type(e).__name__}: {e}")
    (out/"result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = (out/"video.mp4").exists() or bool(report.get("images"))
    raise SystemExit(0 if ok else 3)

if __name__ == "__main__":
    main()
