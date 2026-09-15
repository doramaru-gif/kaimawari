"""Threads 投稿の公開前チェック。status が block の項目が1つでもあれば承認・投稿しない"""

from __future__ import annotations

import re
from urllib.parse import urlparse

MAX_CHARS = 500
MAX_LINKS = 5
RISKY_WORDS = ("絶対", "いちばんお得", "一番お得", "最安", "必ず", "確実に", "100%", "１００％")
PR_PATTERN = re.compile(r"#PR|【PR】|(?:^|\s)PR(?:\s|$)")
URL_PATTERN = re.compile(r"https?://\S+")


def run_checks(text: str, *, fact: str | None = None, link_url: str | None = None) -> list[dict]:
    checks = []

    if PR_PATTERN.search(text):
        checks.append({"label": "PR表記", "status": "ok", "message": "本文に「#PR」があります"})
    else:
        checks.append({"label": "PR表記", "status": "block", "fix": "pr",
                       "message": "アフィリエイト報酬につながる投稿です。ステマ規制のため PR 表記が必要です"})

    length = len(text)
    if length <= MAX_CHARS:
        checks.append({"label": "文字数", "status": "ok", "message": f"{length} / {MAX_CHARS}字"})
    else:
        checks.append({"label": "文字数", "status": "block",
                       "message": f"{length} / {MAX_CHARS}字。Threads の上限を超えています"})

    hits = [w for w in RISKY_WORDS if w in text]
    if hits:
        checks.append({"label": "断定・誇大表現", "status": "block",
                       "message": f"「{'」「'.join(hits)}」は優良誤認と取られるおそれがあります。言い換えてください"})
    else:
        checks.append({"label": "断定・誇大表現", "status": "ok", "message": "該当なし"})

    links = len(URL_PATTERN.findall(text)) + (1 if link_url else 0)
    if links > MAX_LINKS:
        checks.append({"label": "リンク", "status": "block",
                       "message": f"リンクが{links}個あります。Threads は{MAX_LINKS}個までです"})
    elif link_url:
        checks.append({"label": "リンク", "status": "ok", "message": f"リンクカード：{urlparse(link_url).netloc}"})
    else:
        # リンク付き投稿は表示が伸びにくいので、会話用の投稿はリンクなしでプロフィールへ誘導する
        checks.append({"label": "リンク", "status": "ok",
                       "message": "リンクなし（プロフィールのリンクから誘導）"})

    if fact:
        checks.append({"label": "数字と条件の出典", "status": "ok", "message": fact})
    else:
        checks.append({"label": "数字と条件の出典", "status": "warn",
                       "message": "出典が紐づいていません。承認はできますが、数字は再確認してください"})
    return checks


def has_blocking(checks: list[dict]) -> bool:
    return any(c["status"] == "block" for c in checks)
