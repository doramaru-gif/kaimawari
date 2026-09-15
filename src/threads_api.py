"""Threads API（テキスト投稿と長期アクセストークンの更新）"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

GRAPH = "https://graph.threads.net"
PUBLISH_WAIT = 30          # 秒。コンテナ作成から公開までの推奨待機
REFRESH_RETRY_HOURS = 6    # 更新に失敗したら、次に試すまで空ける時間


class ThreadsApiError(Exception):
    pass


def _call(method, url: str, params: dict) -> dict:
    try:
        res = method(url, params=params, timeout=30)
    except requests.RequestException as err:
        # 例外メッセージにはトークン入りのURLが含まれるので出さない
        raise ThreadsApiError(f"Threads に接続できませんでした（{type(err).__name__}）") from None
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code != 200 or "error" in data:
        err = data.get("error")
        message = err.get("message", "") if isinstance(err, dict) else (err or "")
        raise ThreadsApiError(f"HTTP {res.status_code} {message}".strip())
    return data


class ThreadsClient:
    def __init__(self, *, access_token: str | None, user_id: str | None,
                 session: requests.Session | None = None, publish_wait: float = PUBLISH_WAIT):
        if not (access_token and user_id):
            raise ThreadsApiError(".env に THREADS_ACCESS_TOKEN と THREADS_USER_ID を設定してください")
        self.access_token = access_token
        self.user_id = user_id
        self.session = session or requests.Session()
        self.publish_wait = publish_wait

    def post_text(self, text: str, link_url: str | None = None, topic_tag: str | None = None) -> str:
        params = {"media_type": "TEXT", "text": text, "access_token": self.access_token}
        if link_url:
            params["link_attachment"] = link_url
        if topic_tag:
            params["topic_tag"] = topic_tag
        container = _call(self.session.post, f"{GRAPH}/v1.0/{self.user_id}/threads", params)
        if "id" not in container:
            raise ThreadsApiError("コンテナIDが返りませんでした")
        time.sleep(self.publish_wait)
        published = _call(self.session.post, f"{GRAPH}/v1.0/{self.user_id}/threads_publish",
                          {"creation_id": container["id"], "access_token": self.access_token})
        if "id" not in published:
            raise ThreadsApiError("投稿IDが返りませんでした")
        return published["id"]

    def me(self) -> dict:
        """トークンの持ち主（id, username）"""
        return _call(self.session.get, f"{GRAPH}/v1.0/me",
                     {"fields": "id,username", "access_token": self.access_token})

    def publishing_quota(self) -> tuple[int, int]:
        """24時間の投稿枠（使用数, 上限）"""
        data = _call(self.session.get, f"{GRAPH}/v1.0/{self.user_id}/threads_publishing_limit",
                     {"fields": "quota_usage,config", "access_token": self.access_token})
        entry = (data.get("data") or [{}])[0]
        return int(entry.get("quota_usage", 0)), int((entry.get("config") or {}).get("quota_total", 250))


def refresh_long_lived_token(access_token: str, session: requests.Session | None = None) -> dict:
    session = session or requests.Session()
    data = _call(session.get, f"{GRAPH}/refresh_access_token",
                 {"grant_type": "th_refresh_token", "access_token": access_token})
    if "access_token" not in data:
        raise ThreadsApiError("更新後のトークンが返りませんでした")
    return data


def _fingerprint(token: str | None) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()[:12]


class TokenStore:
    """.env のトークンを起点に、更新したトークンを data/threads_token.json に保存する。
    .env のトークンを差し替えたら保存済みのものは使わない（指紋で判定）"""

    def __init__(self, path: Path, env_token: str | None):
        self.path = Path(path)
        self.env_token = env_token
        self.fingerprint = _fingerprint(env_token)

    def _stored(self) -> dict:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data if data.get("env_fingerprint") == self.fingerprint else {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({**data, "env_fingerprint": self.fingerprint}, indent=2), encoding="utf-8")

    def current(self) -> str | None:
        return self._stored().get("access_token") or self.env_token

    def refresh_if_due(self, now: datetime, every_days: int, session: requests.Session | None = None) -> bool:
        token = self.current()
        if not token:
            return False
        stored = self._stored()
        refreshed = stored.get("refreshed_at")
        attempted = stored.get("attempted_at")
        if refreshed and now - datetime.fromisoformat(refreshed) < timedelta(days=every_days):
            return False
        if attempted and now - datetime.fromisoformat(attempted) < timedelta(hours=REFRESH_RETRY_HOURS):
            return False
        try:
            data = refresh_long_lived_token(token, session)
        except ThreadsApiError:
            self._save({**stored, "attempted_at": now.isoformat()})
            raise
        self._save({
            "access_token": data["access_token"],
            "expires_in": data.get("expires_in"),
            "refreshed_at": now.isoformat(),
            "attempted_at": now.isoformat(),
        })
        return True
