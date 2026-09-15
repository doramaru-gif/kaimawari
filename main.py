"""買いまわり帳: 楽天のAPIから候補を集め、買いまわりプランの静的サイトを書き出す

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

from src.extras import pick_books
from src.history import record_history
from src.planner import STRATEGIES, apply_point_rates, pick_items, summarize
from src.rakuten_api import RakutenApiError, RakutenClient, parse_items
from src.schedule import JST, format_period, next_event, parse_events
from src.site_builder import build_site

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("kaimawari")


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def apply_next_event(config: dict, now: datetime):
    """開催予定があれば、サイトの「次回」表示とボーナス上限をその回に合わせ、その回を返す"""
    event = next_event(parse_events(config.get("marathon_events")), now)
    if event:
        config["marathon"]["next_period"] = format_period(event)
        config["marathon"]["point_cap"] = event.point_cap
    return event


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


def make_client() -> RakutenClient:
    return RakutenClient(
        app_id=os.getenv("RAKUTEN_APP_ID"),
        access_key=os.getenv("RAKUTEN_ACCESS_KEY"),
        affiliate_id=os.getenv("RAKUTEN_AFFILIATE_ID"),
        referer=os.getenv("SITE_URL"),
    )


def collect_candidates(config: dict, client: RakutenClient | None) -> list[dict]:
    """client が None のときはサンプルデータを使う"""
    search = config["search"]
    fixture = json.loads((ROOT / "fixtures" / "sample_search.json").read_text(encoding="utf-8")) if client is None else None

    candidates = []
    for query in search["queries"]:
        label = query["label"]
        params = build_search_params(search, query)
        # ポイント倍率アップ中の商品は数が少なく、レビュー順の上位に出にくいので別に探す
        variants = [params, {**params, "pointRateFlag": 1}] if client and search.get("include_point_up") else [params]
        found = 0
        for variant in variants:
            try:
                items = parse_items(fixture.get(label, {})) if client is None else client.search(**variant)
            except RakutenApiError as err:
                log.error("%s の取得に失敗: %s", label, err)
                continue
            for item in items:
                item["label"] = label
            candidates.extend(items)
            found += len(items)
        log.info("%s: %d件", label, found)
    return candidates


def collect_extras(config: dict, client: RakutenClient | None, now: datetime, shop_at: datetime | None = None) -> dict:
    """本命探しの売れ筋と、楽天ブックス・楽天Koboの本。どれかが失敗してもサイトは作る"""
    extras = {"rankings": [], "books": [], "kobo": []}
    conf = config.get("extras") or {}
    if client is None:
        return extras

    for tab in conf.get("rankings", []):
        params = {key: tab[key] for key in ("age", "sex", "genreId", "period") if key in tab}
        try:
            items = client.ranking(**params)
        except RakutenApiError as err:
            log.error("売れ筋（%s）の取得に失敗: %s", tab["label"], err)
            continue
        apply_point_rates(items, shop_at or now)
        extras["rankings"].append({"label": tab["label"], "items": items[: conf.get("ranking_limit", 10)]})

    shelves = (("books", client.books, "booksGenreId", "sales"), ("kobo", client.kobo, "koboGenreId", "reviewCount"))
    for key, fetch, genre_param, default_sort in shelves:
        shelf = conf.get(key)
        if not shelf:
            continue
        params = {genre_param: shelf["genre_id"], "sort": shelf.get("sort", default_sort), "hits": 30, **shelf.get("params", {})}
        try:
            found = fetch(**params)
        except RakutenApiError as err:
            log.error("%s の取得に失敗: %s", key, err)
            continue
        extras[key] = pick_books(found, min_price=config["marathon"]["min_per_shop"], today=now.date(),
                                 limit=shelf.get("limit", 6))

    log.info("売れ筋 %d種類、楽天ブックス %d冊、楽天Kobo %d冊",
             len(extras["rankings"]), len(extras["books"]), len(extras["kobo"]))
    return extras


def main() -> int:
    parser = argparse.ArgumentParser(description="買いまわり帳のサイトを生成する")
    parser.add_argument("--demo", action="store_true", help="サンプルデータで作る（APIキー不要）")
    parser.add_argument("--dry-run", action="store_true", help="プランをログに出すだけでファイルを書かない")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(ROOT / ".env")
    config = load_config()
    now = datetime.now(JST)
    event = apply_next_event(config, now)
    # 買う時点（開催前なら開始時刻）にもポイント倍率が続く商品だけを「倍率アップ」として扱う
    shop_at = max(now, event.start) if event else now

    try:
        client = None if args.demo else make_client()
    except RakutenApiError as err:
        log.error("%s", err)
        return 2

    candidates = collect_candidates(config, client)
    if not candidates:
        log.error("候補が0件でした。前回のサイトを残して終了します")
        return 1
    apply_point_rates(candidates, shop_at)

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

    extras = collect_extras(config, client, now, shop_at)
    history = record_history(ROOT / "data" / ("history-demo.json" if args.demo else "history.json"),
                             plans, len(candidates), now)
    out_dir = ROOT / (config["site"]["out_dir"] + ("-demo" if args.demo else ""))
    warnings = build_site(out_dir, config=config, plans=plans, candidates=candidates, generated_at=now,
                          demo=args.demo, site_url=None if args.demo else os.getenv("SITE_URL"),
                          history=history, extras=extras)
    for warning in warnings:
        log.warning("%s", warning)
    log.info("書き出しました: %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
