"""本番運用前の設定チェック（投稿はしない。楽天とThreadsのAPIを読み取りで1回ずつ呼ぶ）

python setup_check.py            全部チェック
python setup_check.py --offline  APIを呼ばずに .env・開催予定・自動化の設定だけ見る
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.schedule import JST
from src.setup_check import ENV_KEYS, check_env, check_local, check_rakuten, check_schedule, check_threads

ROOT = Path(__file__).resolve().parent
MARKS = {"ok": "✓", "warn": "!", "block": "✕"}


def main() -> int:
    parser = argparse.ArgumentParser(description="本番運用前の設定チェック")
    parser.add_argument("--offline", action="store_true", help="APIを呼ばない")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env", override=True)
    env = {key: (os.getenv(key) or "").strip() for key in ENV_KEYS}
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

    sections = [("設定（.env）", check_env(env))]
    if not args.offline:
        sections.append(("楽天API", check_rakuten(env)))
        sections.append(("Threads", check_threads(env, ROOT / "data" / "threads_token.json")))
    sections.append(("開催予定", check_schedule(config, datetime.now(JST))))
    sections.append(("自動化", check_local(ROOT)))

    blocking = 0
    for title, results in sections:
        print(f"\n■ {title}")
        for result in results:
            print(f"  {MARKS[result['status']]} {result['label']}：{result['message']}")
            blocking += result["status"] == "block"

    print("\n" + ("本番運用できます。" if not blocking else f"✕ が {blocking} 件あります。上から順に直してください。"))
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
