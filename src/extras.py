"""楽天ブックス・楽天Kobo から、買いまわりの1ショップ分になる本を選ぶ"""

from __future__ import annotations

import re
from datetime import date

SALES_DATE = re.compile(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?")


def released(sales_date: str, today: date) -> bool:
    """発売済みか。予約商品は今日の買い物として数えにくいので外す。
    「2026年09月頃」のように日が無いものは、前の月までに出たものだけを発売済みとみなす"""
    match = SALES_DATE.match(sales_date or "")
    if not match:
        return True
    year, month, day = int(match[1]), int(match[2]), match[3]
    try:
        if day is None:
            return date(year, month, 1) < date(today.year, today.month, 1)
        return date(year, month, int(day)) <= today
    except ValueError:
        return True


def pick_books(books: list[dict], *, min_price: int, today: date, limit: int) -> list[dict]:
    """1,000円以上・発売済み・リンクありを、APIの並び（売れている順など）のまま選ぶ"""
    picked, seen = [], set()
    for book in books:
        if book["price"] < min_price or not book["url"] or not released(book.get("sales_date", ""), today):
            continue
        if book["name"] in seen:
            continue
        seen.add(book["name"])
        picked.append(book)
        if len(picked) == limit:
            break
    return picked
