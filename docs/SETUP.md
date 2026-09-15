# 本番運用までの手順

上から順に進める。各ステップの最後に `python setup_check.py` を実行すると、どこまで通ったか分かる。
9月の回（9/19 20:00開始）に間に合わせるなら、**9/18 の朝までに 1〜5 を終える**
（前日告知の枠は 9/18 21:00）。

## 1. 公開URLを決める（GitHub）
楽天の「許可されたWebサイト」に登録するURLが先に必要なので、最初にリポジトリを作る。

1. GitHub で **公開（Public）** リポジトリ `kaimawari` を作る（無料プランの Pages は公開リポジトリのみ）
2. 公開URLは `https://<GitHubユーザー名>.github.io/kaimawari/` になる
3. `.env` の `SITE_URL` にこのURLを入れる（末尾の `/` まで）

リポジトリに入るのはコードと `dist/` だけ。`.env`・`data/`（投稿キューとトークン）・`logs/` は `.gitignore` で除外済み。

## 2. 楽天ウェブサービス
1. https://webservice.rakuten.co.jp/ に楽天会員でログインし、アプリを新規登録する
   - アプリの種類：Webアプリケーション
   - アプリURL：手順1の公開URL
   - 許可されたWebサイト：`<GitHubユーザー名>.github.io`（https:// は付けない）
2. 登録したアプリの画面に出る **アプリID** と **アクセスキー** を `.env` の `RAKUTEN_APP_ID` / `RAKUTEN_ACCESS_KEY` に入れる
3. 同じサイトで確認できる **アフィリエイトID** を `RAKUTEN_AFFILIATE_ID` に入れる
4. `python setup_check.py` で「楽天API 接続」と「アフィリエイトリンク」が ✓ になるのを確認
   - ✕ で HTTP 400/403 のときは、許可されたWebサイトと SITE_URL のドメインが一致しているかを見る

## 3. Threads
1. https://developers.facebook.com/ でアプリを作り、ユースケースで「Threads API にアクセス」を選ぶ
2. 権限に `threads_basic` と `threads_content_publish` を追加する
3. アプリの役割（App roles）で、投稿に使う Threads アカウントを **Threads テスター** として招待する
4. Threads アプリの設定から、Webサイトのアクセス許可 → 招待 を開き、招待を承認する
   （メニュー名は変わることがある）
5. アプリのダッシュボードのユースケース設定にある **User Token Generator** で、承認したテスターのトークンを生成してコピー
   （長期トークン、60日有効。以後は publish_due.py が7日ごとに自動更新する）
6. `.env` の `THREADS_ACCESS_TOKEN` に入れて `python setup_check.py` を実行
   → 「THREADS_USER_ID に ○○ を入れてください」と出るので、その数字を `THREADS_USER_ID` に入れる
7. もう一度 `python setup_check.py` で Threads の3項目が ✓ になるのを確認

## 4. 最初の実データ実行と公開
```bash
python main.py
```
`dist/index.html` をブラウザで開いて、商品とリンクがおかしくないか見る。問題なければ：

1. このフォルダで Git を初期化し、手順1のリポジトリに `main` ブランチで push する
2. GitHub のリポジトリ設定 → Pages → Source を **GitHub Actions** にする
3. Actions の「Pages」が緑になったら、公開URLを開いて確認する

## 5. 自動化の登録
```bash
schtasks /Create /TN "kaimawari-daily" /TR "C:\Users\doram\Desktop\Claude\apps\kaimawari\run_daily.bat" /SC DAILY /ST 05:30
```
```bash
schtasks /Create /TN "kaimawari-publish" /TR "C:\Users\doram\Desktop\Claude\apps\kaimawari\run_publish.bat" /SC MINUTE /MO 10
```
PC がスリープ中は実行されない。予約投稿の時間帯（夜）は PC を起こしておくか、電源設定でスリープを解除する。

## 6. 検索エンジンに知らせる
GitHub Pages のプロジェクトサイト（/kaimawari/ 配下）は robots.txt を置けないので、sitemap は直接登録する。
1. Google Search Console で「URL プレフィックス」に公開URLを追加（HTML ファイルでの確認が必要なら、渡されたファイルを `src/assets/` ではなく `dist/` 直下に置く手順を相談）
2. サイトマップに `sitemap.xml` を送信

## 7. 任意
- `config.yaml` の `rakuyoko.affiliate_url` に、楽天アフィリエイトのリンク作成で作ったラクヨコTOPのリンクを貼る
- `DISCORD_WEBHOOK_URL` を入れると、下書きが増えたときに件数だけ通知が来る
- 10月の回の `point_cap` は告知が出たら直す

## 毎日やること
承認デスクを開いて、承認か却下を押すだけ。
```bash
python review_server.py
```
http://127.0.0.1:8766
