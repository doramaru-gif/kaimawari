"""毎朝の選定結果の記録。あとから遡って作れない一次データなので、初日から残す"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

KEEP_DAYS = 180


def record_history(path: Path, plans: dict, candidates_count: int, now: datetime) -> list[dict]:
    """同じ日付は上書きし、KEEP_DAYS より古い記録は消す"""
    path = Path(path)
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    day = now.date().isoformat()

    entry = {"date": day, "candidates": candidates_count, "shops": plans["cheapest"].shops}
    for strategy, plan in plans.items():
        entry[f"{strategy}_total"] = plan.total
        entry[f"{strategy}_points"] = plan.points

    cutoff = (now.date() - timedelta(days=KEEP_DAYS)).isoformat()
    history = [h for h in history if h["date"] != day and h["date"] >= cutoff] + [entry]
    history.sort(key=lambda h: h["date"])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history
