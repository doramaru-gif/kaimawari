from datetime import datetime
from types import SimpleNamespace

import pytest

from src import rakuten_api, threads_api
from src.schedule import JST
from src.setup_check import check_env, check_local, check_rakuten, check_schedule, check_threads

FULL_ENV = {
    "RAKUTEN_APP_ID": "app", "RAKUTEN_ACCESS_KEY": "key", "RAKUTEN_AFFILIATE_ID": "aff",
    "SITE_URL": "https://doram.github.io/kaimawari/", "THREADS_ACCESS_TOKEN": "token",
    "THREADS_USER_ID": "123", "DISCORD_WEBHOOK_URL": "",
}


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

    def get(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(rakuten_api.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(threads_api.time, "sleep", lambda seconds: None)


def by_label(results):
    return {r["label"]: r for r in results}


def test_env_flags_empty_keys_and_placeholder_site():
    results = by_label(check_env({**FULL_ENV, "RAKUTEN_ACCESS_KEY": "", "SITE_URL": "https://example.github.io/kaimawari/"}))
    assert results["楽天 アクセスキー"]["status"] == "block"
    assert results["公開URL"]["status"] == "block"
    assert results["Discord 通知"]["status"] == "ok"


def test_rakuten_needs_credentials_before_calling():
    [result] = check_rakuten({**FULL_ENV, "RAKUTEN_APP_ID": ""})
    assert result["status"] == "block"


def test_rakuten_success_confirms_affiliate_links():
    item = {"itemName": "x", "itemPrice": 1000, "shopCode": "s", "affiliateUrl": "https://hb.afl.rakuten.co.jp/x"}
    results = by_label(check_rakuten(FULL_ENV, session=FakeSession([FakeResponse({"Items": [item]})])))
    assert results["楽天API 接続"]["status"] == "ok"
    assert results["アフィリエイトリンク"]["status"] == "ok"


def test_rakuten_referer_error_gets_hint():
    session = FakeSession([FakeResponse({"error": "wrong_parameter", "error_description": "invalid referer"}, status=403)])
    [result] = check_rakuten(FULL_ENV, session=session)
    assert result["status"] == "block"
    assert "許可されたWebサイト" in result["message"]


def test_threads_suggests_user_id_when_missing(tmp_path):
    session = FakeSession([FakeResponse({"id": "987", "username": "kaimawari_note"})])
    results = by_label(check_threads({**FULL_ENV, "THREADS_USER_ID": ""}, tmp_path / "t.json", session=session))
    assert results["Threads 接続"]["status"] == "ok"
    assert "987" in results["Threads ユーザーID"]["message"]
    assert session.calls[0].endswith("/v1.0/me")


def test_threads_checks_id_match_and_quota(tmp_path):
    session = FakeSession([
        FakeResponse({"id": "123", "username": "kaimawari_note"}),
        FakeResponse({"data": [{"quota_usage": 4, "config": {"quota_total": 250, "quota_duration": 86400}}]}),
    ])
    results = by_label(check_threads(FULL_ENV, tmp_path / "t.json", session=session))
    assert results["Threads ユーザーID"]["status"] == "ok"
    assert results["Threads 投稿枠"]["message"] == "24時間で 4 / 250 件使用"


def test_threads_mismatched_user_id_blocks(tmp_path):
    session = FakeSession([FakeResponse({"id": "999", "username": "other"})])
    results = by_label(check_threads(FULL_ENV, tmp_path / "t.json", session=session))
    assert results["Threads ユーザーID"]["status"] == "block"


def test_schedule_requires_an_upcoming_event():
    config = {"marathon_events": [{"name": "9月", "start": "2026-09-19T20:00", "end": "2026-09-24T01:59"}]}
    assert check_schedule(config, datetime(2026, 9, 15, tzinfo=JST))[0]["status"] == "ok"
    assert check_schedule(config, datetime(2026, 9, 25, tzinfo=JST))[0]["status"] == "block"


def test_local_reports_git_and_tasks(tmp_path):
    (tmp_path / ".git").mkdir()

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return SimpleNamespace(stdout="origin\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0 if cmd[-1] == "kaimawari-daily" else 1)

    results = by_label(check_local(tmp_path, run=fake_run))
    assert results["GitHub Pages"]["status"] == "ok"
    assert results["タスク kaimawari-daily"]["status"] == "ok"
    assert results["タスク kaimawari-publish"]["status"] == "warn"
