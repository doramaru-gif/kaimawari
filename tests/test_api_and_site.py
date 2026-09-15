from datetime import datetime, timedelta, timezone

import pytest

from src import rakuten_api
from src.planner import summarize
from src.rakuten_api import RakutenApiError, RakutenClient
from src.site_builder import build_site


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
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(rakuten_api.time, "sleep", lambda seconds: None)


def make_client(session):
    return RakutenClient(app_id="app", access_key="key", affiliate_id="aff",
                         referer="https://example.github.io/kaimawari/", session=session)


def test_client_sends_keys_referer_and_origin():
    session = FakeSession([FakeResponse({"Items": []})])
    make_client(session).search(keyword="1000円ポッキリ")
    call = session.calls[0]
    assert call["params"]["applicationId"] == "app"
    assert call["params"]["accessKey"] == "key"
    assert call["params"]["affiliateId"] == "aff"
    assert call["headers"]["Referer"] == "https://example.github.io/kaimawari/"
    assert call["headers"]["Origin"] == "https://example.github.io"


def test_client_retries_rate_limit_then_succeeds():
    session = FakeSession([FakeResponse({}, status=429), FakeResponse({"Items": []})])
    assert make_client(session).search(keyword="x") == []
    assert len(session.calls) == 2


def test_client_raises_with_api_error_detail():
    session = FakeSession([FakeResponse({"error": "wrong_parameter", "error_description": "specify valid applicationId"}, status=400)])
    with pytest.raises(RakutenApiError, match="specify valid applicationId"):
        make_client(session).search(keyword="x")


def test_client_requires_keys_and_site_url():
    with pytest.raises(RakutenApiError, match="SITE_URL"):
        RakutenClient(app_id="app", access_key="", affiliate_id=None, referer=None)


def test_site_escapes_names_and_shows_pr_notice(tmp_path):
    item = {"name": "<script>x</script>洗剤", "item_code": "a", "price": 1000, "tax_included": True,
            "postage_included": True, "url": "#", "shop_name": "S&A", "shop_code": "a", "image": "",
            "review_count": 40, "review_average": 4.5, "label": "日用品"}
    plan = summarize([item], strategy="cheapest")
    config = {
        "site": {"name": "買いまわり帳", "out_dir": "dist"},
        "marathon": {"shops_target": 10, "min_per_shop": 1000, "point_cap": 7000,
                     "next_period": "9/19〜9/24", "guide_url": "https://event.rakuten.co.jp/"},
        "rakuyoko": {"affiliate_url": "", "min_order": 2100, "max_order": 16666, "example_prices": [1990]},
    }
    build_site(tmp_path, config=config, plans={"cheapest": plan, "reviewed": plan}, candidates=[item],
               generated_at=datetime(2026, 9, 14, 5, 30, tzinfo=timezone(timedelta(hours=9))), demo=False)

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script>x</script>" not in index
    assert "&lt;script&gt;" in index
    assert "楽天アフィリエイトを利用しています" in index
    assert 'rel="sponsored noopener"' in index
    assert (tmp_path / "rakuyoko.html").exists()
    assert (tmp_path / "assets" / "tools.js").exists()
    assert (tmp_path / "data" / "plan.json").exists()
