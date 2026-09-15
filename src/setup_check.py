"""本番運用前の設定チェック。APIは読み取りだけ呼ぶ（投稿はしない）"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from .rakuten_api import RakutenApiError, RakutenClient
from .schedule import format_period, next_event, parse_events
from .threads_api import ThreadsApiError, ThreadsClient, TokenStore

ENV_KEYS = (
    "RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY", "RAKUTEN_AFFILIATE_ID", "SITE_URL",
    "THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "DISCORD_WEBHOOK_URL",
)
PLACEHOLDER_HOSTS = ("example.github.io", "example.com")
TASKS = ("kaimawari-daily", "kaimawari-publish")


def _ok(label: str, message: str) -> dict:
    return {"label": label, "status": "ok", "message": message}


def _warn(label: str, message: str) -> dict:
    return {"label": label, "status": "warn", "message": message}


def _block(label: str, message: str) -> dict:
    return {"label": label, "status": "block", "message": message}


def check_env(env: dict) -> list[dict]:
    results = []
    required = (
        ("RAKUTEN_APP_ID", "楽天 アプリID"),
        ("RAKUTEN_ACCESS_KEY", "楽天 アクセスキー"),
        ("RAKUTEN_AFFILIATE_ID", "楽天 アフィリエイトID"),
        ("THREADS_ACCESS_TOKEN", "Threads アクセストークン"),
        ("THREADS_USER_ID", "Threads ユーザーID"),
    )
    for key, label in required:
        results.append(_ok(label, "設定済み") if env.get(key) else _block(label, f".env の {key} が空です"))

    site = env.get("SITE_URL") or ""
    if not site:
        results.append(_block("公開URL", ".env の SITE_URL が空です"))
    elif any(host in site for host in PLACEHOLDER_HOSTS):
        results.append(_block("公開URL", "SITE_URL がサンプルのままです。GitHub Pages の公開URLに変えてください"))
    elif not site.startswith("https://"):
        results.append(_warn("公開URL", "https:// で始まるURLにしてください"))
    else:
        results.append(_ok("公開URL", site))

    if env.get("DISCORD_WEBHOOK_URL"):
        results.append(_ok("Discord 通知", "設定済み"))
    else:
        results.append(_ok("Discord 通知", "未設定（任意。通知なしで動きます）"))
    return results


def check_rakuten(env: dict, session=None) -> list[dict]:
    if not (env.get("RAKUTEN_APP_ID") and env.get("RAKUTEN_ACCESS_KEY") and env.get("SITE_URL")):
        return [_block("楽天API 接続", "アプリID・アクセスキー・SITE_URL を入れると確認できます")]
    try:
        client = RakutenClient(app_id=env["RAKUTEN_APP_ID"], access_key=env["RAKUTEN_ACCESS_KEY"],
                               affiliate_id=env.get("RAKUTEN_AFFILIATE_ID"), referer=env["SITE_URL"], session=session)
        items = client.search(keyword="1000円ポッキリ", hits=3, postageFlag=1, availability=1)
    except RakutenApiError as err:
        message = str(err)
        if "HTTP 400" in message or "HTTP 403" in message:
            message += "。「許可されたWebサイト」に SITE_URL と同じURLが登録されているか、アクセスキーが正しいか確認してください"
        return [_block("楽天API 接続", message)]

    results = [_ok("楽天API 接続", f"商品検索できました（{len(items)}件）")]
    if not items:
        results.append(_warn("アフィリエイトリンク", "商品が0件だったため確認できませんでした"))
    elif any(item["has_affiliate"] for item in items):
        results.append(_ok("アフィリエイトリンク", "affiliateUrl が付いています"))
    else:
        results.append(_block("アフィリエイトリンク", "affiliateUrl が返っていません。RAKUTEN_AFFILIATE_ID を確認してください"))
    return results


def check_threads(env: dict, token_path: Path, session=None) -> list[dict]:
    token = TokenStore(token_path, env.get("THREADS_ACCESS_TOKEN")).current()
    if not token:
        return [_block("Threads 接続", "アクセストークンを入れると確認できます")]
    user_id = env.get("THREADS_USER_ID")
    client = ThreadsClient(access_token=token, user_id=user_id or "me", session=session)
    try:
        me = client.me()
    except ThreadsApiError as err:
        return [_block("Threads 接続", f"{err}。トークンの期限切れや、threads_basic / threads_content_publish の権限を確認してください")]

    owner_id = str(me.get("id", ""))
    results = [_ok("Threads 接続", f"@{me.get('username', '?')} として接続できました")]
    if not user_id:
        results.append(_block("Threads ユーザーID", f".env の THREADS_USER_ID に {owner_id} を入れてください"))
        return results
    if user_id != owner_id:
        results.append(_block("Threads ユーザーID", f"トークンの持ち主のID（{owner_id}）と一致しません"))
        return results
    results.append(_ok("Threads ユーザーID", "トークンの持ち主と一致しています"))
    try:
        used, total = client.publishing_quota()
        results.append(_ok("Threads 投稿枠", f"24時間で {used} / {total} 件使用"))
    except ThreadsApiError as err:
        results.append(_warn("Threads 投稿枠", f"確認できませんでした（{err}）。threads_content_publish の権限を確認してください"))
    return results


def check_schedule(config: dict, now: datetime) -> list[dict]:
    event = next_event(parse_events(config.get("marathon_events")), now)
    if not event:
        return [_block("開催予定", "これから開催されるマラソンが config.yaml にありません。告知を見て追記してください")]
    return [_ok("開催予定", f"{event.name}：{format_period(event)}（ボーナス上限 {event.point_cap:,}pt）")]


def check_local(root: Path, run=subprocess.run) -> list[dict]:
    results = []
    if not (Path(root) / ".git").exists():
        results.append(_warn("GitHub Pages", "Git リポジトリがないため、サイトは公開されません"))
    else:
        try:
            remote = run(["git", "-C", str(root), "remote"], capture_output=True, text=True).stdout.strip()
        except OSError:
            remote = ""
        results.append(_ok("GitHub Pages", f"リモート {remote} に push します") if remote
                       else _warn("GitHub Pages", "Git のリモートが未設定です"))

    for name in TASKS:
        try:
            registered = run(["schtasks", "/Query", "/TN", name], capture_output=True, text=True).returncode == 0
        except OSError:
            registered = False
        results.append(_ok(f"タスク {name}", "登録済み") if registered
                       else _warn(f"タスク {name}", "未登録です（CLAUDE.md のコマンドで登録）"))
    return results
