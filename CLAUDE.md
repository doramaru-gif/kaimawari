# 買いまわり帳（kaimawari）

## 概要
楽天お買い物マラソン向けの収益化パイプライン。収益は楽天アフィリエイト。

1. **サイト（承認なし・毎朝自動）** … 楽天市場の公式APIから「送料込み・1,000円台」の商品を集め、
   別々の10ショップで組んだ買いまわりプランを静的サイトとして書き出す
   - `index.html` … プラン（安い順／レビュー順）、倍率計算機、候補の棚
   - `rakuyoko.html` … ラクヨコ送料無料ライン計算機（2,100〜16,666円の判定と注文の分け方）
   - `data/plan.json` … Threads 下書きの材料
2. **Threads 投稿（承認のみ）** … 開催予定とプランから下書きを自動生成 → 承認デスクで承認 → 予約時刻に自動投稿

進捗と再開手順は `docs/PROGRESS.md`、本番運用までの手順は `docs/SETUP.md`。

## 規約上やってはいけないこと（2026年9月時点で確認済み）
- ラクヨコの商品ページを自動で取得しない（ラクヨコ利用規約 第13条7号）
- ラクヨコの商品画像・商品データを転載しない（同 第13条20号）→ ラクヨコは計算機と公式発表の事実だけ扱う
- ブラウザ拡張で楽天グループのサイト上に情報を表示しない（楽天アフィリエイトガイドライン）
- 楽天ROOMを自動投稿しない（ROOM規約でプログラムによる投稿を禁止）
- 楽天のページをスクショした画像を使わない。API画像は無加工で使う
- アフィリエイトリンクをメール・LINE・DM・Discord に載せない（通知には件数だけ送る）
- PR表記を外さない（サイトは上部とフッター、Threads は本文の #PR）
- 承認されていない投稿は出さない。公開前チェックに ✕ がある投稿は承認も投稿もできない

## 技術スタック
- Python 3.11+（requests / python-dotenv / PyYAML）。承認デスクは標準ライブラリの http.server
- 楽天市場商品検索API `openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701`
  - applicationId と accessKey が必須。Referer ヘッダ必須（「許可されたWebサイト」に SITE_URL のドメインを登録）
  - 1秒1リクエストを超えない。429 はバックオフして再試行
- Threads API `graph.threads.net/v1.0`
  - テキスト投稿：`/{user-id}/threads`（media_type=TEXT, text, link_attachment）→ 約30秒待つ → `/{user-id}/threads_publish`
  - 500字まで、リンク5個まで、24時間で250投稿まで
  - 長期トークン（60日）は `refresh_access_token`（grant_type=th_refresh_token）で7日ごとに更新
- 下書きはテンプレート生成（LLM API は使わないので費用ゼロ）
- 公開は GitHub Pages。Pages は dist/ を直接公開できないので `.github/workflows/pages.yml`（Actions）で公開する

## セットアップ（人がやるのはここだけ）
詳しい手順は `docs/SETUP.md`。各ステップのあとに `python setup_check.py` で確認する。
1. GitHub に公開リポジトリ `kaimawari` を作り、公開URL `https://<ユーザー名>.github.io/kaimawari/` を `.env` の SITE_URL に入れる
2. 楽天ウェブサービスでアプリ登録（許可されたWebサイト＝`<ユーザー名>.github.io`）→ アプリID・アクセスキー・アフィリエイトID
3. Meta for Developers で Threads のテスター登録 → User Token Generator で長期トークン → setup_check が表示するユーザーIDを入れる
4. `python main.py` で実データを確認 → push → Settings → Pages の Source を「GitHub Actions」にする
5. タスクスケジューラに登録
```bash
schtasks /Create /TN "kaimawari-daily" /TR "C:\Users\doram\Desktop\Claude\apps\kaimawari\run_daily.bat" /SC DAILY /ST 05:30
```
```bash
schtasks /Create /TN "kaimawari-publish" /TR "C:\Users\doram\Desktop\Claude\apps\kaimawari\run_publish.bat" /SC MINUTE /MO 10
```
6. 任意：`rakuyoko.affiliate_url`、`DISCORD_WEBHOOK_URL`、開催告知に合わせた `marathon_events` の更新

## 実行
```bash
python setup_check.py              # 本番運用前の設定チェック（--offline でAPIを呼ばない）
python main.py --demo              # サンプルデータで dist-demo/ に書き出し（APIキー不要）
python main.py                     # 実データで dist/ に書き出し
python queue_cli.py draft          # 36時間以内の投稿枠の下書きを作る
python queue_cli.py draft --demo   # デモ用キューに全期間の下書きを作る
python review_server.py            # 承認デスク http://127.0.0.1:8766（--demo でデモ用キュー）
python publish_due.py --dry-run    # 何が投稿されるか確認だけ
python -m pytest -q
```

## 毎日の流れ
- 05:30 `run_daily.bat`：サイト生成 → 下書き生成（Discord に件数通知）→ dist/ を push（Actions が公開）
- 人：承認デスクを開いて、承認か却下（本文はその場で直せる）
- 10分おき `run_publish.bat`：予約時刻が来た承認済みだけ投稿。3時間過ぎたものは「期限切れ」、
  投稿中のまま30分たったものは二重投稿を避けて「失敗」にする

## ファイル構成
- `main.py` … 取得 → プラン作成 → 書き出し
- `queue_cli.py` / `review_server.py` / `publish_due.py` … 下書き・承認デスク・予約投稿
- `setup_check.py` / `src/setup_check.py` … 設定チェック
- `src/rakuten_api.py` / `planner.py` / `site_builder.py` / `assets/` … サイト
- `src/og_image.py` … OGP画像（Windows の游ゴシック等で描画。フォントが無ければ作らず警告）
- `src/history.py` … 毎朝の選定記録 `data/history.json`（demo は history-demo.json）
- `src/schedule.py` … 開催予定と投稿枠
- `src/drafts.py` … 下書きテンプレート
- `src/checks.py` … 公開前チェック（PR表記・500字・誇大表現・リンク・出典）
- `src/queue_store.py` … `data/queue.json`（ロック付き。data/ は Git に入れない）
- `src/threads_api.py` / `publisher.py` … 投稿とトークン更新
- `src/review_api.py` / `review_ui/` … 承認デスクのAPIと画面
- `.github/workflows/pages.yml` … dist/ を GitHub Pages に公開
- `fixtures/sample_search.json` … デモ用サンプル（実在しない商品）
- `mock/approval-queue.html` … 承認デスクの最初のモック
- `docs/SETUP.md` / `docs/PROGRESS.md` … 手順書と進捗
