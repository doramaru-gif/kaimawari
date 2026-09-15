"""買いまわり帳: 楽天市場APIから候補を集め、買いまわりプランの静的サイトを書き出す

python main.py --demo      サンプルデータで dist-demo/ に書き出す（APIキー不要）
python main.py --dry-run   実データでプランをログに出すだけ
python main.py             実データで dist/ に書き出す
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.history import record_history
from src.planner import STRATEGIES, pick_items, summarize
from src.rakuten_api import RakutenApiError, RakutenClient, parse_items
from src.schedule import JST, format_period, next_event, parse_events
from src.site_builder import build_site

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("kaimawari")


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def apply_next_event(config: dict, now: datetime) -> None:
    """開催予定があれば、サイトの「次回」表示とボーナス上限をその回に合わせる"""
    event = next_event(parse_events(config.get("marathon_events")), now)
    if event:
        config["marathon"]["next_period"] = format_period(event)
        config["marathon"]["point_cap"] = event.point_cap


def build_search_params(search: dict, query: dict) -> dict:
    """1枠ぶんの商品検索パラメータ。genre_id があればジャンルで絞り、別カテゴリの商品が混ざらないようにする"""
    params = {
        "keyword": query["keyword"],
        "minPrice": search["min_price"],
        "maxPrice": search["max_price"],
        "postageFlag": 1,
        "availability": 1,
        "hits": search["hits"],
        "sort": "-reviewCount",
        "NGKeyword": search["ng_keyword"],
    }
    if query.get("genre_id"):
        params["genreId"] = int(query["genre_id"])
    return params


def collect_candidates(config: dict, demo: bool) -> list[dict]:
    search = config["search"]
    if demo:
        fixture = json.loads((ROOT / "fixtures" / "sample_search.json").read_text(encoding="utf-8"))
    else:
        client = RakutenClient(
            app_id=os.getenv("RAKUTEN_APP_ID"),
            access_key=os.getenv("RAKUTEN_ACCESS_KEY"),
            affiliate_id=os.getenv("RAKUTEN_AFFILIATE_ID"),
            referer=os.getenv("SITE_URL"),
        )

    candidates = []
    for query in search["queries"]:
        label = query["label"]
        try:
            if demo:
                items = parse_items(fixture.get(label, {}))
            else:
                items = client.search(**build_search_params(search, query))
        except RakutenApiError as err:
            log.error("%s の取得に失敗: %s", label, err)
            continue
        for item in items:
            item["label"] = label
        log.info("%s: %d件", label, len(items))
        candidates.extend(items)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="買いまわり帳のサイトを生成する")
    parser.add_argument("--demo", action="store_true", help="サンプルデータで作る（APIキー不要）")
    parser.add_argument("--dry-run", action="store_true", help="プランをログに出すだけでファイルを書かない")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    config = load_config()
    now = datetime.now(JST)
    apply_next_event(config, now)

    try:
        candidates = collect_candidates(config, args.demo)
    except RakutenApiError as err:
        log.error("%s", err)
        return 2
    if not candidates:
        log.error("候補が0件でした。前回のサイトを残して終了します")
        return 1

    marathon = config["marathon"]
    plans = {}
    for strategy in STRATEGIES:
        items = pick_items(
            candidates,
            strategy=strategy,
            shops_target=marathon["shops_target"],
            min_per_shop=marathon["min_per_shop"],
            min_reviews=config["search"]["min_review_count"],
        )
        plan = summarize(items, strategy=strategy, shops_target=marathon["shops_target"],
                         point_cap=marathon["point_cap"])
        plans[strategy] = plan
        log.info("[%s] %dショップ 合計¥%s 見込み%spt", strategy, plan.shops, f"{plan.total:,}", f"{plan.points:,}")

    if args.dry_run:
        return 0

    history = record_history(ROOT / "data" / ("history-demo.json" if args.demo else "history.json"),
                             plans, len(candidates), now)
    out_dir = ROOT / (config["site"]["out_dir"] + ("-demo" if args.demo else ""))
    warnings = build_site(out_dir, config=config, plans=plans, candidates=candidates, generated_at=now,
                          demo=args.demo, site_url=None if args.demo else os.getenv("SITE_URL"), history=history)
    for warning in warnings:
        log.warning("%s", warning)
    log.info("書き出しました: %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
