#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import requests

URL_RE = re.compile(
    r"https?://(?:(?:www\.)?xiaohongshu\.com|(?:www\.)?xhslink\.(?:com|cn))/[^\s]+",
    re.I,
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def extract_url(raw: str) -> str:
    m = URL_RE.search(raw or "")
    if not m:
        raise ValueError("No Xiaohongshu URL found")
    return m.group(0).rstrip("，。,.!！?？;；")


def resolve_profile_url(url: str) -> str:
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        allow_redirects=True,
        timeout=25,
    )
    r.raise_for_status()
    final_url = r.url
    if not re.search(r"/user/profile/[0-9A-Za-z]+", final_url):
        raise ValueError(f"Resolved URL is not a Xiaohongshu profile: {final_url}")
    return final_url


def pick_latest_card(tabs: list) -> dict | None:
    if not tabs:
        return None
    cards = (tabs[0] or {}).get("cards") or []
    if not cards:
        return None
    # Prefer the first non-sticky card to avoid an old pinned post being treated as "latest".
    for card in cards:
        if not ((card.get("interact") or {}).get("sticky")):
            return card
    return cards[0]


def build_note_url(card: dict | None) -> str:
    if not card:
        return ""
    note_id = str(card.get("note_id") or "").strip()
    if not note_id:
        return ""
    token = str(card.get("xsec_token") or "").strip()
    base = f"https://www.xiaohongshu.com/explore/{note_id}"
    if token:
        return (
            base
            + "?xsec_token="
            + urllib.parse.quote(token, safe="")
            + "&xsec_source=pc_user"
        )
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--profile-script", required=True)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "input": args.input,
        "upstream": "xinzhuwang-wxz/xhs-extract-master@b05a21ffc9c260f71a478a02b433aa06ba6e8441",
        "errors": [],
    }

    try:
        share_url = extract_url(args.input)
        final_url = resolve_profile_url(share_url)
        report["share_url"] = share_url
        report["final_url"] = final_url

        raw_path = out / "profile_raw.json"
        proc = subprocess.run(
            [
                sys.executable,
                args.profile_script,
                final_url,
                "--output",
                str(raw_path),
                "--pretty",
                "--error-json",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        report["profile_parser_exit_code"] = proc.returncode
        if proc.stderr.strip():
            report["profile_parser_stderr"] = proc.stderr.strip()[-4000:]
        if not raw_path.exists():
            raise RuntimeError(
                f"profile parser produced no output, exit={proc.returncode}, stdout={proc.stdout[-2000:]}"
            )

        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        if raw.get("error"):
            raise RuntimeError(raw.get("message") or "profile parser returned an error")

        extract = raw.get("extract") or {}
        if extract.get("type") != "user":
            raise RuntimeError(f"unexpected profile extract type: {extract.get('type')}")
        data = extract.get("data") or {}

        latest = pick_latest_card(data.get("tabs") or [])
        latest_url = build_note_url(latest)

        report.update({
            "user_id": data.get("user_id"),
            "red_id": data.get("red_id"),
            "basic_info": data.get("basic_info") or {},
            "interactions": data.get("interactions") or {},
            "tags": data.get("tags") or [],
            "tab_public": data.get("tab_public") or {},
            "notes": ((data.get("tabs") or [{}])[0] or {}).get("cards") or [],
            "note_count_visible": len((((data.get("tabs") or [{}])[0] or {}).get("cards") or [])),
            "latest_note": latest,
            "latest_note_url": latest_url,
        })

        (out / "latest_note_url.txt").write_text(latest_url, encoding="utf-8")
    except Exception as e:
        report["errors"].append(f"{type(e).__name__}: {e}")

    (out / "profile.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "user_id": report.get("user_id"),
        "nickname": (report.get("basic_info") or {}).get("nickname")
            or (report.get("basic_info") or {}).get("nickName")
            or (report.get("basic_info") or {}).get("name"),
        "red_id": report.get("red_id"),
        "note_count_visible": report.get("note_count_visible", 0),
        "latest_note_id": (report.get("latest_note") or {}).get("note_id"),
        "latest_note_title": (report.get("latest_note") or {}).get("title"),
        "errors": report.get("errors"),
    }, ensure_ascii=False, indent=2))

    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
