import json
from datetime import datetime

from src.extras import pick_deals
from src.schedule import JST, parse_events, upcoming_summary
from src.sections import calendar_section, deals_section, steps_section
from src.status import build_status

NOW = datetime(2026, 9, 16, 8, 0, tzinfo=JST)
EVENTS = parse_events([
    {"name": "9月マラソン", "start": "2026-09-19T20:00", "end": "2026-09-24T01:59", "point_cap": 7000},
    {"name": "10月マラソン", "start": "2026-10-04T20:00", "end": "2026-10-09T01:59", "point_cap": 7000},
])


def item(**overrides):
    base = {"name": "商品", "item_code": "a:1", "price": 1000, "tax_included": True, "postage_included": True,
            "url": "https://hb.afl.rakuten.co.jp/x", "shop_name": "S", "shop_code": "s", "image": "",
            "review_count": 100, "review_average": 4.5, "point_rate_active": 1, "point_rate_end": ""}
    return {**base, **overrides}


def test_deals_are_sorted_by_rate_and_skip_duplicate_shops():
    candidates = [
        item(item_code="a:1", shop_code="a", point_rate_active=5),
        item(item_code="a:2", shop_code="a", point_rate_active=4),   # 同じショップは1つだけ
        item(item_code="b:1", shop_code="b", point_rate_active=20, price=4980, postage_included=False),
        item(item_code="c:1", shop_code="c", point_rate_active=1),   # 倍率なしは出さない
        item(item_code="d:1", shop_code="d", point_rate_active=10, review_count=5),
    ]
    deals = pick_deals(candidates, limit=8, min_reviews=30)
    assert [d["item_code"] for d in deals] == ["b:1", "a:1"]


def test_deals_section_shows_rate_price_and_postage():
    deals = [item(point_rate_active=20, point_rate_end="2026-09-24 01:59", price=4980, postage_included=False)]
    html = deals_section(deals)
    assert "還元率が高い順" in html
    assert "ポイント20倍〜9/24" in html and "¥4,980" in html and "送料別" in html
    assert deals_section([]) == ""


def test_calendar_shows_ongoing_and_days_until():
    summary = upcoming_summary(EVENTS, NOW)
    assert [entry["days_until"] for entry in summary] == [3, 18]
    assert summary[0]["ongoing"] is False
    html = calendar_section(summary)
    assert "あと3日" in html and "9月マラソン" in html and "7,000pt" in html

    during = upcoming_summary(EVENTS, datetime(2026, 9, 20, 12, 0, tzinfo=JST))
    assert during[0]["ongoing"] is True
    assert "開催中" in calendar_section(during)


def test_steps_section_links_to_entry():
    html = steps_section("https://event.rakuten.co.jp/campaign/point-up/marathon/")
    assert "エントリーする" in html
    assert 'href="https://event.rakuten.co.jp/campaign/point-up/marathon/"' in html


def test_status_summarizes_site_queue_and_schedule(tmp_path):
    plan = {"generated_at": "2026-09-16T05:30:00+09:00",
            "plans": {"cheapest": {"shops": 10, "total": 10000, "points": 1945, "effective_rate": 0.1945}}}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (tmp_path / "queue.json").write_text(json.dumps({"posts": [
        {"state": "pending"}, {"state": "approved"}, {"state": "posted"}, {"state": "posted"}]}), encoding="utf-8")
    (tmp_path / "history.json").write_text(json.dumps([{"date": "2026-09-15"}, {"date": "2026-09-16"}]), encoding="utf-8")

    text = build_status(plan_path=tmp_path / "plan.json", queue_path=tmp_path / "queue.json",
                        history_path=tmp_path / "history.json", site_url="https://doramaru-gif.github.io/kaimawari/",
                        threads_ready=False, calendar=upcoming_summary(EVENTS, NOW), now=NOW, notes="トークン待ち")
    assert "¥10,000" in text and "1,945pt" in text and "19.4%" in text
    assert "承認待ち1 / 予約済み1 / 投稿済み2" in text
    assert "未設定（アクセストークン待ち）" in text
    assert "9月マラソン" in text and "あと3日" in text
    assert "トークン待ち" in text
    assert "選定の記録: 2日分" in text


def test_status_without_plan_says_so(tmp_path):
    text = build_status(plan_path=tmp_path / "missing.json", queue_path=tmp_path / "missing.json",
                        history_path=tmp_path / "missing.json", site_url="https://example.com/",
                        threads_ready=True, calendar=[], now=NOW)
    assert "まだ実データでの生成をしていません" in text
    assert "設定済み" in text
