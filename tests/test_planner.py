import json
from pathlib import Path

import pytest

from src.planner import is_eligible, pick_items, price_with_tax, summarize
from src.rakuten_api import parse_items

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_search.json"


@pytest.fixture
def candidates():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = []
    for label, payload in data.items():
        if label.startswith("_"):
            continue
        for item in parse_items(payload):
            item["label"] = label
            items.append(item)
    return items


def test_price_with_tax_converts_tax_excluded_items():
    assert price_with_tax({"price": 1000, "tax_included": True}) == 1000
    assert price_with_tax({"price": 950, "tax_included": False}) == 1045


def test_eligibility_requires_postage_included_and_threshold():
    base = {"shop_code": "s", "postage_included": True, "price": 1000, "tax_included": True, "review_count": 50}
    assert is_eligible(base, 1000, 30)
    assert not is_eligible({**base, "postage_included": False}, 1000, 30)
    assert not is_eligible({**base, "price": 990}, 1000, 30)
    assert not is_eligible({**base, "review_count": 10}, 1000, 30)


def test_cheapest_plan_uses_ten_distinct_shops(candidates):
    picked = pick_items(candidates, strategy="cheapest", shops_target=10, min_per_shop=1000, min_reviews=30)
    shops = [it["shop_code"] for it in picked]
    assert len(picked) == 10
    assert len(set(shops)) == 10
    assert "sample-g" not in shops  # レビュー25件は除外
    assert all(it["postage_included"] and price_with_tax(it) >= 1000 for it in picked)


def test_plan_spreads_across_categories_before_repeating(candidates):
    picked = pick_items(candidates, strategy="cheapest", shops_target=10, min_per_shop=1000, min_reviews=30)
    first_round = [it["label"] for it in picked[:8]]
    assert len(set(first_round)) == 8


def test_summary_estimates_points_on_tax_excluded_total(candidates):
    picked = pick_items(candidates, strategy="cheapest", shops_target=10, min_per_shop=1000, min_reviews=30)
    plan = summarize(picked, strategy="cheapest", shops_target=10, point_cap=7000)
    assert plan.total == 10175
    assert plan.ex_tax_total == 9248
    assert plan.multiplier == 10
    assert plan.normal_points == 92
    assert plan.bonus_points == 832
    assert not plan.bonus_capped


def test_summary_applies_point_cap(candidates):
    picked = pick_items(candidates, strategy="cheapest", shops_target=10, min_per_shop=1000, min_reviews=30)
    plan = summarize(picked, strategy="cheapest", point_cap=500)
    assert plan.bonus_points == 500
    assert plan.bonus_capped


def test_multiplier_follows_shop_count_when_short():
    items = [
        {"shop_code": f"s{i}", "price": 1000, "tax_included": True, "postage_included": True}
        for i in range(3)
    ]
    plan = summarize(items, strategy="cheapest")
    assert plan.multiplier == 3
    assert plan.bonus_points == 2727 * 2 // 100


def test_reviewed_strategy_starts_with_best_rated(candidates):
    picked = pick_items(candidates, strategy="reviewed", shops_target=10, min_per_shop=1000, min_reviews=30)
    assert "麦茶" in picked[0]["name"]


def test_parse_items_supports_format_version_1():
    data = {"Items": [{"Item": {
        "itemName": "x", "itemPrice": 1200, "taxFlag": 0, "postageFlag": 0,
        "affiliateUrl": "https://hb.afl.rakuten.co.jp/x", "itemUrl": "https://item.rakuten.co.jp/x",
        "shopCode": "s", "shopName": "S", "mediumImageUrls": [{"imageUrl": "https://thumbnail.image.rakuten.co.jp/x.jpg"}],
        "reviewCount": 3, "reviewAverage": 4.0,
    }}]}
    [item] = parse_items(data)
    assert item["url"].startswith("https://hb.afl.rakuten.co.jp")
    assert item["has_affiliate"]
    assert item["image"].endswith("x.jpg")
    assert item["postage_included"]
