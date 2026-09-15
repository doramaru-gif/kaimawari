"""楽天ウェブサービス API クライアント（2026年の新仕様 openapi.rakuten.co.jp）

楽天市場の商品検索・ランキングと、楽天ブックス・楽天Kobo の検索を扱う。
どれも applicationId と accessKey、Referer ヘッダが必要。
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
RANKING_URL = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
BOOKS_URL = "https://openapi.rakuten.co.jp/services/api/BooksTotal/Search/20170404"
KOBO_URL = "https://openapi.rakuten.co.jp/services/api/Kobo/EbookSearch/20170426"
MIN_INTERVAL = 1.1  # 秒。1秒1リクエストを超えない
MAX_RETRIES = 4
RETRY_STATUS = {429, 500, 503}


class RakutenApiError(Exception):
    pass


def _error_detail(data: dict) -> str:
    """旧形式 {error, error_description} と新形式 {errors: {errorCode, errorMessage}} の両方から理由を取り出す"""
    errors = data.get("errors")
    if isinstance(errors, dict):
        return str(errors.get("errorMessage", ""))
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        return str(errors[0].get("errorMessage", ""))
    return f"{data.get('error', '')}: {data.get('error_description', '')}".strip(": ")


def _entries(data: dict, wrapper: str) -> list[dict]:
    raw = data.get("Items") or data.get("items") or []
    return [entry.get(wrapper, entry) for entry in raw if isinstance(entry, dict)]


def parse_items(data: dict) -> list[dict]:
    """楽天市場の商品検索・ランキングのレスポンスをそろえる（formatVersion 1 と 2 の両方に対応）"""
    items = []
    for item in _entries(data, "Item"):
        images = [u.get("imageUrl", "") if isinstance(u, dict) else u for u in item.get("mediumImageUrls", [])]
        affiliate_url = item.get("affiliateUrl") or ""
        items.append({
            "name": item.get("itemName", ""),
            "item_code": item.get("itemCode", ""),
            "price": int(item.get("itemPrice", 0)),
            "tax_included": int(item.get("taxFlag", 0)) == 0,
            "postage_included": int(item.get("postageFlag", 1)) == 0,
            "url": affiliate_url or item.get("itemUrl", ""),
            "has_affiliate": bool(affiliate_url),
            "shop_name": item.get("shopName", ""),
            "shop_code": item.get("shopCode", ""),
            "image": next((u for u in images if u), ""),
            "review_count": int(item.get("reviewCount", 0)),
            "review_average": float(item.get("reviewAverage", 0)),
            # 倍率と期間。期限切れの倍率も返ってくるので、使う前に planner.apply_point_rates で判定する
            "point_rate": int(item.get("pointRate") or 1),
            "point_rate_start": item.get("pointRateStartTime") or "",
            "point_rate_end": item.get("pointRateEndTime") or "",
            "shop_of_the_year": int(item.get("shopOfTheYearFlag") or 0) == 1,
            "rank": int(item.get("rank") or 0),
        })
    return items


def parse_books(data: dict) -> list[dict]:
    """楽天ブックス・楽天Kobo の検索レスポンスをそろえる"""
    books = []
    for item in _entries(data, "Item"):
        affiliate_url = item.get("affiliateUrl") or ""
        books.append({
            "name": item.get("title", ""),
            "author": item.get("author", ""),
            "price": int(item.get("itemPrice") or 0),
            "url": affiliate_url or item.get("itemUrl", ""),
            "has_affiliate": bool(affiliate_url),
            "image": item.get("mediumImageUrl") or item.get("largeImageUrl") or "",
            "sales_date": item.get("salesDate") or "",
            "review_count": int(item.get("reviewCount") or 0),
            "review_average": float(item.get("reviewAverage") or 0),
        })
    return books


class RakutenClient:
    def __init__(self, *, app_id: str | None, access_key: str | None, affiliate_id: str | None,
                 referer: str | None, session: requests.Session | None = None):
        if not (app_id and access_key and referer):
            raise RakutenApiError(
                ".env に RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY / SITE_URL を設定してください"
                "（SITE_URL は楽天デベロッパーの「許可されたWebサイト」に登録したURL）"
            )
        self.app_id = app_id
        self.access_key = access_key
        self.affiliate_id = affiliate_id
        parsed = urlparse(referer)
        self._headers = {"Referer": referer, "Origin": f"{parsed.scheme}://{parsed.netloc}"}
        self.session = session or requests.Session()
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = MIN_INTERVAL - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def _get(self, url: str, params: dict) -> dict:
        query = {
            "applicationId": self.app_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": 2,
            **params,
        }
        if self.affiliate_id:
            query["affiliateId"] = self.affiliate_id

        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                res = self.session.get(url, params=query, headers=self._headers, timeout=20)
            except requests.RequestException as err:
                # 例外メッセージにはアクセスキー入りのURLが含まれるので出さない
                raise RakutenApiError(f"楽天APIに接続できませんでした（{type(err).__name__}）") from None
            self._last_request = time.monotonic()
            if res.status_code in RETRY_STATUS:
                time.sleep(2 ** (attempt + 1))
                continue
            try:
                data = res.json()
            except ValueError:
                data = {}
            if res.status_code != 200 or "error" in data or "errors" in data:
                raise RakutenApiError(f"HTTP {res.status_code} {_error_detail(data)}".strip())
            return data

        raise RakutenApiError(f"HTTP {res.status_code} が{MAX_RETRIES}回続いたため中断しました")

    def search(self, **params) -> list[dict]:
        return parse_items(self._get(SEARCH_URL, params))

    def ranking(self, **params) -> list[dict]:
        """デイリーランキング。順位の昇順で返す"""
        items = parse_items(self._get(RANKING_URL, params))
        return sorted(items, key=lambda it: it["rank"] or 10**6)

    def books(self, **params) -> list[dict]:
        return parse_books(self._get(BOOKS_URL, params))

    def kobo(self, **params) -> list[dict]:
        return parse_books(self._get(KOBO_URL, params))
