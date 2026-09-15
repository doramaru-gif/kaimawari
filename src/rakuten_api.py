"""楽天市場 商品検索API クライアント（2026年の新仕様 openapi.rakuten.co.jp）"""

from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
MIN_INTERVAL = 1.1  # 秒。1秒1リクエストを超えない
MAX_RETRIES = 4
RETRY_STATUS = {429, 500, 503}


class RakutenApiError(Exception):
    pass


def parse_items(data: dict) -> list[dict]:
    """APIレスポンスを扱いやすい形にそろえる（formatVersion 1 と 2 の両方に対応）"""
    raw = data.get("Items") or data.get("items") or []
    items = []
    for entry in raw:
        item = entry.get("Item", entry) if isinstance(entry, dict) else {}
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
            "point_rate": int(item.get("pointRate", 1)),
        })
    return items


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

    def search(self, **params) -> list[dict]:
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
                res = self.session.get(SEARCH_URL, params=query, headers=self._headers, timeout=20)
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
            if res.status_code != 200 or "error" in data:
                detail = f"{data.get('error', '')}: {data.get('error_description', '')}".strip(": ")
                raise RakutenApiError(f"HTTP {res.status_code} {detail}".strip())
            return parse_items(data)

        raise RakutenApiError(f"HTTP {res.status_code} が{MAX_RETRIES}回続いたため中断しました")
