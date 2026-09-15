from datetime import date, datetime

import pytest

from src import rakuten_api
from src.extras import pick_books, released
from src.planner import apply_point_rates, pick_items, summarize
from src.rakuten_api import RakutenClient, parse_books, parse_items
from src.schedule import JST
from src.sections import badges, books_section, ranking_section

NOW = datetime(2026, 9, 16, 7, 0, tzinfo=JST)


def item(**overrides):
    base = {"name": "商品", "item_code": "s:1", "price": 1000, "tax_included": True, "postage_included": True,
            "url": "https://hb.afl.rakuten.co.jp/x", "shop_name": "S", "shop_code": "s", "image": "",
            "review_count": 100, "review_average": 4.5, "label": "日用品",
            "point_rate": 1, "point_rate_start": "", "point_rate_end": ""}
    return {**base, **overrides}


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append({"url": url, "params": params})
        return self.responses.pop(0)


def test_parse_items_reads_point_rate_rank_and_soy():
    data = {"Items": [{"itemName": "x", "itemPrice": 1000, "shopCode": "s", "pointRate": 5,
                       "pointRateStartTime": "2026-09-01 00:00", "pointRateEndTime": "2026-09-30 23:59",
                       "shopOfTheYearFlag": 1, "rank": 3}]}
    [parsed] = parse_items(data)
    assert parsed["point_rate"] == 5
    assert parsed["point_rate_end"] == "2026-09-30 23:59"
    assert parsed["shop_of_the_year"] and parsed["rank"] == 3


def test_only_currently_active_point_rates_count():
    items = [
        item(item_code="ended", point_rate=10, point_rate_start="2026-09-15 00:00", point_rate_end="2026-09-15 23:59"),
        item(item_code="ongoing", point_rate=3, point_rate_start="2026-09-01 00:00", point_rate_end="9999-12-31 23:59"),
        item(item_code="later", point_rate=5, point_rate_start="2026-09-20 00:00", point_rate_end="2026-09-25 23:59"),
    ]
    apply_point_rates(items, NOW)
    assert [it["point_rate_active"] for it in items] == [1, 3, 1]


def test_point_rate_breaks_price_ties_and_raises_estimate():
    items = [item(item_code=f"s{i}:1", shop_code=f"s{i}") for i in range(3)]
    items.append(item(item_code="p:1", shop_code="p", point_rate=5, review_count=40,
                      point_rate_start="2026-09-01 00:00", point_rate_end="2026-09-30 23:59"))
    apply_point_rates(items, NOW)
    picked = pick_items(items, strategy="cheapest", shops_target=2, min_per_shop=1000)
    assert picked[0]["shop_code"] == "p"
    plan = summarize(picked, strategy="cheapest", shops_target=10)
    assert plan.normal_points == (909 * 5 + 909) // 100


def test_badges_show_rate_until_and_soy():
    active = {**item(point_rate=5, point_rate_end="2026-09-24 01:59", shop_of_the_year=True), "point_rate_active": 5}
    html = "".join(badges(active))
    assert "ポイント5倍〜9/24" in html and "ショップ・オブ・ザ・イヤー" in html
    open_ended = {**active, "point_rate_end": "9999-12-31 23:59"}
    assert "ポイント5倍</span>" in "".join(badges(open_ended))


def test_ranking_is_sorted_by_rank(monkeypatch):
    monkeypatch.setattr(rakuten_api.time, "sleep", lambda seconds: None)
    payload = {"Items": [{"itemName": "c", "itemPrice": 1, "shopCode": "c", "rank": 3},
                         {"itemName": "a", "itemPrice": 1, "shopCode": "a", "rank": 1}]}
    session = FakeSession([FakeResponse(payload)])
    client = RakutenClient(app_id="app", access_key="key", affiliate_id="aff",
                           referer="https://example.github.io/kaimawari/", session=session)
    assert [it["rank"] for it in client.ranking(age=30, sex=1)] == [1, 3]
    assert session.calls[0]["url"] == rakuten_api.RANKING_URL
    assert session.calls[0]["params"]["age"] == 30 and session.calls[0]["params"]["affiliateId"] == "aff"


def test_books_skip_cheap_preorders_and_month_only_dates():
    data = {"Items": [
        {"title": "安い本", "itemPrice": 700, "affiliateUrl": "https://hb.afl/a", "salesDate": "2026年08月04日"},
        {"title": "予約の本", "itemPrice": 3410, "affiliateUrl": "https://hb.afl/b", "salesDate": "2026年11月20日頃"},
        {"title": "今月頃の本", "itemPrice": 1200, "affiliateUrl": "https://hb.afl/c", "salesDate": "2026年09月頃"},
        {"title": "買える本", "itemPrice": 1320, "affiliateUrl": "https://hb.afl/d", "salesDate": "2026年09月04日",
         "author": "著者", "reviewAverage": "4.50"},
    ]}
    books = parse_books(data)
    assert books[3]["review_average"] == 4.5
    picked = pick_books(books, min_price=1000, today=date(2026, 9, 16), limit=6)
    assert [b["name"] for b in picked] == ["買える本"]
    assert released("", date(2026, 9, 16))


def test_sections_render_and_disappear_when_empty():
    assert ranking_section([]) == ""
    assert books_section([], [], {}) == ""
    ranked = {**item(rank=1, name="<b>売れ筋</b>"), "point_rate_active": 1}
    html = ranking_section([{"label": "総合", "items": [ranked]}, {"label": "女性30代", "items": [ranked]}])
    assert "&lt;b&gt;売れ筋" in html
    assert 'data-panel="1" hidden' in html
    assert 'rel="sponsored noopener"' in html
    books_html = books_section([{"name": "本", "author": "A", "price": 1320, "url": "https://x", "image": ""}], [], {})
    assert "楽天ブックス（漫画・売れている順）" in books_html and "¥1,320" in books_html
    assert "楽天Kobo（電子書籍）" not in books_html


def test_rate_ending_before_marathon_start_is_not_counted():
    items = [item(point_rate=10, point_rate_start="2026-09-10 00:00", point_rate_end="2026-09-18 23:59")]
    apply_point_rates(items, datetime(2026, 9, 19, 20, 0, tzinfo=JST))
    assert items[0]["point_rate_active"] == 1
