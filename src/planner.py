"""お買い物マラソンの買いまわりプランを組む"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass


def price_with_tax(item: dict) -> int:
    """税込価格。税別表示（taxFlag=1）の商品は10%で切り上げ換算する"""
    price = int(item["price"])
    return price if item.get("tax_included", True) else (price * 11 + 9) // 10


def ex_tax(price_in_tax: int) -> int:
    """税抜の概算。軽減税率8%の商品もあるが、ポイントを多く見せないよう10%で割り戻す"""
    return price_in_tax * 10 // 11


def is_eligible(item: dict, min_per_shop: int, min_reviews: int = 0) -> bool:
    """1ショップ1カウントになる商品か。送料は1,000円判定に含まれないので送料込み商品だけを使う"""
    return (
        bool(item.get("shop_code"))
        and item.get("postage_included", False)
        and price_with_tax(item) >= min_per_shop
        and item.get("review_count", 0) >= min_reviews
    )


STRATEGIES = {
    "cheapest": lambda it: (price_with_tax(it), -it.get("review_count", 0)),
    "reviewed": lambda it: (-it.get("review_average", 0), -it.get("review_count", 0), price_with_tax(it)),
}


@dataclass
class Plan:
    strategy: str
    items: list
    shops: int
    multiplier: int
    total: int
    ex_tax_total: int
    normal_points: int
    bonus_points: int
    bonus_capped: bool
    point_cap: int

    @property
    def points(self) -> int:
        return self.normal_points + self.bonus_points

    @property
    def effective_rate(self) -> float:
        return self.points / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["points"] = self.points
        data["effective_rate"] = round(self.effective_rate, 4)
        return data


def pick_items(candidates: list[dict], *, strategy: str = "cheapest", shops_target: int = 10,
               min_per_shop: int = 1000, min_reviews: int = 0) -> list[dict]:
    """別々のショップから1点ずつ選ぶ。カテゴリが偏らないよう、選ばれた数が少ないカテゴリを優先する"""
    key = STRATEGIES[strategy]
    seen, pool = set(), []
    for item in candidates:
        code = item.get("item_code") or (item.get("shop_code"), item.get("name"))
        if code in seen or not is_eligible(item, min_per_shop, min_reviews):
            continue
        seen.add(code)
        pool.append(item)
    pool.sort(key=key)

    picked, shops, per_label = [], set(), Counter()
    while len(picked) < shops_target:
        available = [it for it in pool if it["shop_code"] not in shops]
        if not available:
            break
        fewest = min(per_label[it.get("label", "")] for it in available)
        choice = next(it for it in available if per_label[it.get("label", "")] == fewest)
        picked.append(choice)
        shops.add(choice["shop_code"])
        per_label[choice.get("label", "")] += 1
    return picked


def summarize(items: list[dict], *, strategy: str, shops_target: int = 10, point_cap: int = 7000) -> Plan:
    """通常1倍 + 買いまわり（ショップ数-1）倍 のポイントを税抜概算で見積もる"""
    prices = [price_with_tax(it) for it in items]
    total = sum(prices)
    ex_total = sum(ex_tax(p) for p in prices)
    shops = len({it["shop_code"] for it in items})
    multiplier = max(1, min(shops, shops_target))
    raw_bonus = ex_total * (multiplier - 1) // 100
    return Plan(
        strategy=strategy,
        items=items,
        shops=shops,
        multiplier=multiplier,
        total=total,
        ex_tax_total=ex_total,
        normal_points=ex_total // 100,
        bonus_points=min(raw_bonus, point_cap),
        bonus_capped=raw_bonus > point_cap,
        point_cap=point_cap,
    )
