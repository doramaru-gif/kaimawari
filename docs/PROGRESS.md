# 進捗メモ（セッションが切れたらここから再開）

最終更新: 2026-09-15

## 方針（ユーザー合意済み）
- ① 承認なし・費用なし → 実装：買いまわり帳サイト（楽天市場API → 静的サイト、毎朝自動）
- ② 承認のみ → Threads のマラソン投稿に絞る：下書き自動生成 → 承認デスクで承認 → 予約時刻に自動投稿
- ラクヨコは規約（第13条7号・20号）で自動取得・転載禁止。データは楽天市場APIのみ

## 完了
- [x] ① サイト生成（main.py / src/rakuten_api.py / planner.py / site_builder.py / assets）
- [x] ① テスト、デモ書き出し（dist-demo）、ブラウザで表示確認
- [x] ② モック（artifact: https://claude.ai/code/artifact/073fa1e9-f4a9-42c0-976d-e6b7fc6526af）

## ② 本実装（進行中）
- [x] src/schedule.py … 開催予定と投稿枠（前夜・1時間前・開始直後・中日・ラクヨコ・最終日・残り2時間）
- [x] src/checks.py … 公開前チェック（PR表記・500字・誇大表現・リンク数・出典）
- [x] src/drafts.py … テンプレートで下書き生成（API費用なし）
- [x] src/queue_store.py … data/queue.json（ロック付き）
- [x] src/threads_api.py … 投稿（コンテナ→30秒待ち→公開）、長期トークン更新
- [x] src/publisher.py … 予約時刻が来た承認済みだけ投稿。期限切れ・二重投稿防止
- [x] src/review_api.py / review_server.py / src/review_ui … 承認デスク（127.0.0.1:8766）
- [x] queue_cli.py / publish_due.py / run_publish.bat
- [x] src/review_ui（index.html / desk.css / app.js）
- [x] テスト全通過（41件）、デモ下書き7件の生成、publish_due --dry-run
- [x] デモキューで承認デスクをブラウザ確認（表示・承認の保存・自動で次へ）
- [x] ローカル以外からのリクエスト拒否を確認（独自ヘッダなし／他オリジン／他ホスト → 403）

## 2026-09-15 再開後に追加
- [x] setup_check.py … .env・楽天API・Threads（me / 投稿枠）・開催予定・Git・タスク登録をまとめて確認
- [x] docs/SETUP.md … ユーザーが上から順に進める手順書
- [x] .github/workflows/pages.yml … Pages は dist/ から直接公開できないため Actions で公開
- [x] .env を .env.example から作成（値は空）

## 2026-09-16 追加（ユーザー設定待ちの間に進めた分）
- [x] src/og_image.py … OGP画像（今日のプランの数字入り／ラクヨコ計算機）。Threads のリンクカードに出る。URLに ?v=日付
- [x] canonical・og:*・twitter:card・favicon.svg・sitemap.xml（SITE_URL がある時だけ絶対URL系を出す）
- [x] src/history.py … 毎朝の選定結果を data/history.json に記録（180日）→ サイトに「毎朝の選定記録」表
- [x] .env 確認：SITE_URL はサンプルのまま、ほかは空（ユーザー設定はまだ）

## 2026-09-16 ユーザー目線の検証で直したこと
- [x] スマホで横にはみ出す（記録表の min-width が main グリッドを540pxに広げていた）→ main > * { min-width: 0 }
- [x] スタンプカードは「予定の枠」にし、各商品の「買った」チェックで押印（localStorage、2つの並べ方で共有）
- [x] 冒頭に「先にエントリーする」ボタン（公式マラソンページ）
- [x] CSS/JS の URL に中身のハッシュ（GitHub Pages のキャッシュで古い JS が動く問題。検証中に実際に発生）
- [x] ラクヨコ計算機：「例を消す」、スマホで判定が見えるバー（入力中も画面下に表示）
- [x] 文字サイズとタップ領域、見出しが語の途中で折り返さないように
- [x] Threads 下書き：リンク付きは3本（開始直後・中日・ラクヨコ）、他は問いかけ＋プロフィール誘導。topic_tag を付与
- [x] 集客プラン（artifact）：docs/promotion-plan.html

## 2026-09-16 本番公開
- [x] GitHub：doramaru-gif/kaimawari（Public、Pages＝GitHub Actions）。PCは GitHub CLI（%LOCALAPPDATA%\gh-cli、ポータブル版）でログイン済み、git は gh の認証を使う
- [x] 楽天：アプリ登録済み（許可サイト doramaru-gif.github.io、Ichiba API スコープ追加済み）。.env に3値
- [x] 実データで初回生成（8検索・240件）→ push → https://doramaru-gif.github.io/kaimawari/ が HTTP 200
- [x] 楽天の新しいエラー形式（errors.errorMessage）に対応。レビュー順は件数で重み付けした評価に変更
- [x] タスクスケジューラ登録：kaimawari-daily（毎日05:30）、kaimawari-publish（10分おき。Threads 未設定の間は確認だけ）
- [ ] Threads（③）：未着手。ユーザーはスマホのみ・PCのChromeはMeta未ログイン。1画面ずつ一緒に進める
- [x] 品質：キーワード検索だけだと「ペット」「飲料」枠に別カテゴリの商品が入っていた → 楽天ジャンル検索APIで確認した genreId で各枠を絞り込み（config.yaml の queries.genre_id）
- [x] 「初回限定」「初回購入」を NGKeyword で除外

## 2026-09-16 楽天APIを使ったユーザー向け機能の追加
- [x] ポイント倍率アップ（pointRate）：買う時点（開催前なら開始時刻）で有効な倍率だけを数える。同じ価格なら倍率の高い商品を優先し、見込みptに反映、「ポイント○倍〜期限」チップ
- [x] 本命探しの売れ筋：楽天市場デイリーランキング（総合／女性30代／女性40代／男性30代）
- [x] 本と電子書籍で、あと2ショップ：楽天ブックス（漫画・売上順・在庫あり）と楽天Kobo（漫画・レビュー件数順）の1,000円以上・発売済み
- [x] ショップ・オブ・ザ・イヤー受賞店のチップ
- 入れなかったもの：楽天トラベル・GORA・レシピ（お買い物マラソンの買いまわり対象ではなく、ターゲットの目的と合わない）
- 1回の更新で呼ぶAPI：商品検索16回＋ランキング4回＋ブックス1回＋Kobo1回（約30秒）

## 2026-09-16 コンテンツ追加・改善・バグ修正
- [x] 「買う前の3ステップ」（エントリー → カート → 開始後に注文）。ポイント付与は翌月15日ごろ
- [x] 「還元率が高い順」＝いま倍率アップ中の商品（買いまわり候補＋売れ筋から。ショップ重複なし）
- [x] 「開催の予定」＝次回と次々回（あと何日・上限pt）
- [x] タブに aria-controls / aria-labelledby を付与
- [x] バグ：calendar_section の f文字列の入れ子引用で KeyError → 生成が落ちていた
- [x] バグ：publish_due が10分おきに「トークン未設定」を警告していた → 予約が無ければ静かに終了
- [x] 定期連携：`python status.py` で状況メモを出力（docs/HANDOFF.md に使い方）
- [ ] 月額利用向けの設定 … 内容の確認待ち（ユーザーに質問中）

## 残り（ユーザーの設定待ち。コード側の作業はなし）
- 実データでの初回実行（main.py → queue_cli.py draft → 承認 → publish_due.py）
- 9月の回（9/19 20:00開始）に間に合わせるには、9/18 05:30 の run_daily より前に下の1〜5を終える
- [x] CLAUDE.md 更新

## ユーザー側の作業待ち（こちらではできない）
1. 楽天ウェブサービスのアプリ登録 → .env（RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY / RAKUTEN_AFFILIATE_ID / SITE_URL）
2. 「許可されたWebサイト」に SITE_URL を登録
3. GitHub リポジトリ作成と Pages 設定（dist/ を公開）
4. Threads 長期アクセストークンとユーザーID → .env（THREADS_ACCESS_TOKEN / THREADS_USER_ID）
5. タスクスケジューラ登録（CLAUDE.md の schtasks 2本）

## 再開時の確認コマンド
```bash
python -m pytest -q
python main.py --demo
python queue_cli.py draft --demo
python review_server.py --demo
```
