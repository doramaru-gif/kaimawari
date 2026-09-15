from datetime import datetime, timedelta

import pytest
import requests

from src import threads_api
from src.schedule import JST
from src.threads_api import ThreadsApiError, ThreadsClient, TokenStore

NOW = datetime(2026, 9, 19, 6, 0, tzinfo=JST)


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

    def _next(self, method, url, params, timeout):
        self.calls.append({"method": method, "url": url, "params": params})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, params, timeout):
        return self._next("POST", url, params, timeout)

    def get(self, url, params, timeout):
        return self._next("GET", url, params, timeout)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(threads_api.time, "sleep", lambda seconds: None)


def test_post_text_creates_container_then_publishes():
    session = FakeSession([FakeResponse({"id": "c1"}), FakeResponse({"id": "m1"})])
    client = ThreadsClient(access_token="SECRET", user_id="123", session=session)
    assert client.post_text("本文\n#PR", "https://example.github.io/kaimawari/", "楽天お買い物マラソン") == "m1"
    create, publish = session.calls
    assert create["url"].endswith("/v1.0/123/threads")
    assert create["params"]["media_type"] == "TEXT"
    assert create["params"]["link_attachment"] == "https://example.github.io/kaimawari/"
    assert create["params"]["topic_tag"] == "楽天お買い物マラソン"
    assert publish["url"].endswith("/v1.0/123/threads_publish")
    assert publish["params"]["creation_id"] == "c1"


def test_api_error_message_is_surfaced():
    session = FakeSession([FakeResponse({"error": {"message": "Invalid parameter", "code": 100}}, status=400)])
    client = ThreadsClient(access_token="SECRET", user_id="123", session=session)
    with pytest.raises(ThreadsApiError, match="Invalid parameter"):
        client.post_text("x")


def test_network_error_does_not_leak_token():
    error = requests.ConnectionError("https://graph.threads.net/v1.0/123/threads?access_token=SECRET")
    client = ThreadsClient(access_token="SECRET", user_id="123", session=FakeSession([error]))
    with pytest.raises(ThreadsApiError) as err:
        client.post_text("x")
    assert "SECRET" not in str(err.value)


def test_client_requires_credentials():
    with pytest.raises(ThreadsApiError, match="THREADS_ACCESS_TOKEN"):
        ThreadsClient(access_token="", user_id=None)


def test_token_store_refreshes_on_schedule(tmp_path):
    store = TokenStore(tmp_path / "token.json", env_token="env-token")
    session = FakeSession([FakeResponse({"access_token": "new-token", "token_type": "bearer", "expires_in": 5184000})])
    assert store.refresh_if_due(NOW, 7, session=session) is True
    assert session.calls[0]["params"] == {"grant_type": "th_refresh_token", "access_token": "env-token"}
    assert store.current() == "new-token"
    assert store.refresh_if_due(NOW + timedelta(days=1), 7, session=session) is False


def test_token_store_throttles_failed_refresh(tmp_path):
    store = TokenStore(tmp_path / "token.json", env_token="env-token")
    session = FakeSession([FakeResponse({"error": {"message": "Session has expired"}}, status=400)])
    with pytest.raises(ThreadsApiError):
        store.refresh_if_due(NOW, 7, session=session)
    assert store.refresh_if_due(NOW + timedelta(hours=1), 7, session=session) is False
    assert store.current() == "env-token"


def test_new_env_token_ignores_old_stored_token(tmp_path):
    path = tmp_path / "token.json"
    old = TokenStore(path, env_token="old-env")
    old.refresh_if_due(NOW, 7, session=FakeSession([FakeResponse({"access_token": "refreshed-old"})]))
    assert TokenStore(path, env_token="new-env").current() == "new-env"
