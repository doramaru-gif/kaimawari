"""予約時刻が来た承認済みの投稿だけを Threads に出す"""

from __future__ import annotations

from datetime import datetime, timedelta

from .checks import has_blocking, run_checks
from .queue_store import QueueStore
from .threads_api import ThreadsApiError

STUCK_MINUTES = 30


def publish_due(store: QueueStore, client, *, now: datetime, grace_minutes: int = 180,
                dry_run: bool = False) -> list[dict]:
    results: list[dict] = []
    to_post: list[dict] = []

    with store.transaction() as data:
        for post in data["posts"]:
            if post["state"] == "publishing":
                started = datetime.fromisoformat(post["publishing_at"])
                if now - started > timedelta(minutes=STUCK_MINUTES) and not dry_run:
                    # 投稿したかどうか分からない状態。二重投稿を避けるため再送はしない
                    post["state"] = "failed"
                    post["error"] = "投稿結果を確認できませんでした。Threads で投稿されたか確認してください"
                    results.append({"id": post["id"], "result": "failed", "error": post["error"]})
                continue
            if post["state"] != "approved":
                continue
            at = datetime.fromisoformat(post["at"])
            if at > now:
                continue
            if now - at > timedelta(minutes=grace_minutes):
                error = f"予約時刻から{grace_minutes}分以上過ぎたため投稿しませんでした"
                if not dry_run:
                    post["state"] = "expired"
                    post["error"] = error
                results.append({"id": post["id"], "result": "expired", "error": error})
                continue
            if has_blocking(run_checks(post["text"], fact=post.get("fact"), link_url=post.get("link_url"))):
                error = "公開前チェックに ✕ があるため投稿しませんでした"
                if not dry_run:
                    post["state"] = "failed"
                    post["error"] = error
                results.append({"id": post["id"], "result": "failed", "error": error})
                continue
            if dry_run:
                results.append({"id": post["id"], "result": "dry_run"})
                continue
            post["state"] = "publishing"
            post["publishing_at"] = now.isoformat()
            to_post.append(dict(post))

    for post in to_post:
        try:
            post_id = client.post_text(post["text"], post.get("link_url"), post.get("topic_tag"))
            outcome = {"state": "posted", "post_id": post_id, "posted_at": now.isoformat()}
        except ThreadsApiError as err:
            outcome = {"state": "failed", "error": str(err)}
        with store.transaction() as data:
            target = store._find(data, post["id"])
            target.update(outcome)
            target.pop("publishing_at", None)
        results.append({"id": post["id"], "result": outcome["state"], **{k: v for k, v in outcome.items() if k != "state"}})

    return results
