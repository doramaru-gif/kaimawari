"""お買い物マラソンの開催予定と、Threads 投稿枠の時刻"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
WEEKDAYS = "月火水木金土日"


@dataclass(frozen=True)
class MarathonEvent:
    name: str
    start: datetime
    end: datetime
    point_cap: int

    @property
    def key(self) -> str:
        return self.start.strftime("%Y%m%d")


def _parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=JST)


def parse_events(raw: list[dict] | None) -> list[MarathonEvent]:
    events = [
        MarathonEvent(name=e["name"], start=_parse(e["start"]), end=_parse(e["end"]),
                      point_cap=int(e.get("point_cap", 7000)))
        for e in raw or []
    ]
    return sorted(events, key=lambda ev: ev.start)


def next_event(events: list[MarathonEvent], now: datetime) -> MarathonEvent | None:
    """開催中、またはこれから始まる最初の回"""
    return next((ev for ev in events if ev.end > now), None)


def format_period(ev: MarathonEvent) -> str:
    s, e = ev.start, ev.end
    return (f"{s.year}年{s.month}月{s.day}日（{WEEKDAYS[s.weekday()]}）{s:%H:%M} 〜 "
            f"{e.month}月{e.day}日（{WEEKDAYS[e.weekday()]}）{e:%H:%M}")


def slots_for(ev: MarathonEvent) -> list[tuple[str, datetime]]:
    """1回のマラソンで投稿する枠。終了は深夜1:59なので「最終日」は終了2時間前の日付で決める"""
    def on_day(offset: int, hour: int, minute: int) -> datetime:
        return (ev.start + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    last_evening = ev.end - timedelta(hours=2)
    candidates = [
        ("eve", on_day(-1, 21, 0)),
        ("hour_before", ev.start - timedelta(hours=1)),
        ("kickoff", ev.start + timedelta(minutes=5)),
        ("midway", on_day(2, 12, 10)),
        ("rakuyoko", on_day(3, 21, 0)),
        ("final_day", last_evening.replace(hour=12, minute=10, second=0, microsecond=0)),
        ("last_2h", last_evening),
    ]
    before_start = {"eve", "hour_before"}
    slots = [(slot, at) for slot, at in candidates
             if at < ev.end and (slot in before_start or at >= ev.start)]
    return sorted(slots, key=lambda pair: pair[1])
