"""投稿キュー（data/queue.json）。承認デスクと予約投稿の両方から触るのでロックして読み書きする

状態: pending → approved → publishing → posted
                         ↘ failed / expired
      pending → rejected
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .checks import has_blocking, run_checks

LOCK_TIMEOUT = 10  # 秒
STALE_LOCK = 60    # 秒。これより古いロックは異常終了の残骸として消す
MAX_TEXT = 2000
UNDOABLE = {"approved", "rejected", "failed", "expired"}


class QueueError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def queue_path(root: Path, demo: bool = False) -> Path:
    return Path(root) / "data" / ("queue-demo.json" if demo else "queue.json")


class QueueStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def _read(self) -> dict:
        if not self.path.exists():
            return {"posts": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                os.close(os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return
            except FileExistsError:
                try:
                    if time.time() - self.lock_path.stat().st_mtime > STALE_LOCK:
                        self.lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise QueueError("キューを別の処理が使っています。少し待ってからやり直してください", 503)
                time.sleep(0.05)

    @contextmanager
    def transaction(self):
        """ブロック内で data を書き換えると、例外が出なければ保存される"""
        self._acquire()
        try:
            data = self._read()
            yield data
            self._write(data)
        finally:
            self.lock_path.unlink(missing_ok=True)

    def snapshot(self) -> dict:
        return self._read()

    @staticmethod
    def _find(data: dict, post_id: str) -> dict:
        for post in data["posts"]:
            if post["id"] == post_id:
                return post
        raise QueueError("投稿が見つかりません", 404)

    def add_drafts(self, drafts: list[dict], now: datetime) -> int:
        with self.transaction() as data:
            existing = {p["id"] for p in data["posts"]}
            added = 0
            for draft in drafts:
                if draft["id"] in existing:
                    continue
                data["posts"].append({**draft, "state": "pending", "created_at": now.isoformat()})
                existing.add(draft["id"])
                added += 1
            data["posts"].sort(key=lambda p: p["at"])
        return added

    def update_text(self, post_id: str, text: str) -> dict:
        if len(text) > MAX_TEXT:
            raise QueueError(f"本文が長すぎます（{MAX_TEXT}字まで）", 400)
        with self.transaction() as data:
            post = self._find(data, post_id)
            if post["state"] != "pending":
                raise QueueError("承認待ちの投稿だけ編集できます。先に「承認待ちに戻す」を押してください")
            post["text"] = text
            return dict(post)

    def approve(self, post_id: str, now: datetime) -> dict:
        with self.transaction() as data:
            post = self._find(data, post_id)
            if post["state"] != "pending":
                raise QueueError("承認待ちの投稿だけ承認できます")
            if has_blocking(run_checks(post["text"], fact=post.get("fact"), link_url=post.get("link_url"))):
                raise QueueError("公開前チェックに ✕ があるため承認できません", 422)
            post["state"] = "approved"
            post["approved_at"] = now.isoformat()
            return dict(post)

    def reject(self, post_id: str) -> dict:
        with self.transaction() as data:
            post = self._find(data, post_id)
            if post["state"] != "pending":
                raise QueueError("承認待ちの投稿だけ却下できます")
            post["state"] = "rejected"
            return dict(post)

    def undo(self, post_id: str) -> dict:
        with self.transaction() as data:
            post = self._find(data, post_id)
            if post["state"] not in UNDOABLE:
                raise QueueError("投稿中・投稿済みの投稿は戻せません")
            post["state"] = "pending"
            for key in ("approved_at", "error"):
                post.pop(key, None)
            return dict(post)
