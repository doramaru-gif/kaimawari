"""定期連携用の状況メモを作る。セッションの最初に貼ると、続きからすぐ動ける"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def _load(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build_status(*, plan_path: Path, queue_path: Path, history_path: Path, site_url: str,
                 threads_ready: bool, calendar: list[dict], now: datetime, notes: str = "") -> str:
    plan_payload = _load(plan_path, {})
    cheapest = (plan_payload.get("plans") or {}).get("cheapest") or {}
    posts = _load(queue_path, {}).get("posts", [])
    states = Counter(post.get("state") for post in posts)
    history = _load(history_path, [])

    lines = [f"【買いまわり帳 定期連携 {now:%Y-%m-%d %H:%M}】", "", "■ サイト"]
    if cheapest:
        generated = str(plan_payload.get("generated_at", ""))[:16].replace("T", " ")
        rate = cheapest.get("effective_rate", 0) * 100
        lines += [
            f"- 最終更新: {generated}（毎朝5:30に自動更新）",
            f"- 公開URL: {site_url}",
            f"- 今日のプラン: {cheapest.get('shops', 0)}ショップ ¥{cheapest.get('total', 0):,} / "
            f"見込み{cheapest.get('points', 0):,}pt（実質{rate:.1f}%）",
            f"- 選定の記録: {len(history)}日分",
        ]
    else:
        lines.append("- まだ実データでの生成をしていません（python main.py）")

    lines += [
        "",
        "■ Threads",
        f"- 接続: {'設定済み' if threads_ready else '未設定（アクセストークン待ち）'}",
        f"- キュー: 承認待ち{states.get('pending', 0)} / 予約済み{states.get('approved', 0)} / "
        f"投稿済み{states.get('posted', 0)} / 却下{states.get('rejected', 0)} / 失敗{states.get('failed', 0)}",
    ]

    if calendar:
        lines += ["", "■ 開催予定"]
        for entry in calendar:
            when = "開催中" if entry["ongoing"] else f"あと{entry['days_until']}日"
            lines.append(f"- {entry['name']} {entry['period']}（{when}・上限{entry['point_cap']:,}pt）")

    lines += ["", "■ 相談したいこと", f"- {notes or '（あれば書く）'}"]
    return "\n".join(lines)
