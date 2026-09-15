"""定期連携用の状況メモを表示する

python status.py                そのまま表示
python status.py --note "〇〇"  相談したいことを添える
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.queue_store import queue_path
from src.schedule import JST, parse_events, upcoming_summary
from src.status import build_status

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="定期連携用の状況メモ")
    parser.add_argument("--note", default="", help="相談したいこと")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    now = datetime.now(JST)

    print(build_status(
        plan_path=ROOT / config["site"]["out_dir"] / "data" / "plan.json",
        queue_path=queue_path(ROOT),
        history_path=ROOT / "data" / "history.json",
        site_url=os.getenv("SITE_URL") or "（未設定）",
        threads_ready=bool(os.getenv("THREADS_ACCESS_TOKEN") and os.getenv("THREADS_USER_ID")),
        calendar=upcoming_summary(parse_events(config.get("marathon_events")), now),
        now=now,
        notes=args.note,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
