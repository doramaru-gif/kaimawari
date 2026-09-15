"""Threads 投稿キューの操作

python queue_cli.py draft          今日のプランと開催予定から下書きを作る（run_daily.bat から実行）
python queue_cli.py draft --demo   dist-demo のプランで data/queue-demo.json に全期間の下書きを作る
python queue_cli.py list [--demo]  キューの一覧
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

from src.drafts import build_drafts
from src.queue_store import QueueStore, queue_path
from src.schedule import JST, parse_events

ROOT = Path(__file__).resolve().parent
DEMO_HORIZON_HOURS = 24 * 14
log = logging.getLogger("kaimawari.queue")


def notify(webhook: str, count: int) -> None:
    """自分用の通知。アフィリエイトリンクは載せない"""
    message = f"買いまわり帳：承認待ちの Threads 下書きが{count}件増えました。承認デスク（python review_server.py）で確認してください。"
    try:
        requests.post(webhook, json={"content": message}, timeout=10).raise_for_status()
    except requests.RequestException as err:
        log.warning("通知に失敗しました（%s）", type(err).__name__)


def cmd_draft(args, config: dict) -> int:
    out_dir = "dist-demo" if args.demo else config["site"]["out_dir"]
    plan_path = ROOT / out_dir / "data" / "plan.json"
    if not plan_path.exists():
        log.error("%s がありません。先に python main.py%s を実行してください", plan_path, " --demo" if args.demo else "")
        return 1
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if payload.get("demo") and not args.demo:
        log.error("plan.json がサンプルデータです。実データで main.py を実行してから下書きを作ってください")
        return 2

    now = datetime.now(JST)
    horizon = DEMO_HORIZON_HOURS if args.demo else config["threads"]["draft_horizon_hours"]
    site_url = os.getenv("SITE_URL") or "https://example.github.io/kaimawari/"
    drafts = build_drafts(parse_events(config.get("marathon_events")), payload,
                          now=now, horizon_hours=horizon, site_url=site_url)
    added = QueueStore(queue_path(ROOT, args.demo)).add_drafts(drafts, now)
    log.info("下書き %d件（新規 %d件）", len(drafts), added)

    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if added and webhook and not args.demo:
        notify(webhook, added)
    return 0


def cmd_list(args, config: dict) -> int:
    posts = QueueStore(queue_path(ROOT, args.demo)).snapshot()["posts"]
    if not posts:
        print("キューは空です")
    for post in posts:
        print(f'{post["at"][:16].replace("T", " ")}  {post["state"]:<10}  {post["kind"]}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Threads 投稿キューの操作")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("draft", "list"):
        p = sub.add_parser(name)
        p.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return {"draft": cmd_draft, "list": cmd_list}[args.command](args, config)


if __name__ == "__main__":
    sys.exit(main())
