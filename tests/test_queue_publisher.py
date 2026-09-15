from datetime import datetime, timedelta

import pytest

from src.publisher import publish_due
from src.queue_store import QueueError, QueueStore
from src.review_api import handle, is_local_request
from src.schedule import JST, parse_events
from src.threads_api import ThreadsApiError

NOW = datetime(2026, 9, 19, 6, 0, tzinfo=JST)
SITE = "https://example.github.io/kaimawari/"
EVENTS = parse_events([{"name": "9月", "start": "2026-09-19T20:00", "end": "2026-09-24T01:59"}])


def draft(post_id="20260919-kickoff", at="2026-09-19T20:05:00+09:00", text="マラソン始まった。\n#PR"):
    return {"id": post_id, "at": at, "kind": "開始直後", "source": "今日のプラン", "event": "9月",
            "text": text, "link_url": SITE, "fact": "plan.json"}


class FakeThreads:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def post_text(self, text, link_url=None, topic_tag=None):
        self.calls.append((text, link_url))
        self.topic_tags = getattr(self, "topic_tags", []) + [topic_tag]
        if self.fail:
            raise ThreadsApiError("HTTP 400 Invalid parameter")
        return "17900000000"


@pytest.fixture
def store(tmp_path):
    return QueueStore(tmp_path / "queue.json")


def state_of(store, post_id):
    return next(p for p in store.snapshot()["posts"] if p["id"] == post_id)


def test_add_drafts_is_idempotent(store):
    assert store.add_drafts([draft()], NOW) == 1
    assert store.add_drafts([draft()], NOW) == 0
    assert state_of(store, "20260919-kickoff")["state"] == "pending"


def test_approve_refuses_post_with_blocking_check(store):
    store.add_drafts([draft(text="表記なしの本文")], NOW)
    with pytest.raises(QueueError) as err:
        store.approve("20260919-kickoff", NOW)
    assert err.value.status == 422


def test_edit_approve_lock_and_undo(store):
    store.add_drafts([draft(text="表記なしの本文")], NOW)
    store.update_text("20260919-kickoff", "表記なしの本文\n#PR")
    assert store.approve("20260919-kickoff", NOW)["state"] == "approved"
    with pytest.raises(QueueError):
        store.update_text("20260919-kickoff", "承認後の書き換え")
    assert store.undo("20260919-kickoff")["state"] == "pending"


def test_publish_posts_only_due_approved(store):
    store.add_drafts([draft(), draft("20260921-midway", "2026-09-21T12:10:00+09:00")], NOW)
    store.approve("20260919-kickoff", NOW)
    store.approve("20260921-midway", NOW)
    client = FakeThreads()

    results = publish_due(store, client, now=datetime(2026, 9, 19, 20, 6, tzinfo=JST))
    assert [r["id"] for r in results] == ["20260919-kickoff"]
    assert client.calls == [("マラソン始まった。\n#PR", SITE)]
    posted = state_of(store, "20260919-kickoff")
    assert posted["state"] == "posted" and posted["post_id"] == "17900000000"
    assert state_of(store, "20260921-midway")["state"] == "approved"

    assert publish_due(store, client, now=datetime(2026, 9, 19, 20, 16, tzinfo=JST)) == []
    assert len(client.calls) == 1


def test_publish_skips_pending_and_rejected(store):
    store.add_drafts([draft(), draft("20260919-hour_before", "2026-09-19T19:00:00+09:00")], NOW)
    store.reject("20260919-hour_before")
    client = FakeThreads()
    assert publish_due(store, client, now=datetime(2026, 9, 19, 20, 30, tzinfo=JST)) == []
    assert client.calls == []


def test_publish_expires_after_grace(store):
    store.add_drafts([draft()], NOW)
    store.approve("20260919-kickoff", NOW)
    client = FakeThreads()
    results = publish_due(store, client, now=datetime(2026, 9, 19, 23, 30, tzinfo=JST), grace_minutes=180)
    assert results[0]["result"] == "expired"
    assert state_of(store, "20260919-kickoff")["state"] == "expired"
    assert client.calls == []


def test_publish_records_api_failure(store):
    store.add_drafts([draft()], NOW)
    store.approve("20260919-kickoff", NOW)
    results = publish_due(store, FakeThreads(fail=True), now=datetime(2026, 9, 19, 20, 6, tzinfo=JST))
    assert results[0]["result"] == "failed"
    post = state_of(store, "20260919-kickoff")
    assert post["state"] == "failed" and "Invalid parameter" in post["error"]
    assert "publishing_at" not in post


def test_dry_run_changes_nothing(store):
    store.add_drafts([draft()], NOW)
    store.approve("20260919-kickoff", NOW)
    client = FakeThreads()
    results = publish_due(store, client, now=datetime(2026, 9, 19, 20, 6, tzinfo=JST), dry_run=True)
    assert results == [{"id": "20260919-kickoff", "result": "dry_run"}]
    assert state_of(store, "20260919-kickoff")["state"] == "approved"
    assert client.calls == []


def test_stuck_publishing_is_not_resent(store):
    store.add_drafts([draft()], NOW)
    with store.transaction() as data:
        data["posts"][0].update(state="publishing", publishing_at="2026-09-19T20:05:00+09:00")
    client = FakeThreads()
    results = publish_due(store, client, now=datetime(2026, 9, 19, 20, 45, tzinfo=JST))
    assert results[0]["result"] == "failed"
    assert client.calls == []


def test_review_api_lists_posts_with_checks(store):
    store.add_drafts([draft(), draft("20260901-old", "2026-09-01T12:00:00+09:00")], NOW)
    status, payload = handle(store, EVENTS, "GET", "/api/posts", None, NOW, threads_ready=False)
    assert status == 200
    assert [p["id"] for p in payload["posts"]] == ["20260919-kickoff"]
    assert payload["posts"][0]["blocking"] is False
    assert payload["threads_ready"] is False
    assert payload["events"][0]["start"].startswith("2026-09-19T20:00")


def test_review_api_actions_and_errors(store):
    store.add_drafts([draft(text="表記なし")], NOW)
    assert handle(store, EVENTS, "POST", "/api/posts/20260919-kickoff/text", {}, NOW, threads_ready=False)[0] == 400
    assert handle(store, EVENTS, "POST", "/api/posts/20260919-kickoff/approve", {}, NOW, threads_ready=False)[0] == 422
    status, payload = handle(store, EVENTS, "POST", "/api/posts/20260919-kickoff/text", {"text": "表記なし\n#PR"},
                             NOW, threads_ready=False)
    assert status == 200 and payload["post"]["blocking"] is False
    assert handle(store, EVENTS, "POST", "/api/posts/20260919-kickoff/approve", {}, NOW, threads_ready=False)[0] == 200
    assert handle(store, EVENTS, "POST", "/api/posts/missing/approve", {}, NOW, threads_ready=False)[0] == 404
    assert handle(store, EVENTS, "DELETE", "/api/posts/20260919-kickoff/approve", {}, NOW, threads_ready=False)[0] == 404


def test_local_request_guard():
    assert is_local_request("127.0.0.1:8766", None, 8766)
    assert is_local_request("localhost:8766", "http://localhost:8766", 8766)
    assert not is_local_request("evil.example:8766", None, 8766)
    assert not is_local_request("127.0.0.1:8766", "https://evil.example", 8766)
