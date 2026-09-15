"""予約時刻が来た承認済みの投稿を Threads に出す（run_publish.bat から10分おきに実行）

python publish_due.py            投稿する（トークン未設定なら確認だけ）
python publish_due.py --dry-run  何が投稿されるかをログに出すだけ
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.publisher import publish_due
from src.queue_store import QueueError, QueueStore, queue_path
from src.schedule import JST
from src.threads_api import ThreadsApiError, ThreadsClient, TokenStore

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("kaimawari.publish")


def main() -> int:
    parser = argparse.ArgumentParser(description="承認済みの Threads 投稿を公開する")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    threads_conf = config["threads"]
    now = datetime.now(JST)

    store = QueueStore(queue_path(ROOT))
    waiting = [p for p in store.snapshot().get("posts", []) if p["state"] in ("approved", "publishing")]
    if not waiting:
        # 10分おきに動くので、予約が無いときは静かに終わる
        log.info("投稿の予約はありません")
        return 0

    tokens = TokenStore(ROOT / "data" / "threads_token.json", os.getenv("THREADS_ACCESS_TOKEN"))
    user_id = os.getenv("THREADS_USER_ID")
    dry_run = args.dry_run
    client = None
    if not dry_run and not (tokens.current() and user_id):
        log.warning("THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定のため、投稿せずに確認だけ行います")
        dry_run = True
    if not dry_run:
        try:
            if tokens.refresh_if_due(now, threads_conf["token_refresh_days"]):
                log.info("Threads のアクセストークンを更新しました")
        except ThreadsApiError as err:
            log.warning("トークンの更新に失敗しました。今のトークンで続けます: %s", err)
        client = ThreadsClient(access_token=tokens.current(), user_id=user_id)

    try:
        results = publish_due(store, client, now=now,
                              grace_minutes=threads_conf["publish_grace_minutes"], dry_run=dry_run)
    except QueueError as err:
        log.error("%s", err)
        return 1

    for result in results:
        detail = result.get("post_id") or result.get("error") or ""
        log.info("%s: %s %s", result["id"], result["result"], detail)
    return 1 if any(r["result"] == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
