"""承認デスク（ローカル専用）

python review_server.py          http://127.0.0.1:8766 で data/queue.json を承認する
python review_server.py --demo   data/queue-demo.json を使う（投稿はされない）
"""

import argparse
import json
import os
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

from src.queue_store import QueueStore, queue_path
from src.review_api import handle, is_local_request
from src.schedule import JST, parse_events

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "src" / "review_ui"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/desk.css": ("desk.css", "text/css; charset=utf-8"),
}
MAX_BODY = 20_000


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "kaimawari-review"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _local(self) -> bool:
        if is_local_request(self.headers.get("Host"), self.headers.get("Origin"), self.server.port):
            return True
        self._json(403, {"error": "このデスクは 127.0.0.1 からだけ使えます"})
        return False

    def _api(self, method: str, path: str, body) -> None:
        status, payload = handle(self.server.store, self.server.events, method, path, body, datetime.now(JST),
                                 threads_ready=self.server.threads_ready, demo=self.server.demo)
        self._json(status, payload)

    def do_GET(self) -> None:
        if not self._local():
            return
        path = urlparse(self.path).path
        if path in STATIC:
            name, content_type = STATIC[path]
            self._send(200, (UI_DIR / name).read_bytes(), content_type)
        elif path.startswith("/api/"):
            self._api("GET", path, None)
        else:
            self._json(404, {"error": "見つかりません"})

    def do_POST(self) -> None:
        if not self._local():
            return
        if self.headers.get("X-Kaimawari") != "1":
            self._json(403, {"error": "承認デスクの画面から操作してください"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json(413, {"error": "送信内容が大きすぎます"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json(400, {"error": "JSON を送ってください"})
            return
        self._api("POST", urlparse(self.path).path, body)

    def log_message(self, format, *args) -> None:  # noqa: A002 - 標準ライブラリの引数名
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Threads 投稿の承認デスク")
    parser.add_argument("--demo", action="store_true", help="デモ用キューを使う")
    parser.add_argument("--port", type=int, help="ポート番号（既定は config.yaml）")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    port = args.port or config["threads"]["review_port"]

    server = ThreadingHTTPServer(("127.0.0.1", port), ReviewHandler)
    server.port = port
    server.demo = args.demo
    server.store = QueueStore(queue_path(ROOT, args.demo))
    server.events = parse_events(config.get("marathon_events"))
    server.threads_ready = bool(os.getenv("THREADS_ACCESS_TOKEN") and os.getenv("THREADS_USER_ID")) and not args.demo

    print(f"承認デスク: http://127.0.0.1:{port}{'（デモ）' if args.demo else ''}  Ctrl+C で終了", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
