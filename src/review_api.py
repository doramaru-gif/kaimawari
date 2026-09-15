"""承認デスクのAPI。HTTPサーバーから切り離して、テストしやすい純粋な処理にしている"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .checks import has_blocking, run_checks
from .queue_store import QueueError, QueueStore
from .schedule import MarathonEvent

ACTION = re.compile(r"^/api/posts/([A-Za-z0-9_-]+)/(text|approve|reject|undo)$")
KEEP_DAYS = 7


def view(post: dict) -> dict:
    checks = run_checks(post["text"], fact=post.get("fact"), link_url=post.get("link_url"))
    return {**post, "checks": checks, "blocking": has_blocking(checks)}


def is_local_request(host: str | None, origin: str | None, port: int) -> bool:
    """DNSリバインディングと他サイトからの送信を防ぐ"""
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if host not in allowed:
        return False
    return origin is None or origin in {f"http://{h}" for h in allowed}


def handle(store: QueueStore, events: list[MarathonEvent], method: str, path: str, body, now: datetime,
           *, threads_ready: bool, demo: bool = False) -> tuple[int, dict]:
    if method == "GET" and path == "/api/posts":
        cutoff = now - timedelta(days=KEEP_DAYS)
        posts = [view(p) for p in store.snapshot()["posts"] if datetime.fromisoformat(p["at"]) >= cutoff]
        return 200, {
            "now": now.isoformat(),
            "threads_ready": threads_ready,
            "demo": demo,
            "posts": posts,
            "events": [{"name": e.name, "start": e.start.isoformat(), "end": e.end.isoformat()} for e in events],
        }

    match = ACTION.match(path)
    if method != "POST" or not match:
        return 404, {"error": "このURLは使えません"}

    post_id, action = match.groups()
    try:
        if action == "text":
            text = body.get("text") if isinstance(body, dict) else None
            if not isinstance(text, str):
                return 400, {"error": "本文（text）を文字列で送ってください"}
            post = store.update_text(post_id, text)
        elif action == "approve":
            post = store.approve(post_id, now)
        elif action == "reject":
            post = store.reject(post_id)
        else:
            post = store.undo(post_id)
    except QueueError as err:
        return err.status, {"error": str(err)}
    return 200, {"post": view(post)}
