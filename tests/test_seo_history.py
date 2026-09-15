import json
import re
from datetime import datetime, timedelta

import pytest
from PIL import Image

from src.history import KEEP_DAYS, record_history
from src.og_image import find_font, render_plan_card, render_rakuyoko_card
from src.planner import summarize
from src.schedule import JST
from src.site_builder import build_site

NOW = datetime(2026, 9, 19, 5, 30, tzinfo=JST)
CONFIG = {
    "site": {"name": "買いまわり帳", "out_dir": "dist"},
    "marathon": {"shops_target": 10, "min_per_shop": 1000, "point_cap": 7000,
                 "next_period": "9/19〜9/24", "guide_url": "https://event.rakuten.co.jp/"},
    "search": {"min_price": 1000, "max_price": 1380, "min_review_count": 30},
    "rakuyoko": {"affiliate_url": "", "min_order": 2100, "max_order": 16666, "example_prices": [1990]},
}


def make_plans():
    items = [{"name": f"商品{i}", "item_code": f"s{i}:1", "price": 1000, "tax_included": True,
              "postage_included": True, "url": "#", "shop_name": f"S{i}", "shop_code": f"s{i}",
              "image": "", "review_count": 40, "review_average": 4.5, "label": "日用品"} for i in range(10)]
    plan = summarize(items, strategy="cheapest")
    return {"cheapest": plan, "reviewed": summarize(items, strategy="reviewed")}, items


def test_history_replaces_same_day_and_trims_old(tmp_path):
    path = tmp_path / "history.json"
    plans, _ = make_plans()
    old = (NOW - timedelta(days=KEEP_DAYS + 1)).date().isoformat()
    path.write_text(json.dumps([{"date": old, "cheapest_total": 1, "cheapest_points": 1, "candidates": 1, "shops": 1}]),
                    encoding="utf-8")

    record_history(path, plans, 40, NOW)
    history = record_history(path, plans, 42, NOW + timedelta(hours=2))
    assert [h["date"] for h in history] == ["2026-09-19"]
    assert history[0]["candidates"] == 42
    assert history[0]["cheapest_total"] == 10000 and history[0]["reviewed_points"] == plans["reviewed"].points


def test_site_with_url_has_canonical_og_and_sitemap(tmp_path):
    plans, items = make_plans()
    history = [{"date": "2026-09-18", "cheapest_total": 10300, "cheapest_points": 930, "reviewed_total": 10400,
                "candidates": 180, "shops": 10}]
    build_site(tmp_path, config=CONFIG, plans=plans, candidates=items, generated_at=NOW, demo=False,
               site_url="https://doram.github.io/kaimawari", history=history)

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://doram.github.io/kaimawari/">' in index
    assert 'property="og:url" content="https://doram.github.io/kaimawari/"' in index
    assert "毎朝の選定記録" in index and "09/18" in index
    rakuyoko = (tmp_path / "rakuyoko.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://doram.github.io/kaimawari/rakuyoko.html">' in rakuyoko

    sitemap = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://doram.github.io/kaimawari/rakuyoko.html</loc>" in sitemap
    assert json.loads((tmp_path / "data" / "history.json").read_text(encoding="utf-8"))[0]["date"] == "2026-09-18"
    assert (tmp_path / "assets" / "favicon.svg").exists()

    if find_font():
        assert 'content="https://doram.github.io/kaimawari/assets/og-plan.png?v=20260919"' in index
        assert "og-rakuyoko.png?v=20260919" in rakuyoko


def test_site_without_url_skips_absolute_meta(tmp_path):
    plans, items = make_plans()
    warnings = build_site(tmp_path, config=CONFIG, plans=plans, candidates=items, generated_at=NOW, demo=True)
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "canonical" not in index and "og:image" not in index
    assert not (tmp_path / "sitemap.xml").exists()
    assert "毎朝の選定記録" not in index
    assert any("SITE_URL" in w for w in warnings)


def test_assets_are_versioned_and_plan_has_buy_checks(tmp_path):
    plans, items = make_plans()
    build_site(tmp_path, config=CONFIG, plans=plans, candidates=items, generated_at=NOW, demo=False)
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert re.search(r'assets/site\.css\?v=[0-9a-f]{8}"', index)
    assert re.search(r'assets/tools\.js\?v=[0-9a-f]{8}"', index)
    assert index.count('data-buy="s0:1"') == 2  # 安い順・レビュー順の両方
    assert 'data-slot="9"' in index and "0 / 10" in index
    assert 'href="https://event.rakuten.co.jp/campaign/point-up/marathon/"' in index


@pytest.mark.skipif(find_font() is None, reason="日本語フォントが無い環境")
def test_og_images_are_1200_by_630(tmp_path):
    plans, _ = make_plans()
    assert render_plan_card(tmp_path / "plan.png", plans["cheapest"], NOW)
    assert render_rakuyoko_card(tmp_path / "rakuyoko.png", 2100, 16666)
    for name in ("plan.png", "rakuyoko.png"):
        with Image.open(tmp_path / name) as img:
            assert img.size == (1200, 630)
