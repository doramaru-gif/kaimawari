"""サイトに載せる追加データの選定（本の枠、ポイント倍率アップの棚）"""

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


def pick_deals(candidates: list[dict], *, limit: int, min_reviews: int = 0) -> list[dict]:
    """いま倍率が上がっている商品を、倍率の高い順に。ショップは重複させない"""
    picked, shops, seen = [], set(), set()
    ordered = sorted(candidates, key=lambda it: (-it.get("point_rate_active", 1), it.get("price", 0),
                                                 -it.get("review_count", 0)))
    for item in ordered:
        code = item.get("item_code") or item.get("name")
        if item.get("point_rate_active", 1) < 2 or item.get("review_count", 0) < min_reviews:
            continue
        if code in seen or item.get("shop_code") in shops:
            continue
        seen.add(code)
        shops.add(item.get("shop_code"))
        picked.append(item)
        if len(picked) == limit:
            break
    return picked
