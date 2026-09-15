"""静的サイトの書き出し（index.html / rakuyoko.html / OGP画像 / sitemap.xml / data/*.json）"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path

from .og_image import find_font, render_plan_card, render_rakuyoko_card
from .sections import badges, books_section, calendar_section, deals_section, ranking_section, steps_section
from .planner import Plan, is_eligible, price_with_tax

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
STRATEGY_LABELS = {"cheapest": "合計が安い順", "reviewed": "レビュー評価順"}
FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Dela+Gothic+One"
    "&family=IBM+Plex+Mono:wght@500&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap"
)
RAKUYOKO_PRESS_URL = "https://corp.rakuten.co.jp/news/press/2026/0825_01.html"
MARATHON_ENTRY_URL = "https://event.rakuten.co.jp/campaign/point-up/marathon/"
HISTORY_ROWS = 14


def yen(n: int) -> str:
    return f"¥{n:,}"


def e(value) -> str:
    return escape(str(value), quote=True)


def _page(*, title: str, description: str, active: str, body: str, config: dict,
          generated_at: datetime, demo: bool, canonical: str | None, og_image: str | None) -> str:
    nav = []
    for href, label in (("index.html", "買いまわりプラン"), ("rakuyoko.html", "ラクヨコ計算機")):
        current = ' aria-current="page"' if href == active else ""
        nav.append(f'<a href="{href}"{current}>{label}</a>')
    demo_banner = (
        '<div class="demo-banner" role="note">サンプルデータで表示しています（実在の商品・ショップではありません）。'
        ".env に楽天ウェブサービスのキーを入れると実データに切り替わります。</div>"
        if demo else ""
    )

    meta = [
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{e(config["site"]["name"])}">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(description)}">',
        '<meta property="og:locale" content="ja_JP">',
    ]
    if canonical:
        meta.insert(0, f'<link rel="canonical" href="{e(canonical)}">')
        meta.append(f'<meta property="og:url" content="{e(canonical)}">')
    if og_image:
        meta += [
            f'<meta property="og:image" content="{e(og_image)}">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            '<meta name="twitter:card" content="summary_large_image">',
        ]

    stamp = generated_at.strftime("%Y年%m月%d日 %H:%M")
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
{chr(10).join(meta)}
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS_URL}">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<p class="pr-bar"><span class="pr-tag">PR</span>このサイトは楽天アフィリエイトを利用しています</p>
{demo_banner}
<header class="masthead">
  <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">10</span>{e(config["site"]["name"])}</a>
  <nav class="nav" aria-label="ページ">{"".join(nav)}</nav>
</header>
<main>
{body}
</main>
<footer class="site-foot">
  <p><span class="pr-tag">PR</span>リンク先で購入があると、運営者に楽天アフィリエイトの報酬が発生します。</p>
  <p>楽天グループ株式会社とは関係のない非公式ツールです。価格・在庫・キャンペーン条件は{stamp}時点の情報です。購入前にリンク先と公式ページで確認してください。</p>
  <p><a href="https://webservice.rakuten.co.jp/" rel="noopener" target="_blank">Supported by Rakuten Developers</a></p>
</footer>
<script src="assets/tools.js" defer></script>
</body>
</html>
"""


def _plan_block(plan: Plan, *, shops_target: int, generated_at: datetime, hidden: bool) -> str:
    # スタンプは「予定の枠」として出し、買ったチェックで押印する（tools.js）
    stamps = []
    for i in range(shops_target):
        label = plan.items[i].get("label", "") if i < len(plan.items) else ""
        label_html = f'<span class="stamp-label">{e(label)}</span>' if label else ""
        stamps.append(f'<li class="stamp" data-slot="{i}"><span class="stamp-no">{i + 1}</span>{label_html}</li>')

    lines = []
    for i, item in enumerate(plan.items, 1):
        thumb = (
            f'<img class="thumb" src="{e(item["image"])}" alt="" width="56" height="56" loading="lazy">'
            if item.get("image") else '<span class="thumb" aria-hidden="true"></span>'
        )
        meta = [f'<span class="chip">{e(item.get("label", ""))}</span>', f'<span>{e(item["shop_name"])}</span>']
        if item.get("review_count"):
            meta.append(f'<span>★{item["review_average"]:.2f}（{item["review_count"]:,}件）</span>')
        meta.append("<span>送料込み</span>")
        if not item.get("tax_included", True):
            meta.append("<span>税別表示を税込に換算</span>")
        meta[1:1] = badges(item)
        code = e(item.get("item_code") or item["url"])
        lines.append(
            f'<li class="line"><span class="line-no">{i:02d}</span>{thumb}'
            f'<div class="line-body"><a class="line-name" href="{e(item["url"])}" rel="sponsored noopener" target="_blank">{e(item["name"])}</a>'
            f'<div class="line-meta">{"".join(meta)}</div></div>'
            f'<div class="line-side"><span class="line-price">{yen(price_with_tax(item))}</span>'
            f'<label class="line-check"><input type="checkbox" data-buy="{code}" data-slot="{i - 1}">'
            f'<span class="visually-hidden">{e(item["name"])}を</span>買った</label></div></li>'
        )

    short = ""
    if plan.shops < shops_target:
        short = f'<p class="fine is-warn">今日は条件に合う商品が{plan.shops}ショップ分しか見つかりませんでした。</p>'
    capped = "（上限に到達）" if plan.bonus_capped else ""
    hidden_attr = " hidden" if hidden else ""

    return f"""<div class="plan" data-plan="{plan.strategy}" data-total="{plan.total}" role="tabpanel"{hidden_attr}>
  <div class="card">
    <div class="card-head"><span>スタンプカード</span><span class="mono" data-progress data-target="{plan.shops}">0 / {plan.shops}</span></div>
    <ol class="stamps" aria-label="買ったショップのスタンプ">{"".join(stamps)}</ol>
    <p class="fine">商品の「買った」を押すとスタンプが埋まります。チェックはこの端末にだけ保存されます。<button type="button" class="text-button" data-reset-bought>チェックを全部外す</button></p>
    <dl class="tally">
      <div><dt>合計（税込）</dt><dd>{yen(plan.total)}</dd></div>
      <div><dt>ポイント倍率</dt><dd>{plan.multiplier}倍</dd></div>
      <div class="is-key"><dt>獲得見込み</dt><dd>{plan.points:,}pt</dd></div>
      <div><dt>実質還元</dt><dd>{plan.effective_rate * 100:.1f}%</dd></div>
    </dl>
    {short}
    <p class="fine">通常1倍（ショップのポイント倍率アップ中の商品は、いまの倍率）＋買いまわり{plan.multiplier - 1}倍{capped}。税抜価格を10%で割り戻して少なめに見積もっています。ボーナス上限{plan.point_cap:,}pt、エントリーが必要です。</p>
  </div>
  <div class="receipt">
    <div class="receipt-head"><span>{STRATEGY_LABELS[plan.strategy]}</span><span>{generated_at:%m/%d %H:%M} 時点の価格</span></div>
    <ol class="lines">{"".join(lines)}</ol>
    <div class="receipt-foot"><span>{plan.shops}ショップ 合計</span><span>{yen(plan.total)}</span></div>
  </div>
</div>"""


def _shelf(candidates: list[dict], min_per_shop: int, per_label: int = 5) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    for item in sorted(candidates, key=lambda it: -it.get("review_count", 0)):
        code = item.get("item_code") or item["name"]
        if code in seen or not is_eligible(item, min_per_shop):
            continue
        seen.add(code)
        groups[item.get("label", "その他")].append(item)

    cols = []
    for label, items in groups.items():
        rows = "".join(
            f'<li><a href="{e(it["url"])}" rel="sponsored noopener" target="_blank">{e(it["name"])}</a>'
            f'<span class="p">{yen(price_with_tax(it))}</span></li>'
            for it in items[:per_label]
        )
        cols.append(f'<div class="shelf-col"><h3>{e(label)}</h3><ul>{rows}</ul></div>')
    return "".join(cols)


def _history_section(history: list[dict] | None, config: dict) -> str:
    if not history:
        return ""
    rows = []
    for h in reversed(history[-HISTORY_ROWS:]):
        reviewed = yen(h["reviewed_total"]) if h.get("reviewed_total") else "–"
        rows.append(
            f'<tr><th scope="row">{e(h["date"][5:].replace("-", "/"))}</th>'
            f'<td>{yen(h["cheapest_total"])}</td><td>{h["cheapest_points"]:,}pt</td>'
            f'<td>{reviewed}</td><td>{h["candidates"]:,}件</td></tr>'
        )
    s = config["search"]
    return f"""<section class="history" aria-labelledby="history-title">
  <h2 id="history-title">毎朝の選定記録</h2>
  <p class="lede">同じ条件（送料込み・{s["min_price"]:,}〜{s["max_price"]:,}円・レビュー{s["min_review_count"]}件以上）で毎朝選び直した結果です。マラソンの前後で合計がどう動くかを残しています。</p>
  <div class="table-wrap">
    <table class="history-table">
      <thead><tr><th scope="col">日付</th><th scope="col">合計（安い順）</th><th scope="col">見込み</th><th scope="col">合計（レビュー順）</th><th scope="col">候補</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</section>"""


def _index_body(config: dict, plans: dict[str, Plan], candidates: list[dict], generated_at: datetime,
                history: list[dict] | None, extras: dict | None = None) -> str:
    extras = extras or {}
    m = config["marathon"]
    cheapest = plans["cheapest"]
    entry_url = m.get("entry_url") or MARATHON_ENTRY_URL
    tabs = "".join(
        f'<button type="button" role="tab" aria-selected="{"true" if i == 0 else "false"}" data-strategy="{key}">{STRATEGY_LABELS[key]}</button>'
        for i, key in enumerate(plans)
    )
    blocks = "\n".join(
        _plan_block(plan, shops_target=m["shops_target"], generated_at=generated_at, hidden=i > 0)
        for i, plan in enumerate(plans.values())
    )
    return f"""<section class="lead">
  <p class="eyebrow">次回のお買い物マラソン　{e(m["next_period"])}</p>
  <h1>1,000円を10ショップ。<br>ポイント10倍までの<span class="nowrap">最短ルート</span></h1>
  <p class="lede">楽天市場の「送料込み・1,000円台」から、別々の10ショップを毎朝選び直しています。どうせ買う日用品で倍率を上げて、本命の買い物はそのあとに。</p>
  <p class="lead-actions"><a class="button" href="{e(entry_url)}" rel="noopener" target="_blank">先にエントリーする</a><span class="note">楽天の公式ページが開きます。開催期間外は終了ページが表示されます</span></p>
</section>

<section class="planner" data-strategy-root aria-label="買いまわりプラン">
  <div class="seg" role="tablist" aria-label="並べ方">{tabs}</div>
  {blocks}
</section>

{steps_section(entry_url)}

{deals_section(extras.get("deals"))}

<section class="calc" id="calc">
  <div class="calc-copy">
    <h2>倍率と還元の計算</h2>
    <p class="lede">本命の買い物を足したときに何ポイントになるか、上限まであといくらかを確かめられます。ショップ独自のポイント倍率アップは含めない計算です（上のプランの見込みには含めています）。</p>
    <form class="fields" data-marathon-calc>
      <label class="field">ショップ数
        <span class="field-row"><input type="range" name="shops" min="1" max="{m["shops_target"]}" value="{cheapest.multiplier}"><output name="shopsOut" class="big">{cheapest.multiplier}</output></span>
      </label>
      <label class="field">期間中の合計（税込・円）
        <input type="number" name="total" value="{cheapest.total}" min="0" step="1" inputmode="numeric">
      </label>
      <label class="field">ボーナス上限（pt）
        <input type="number" name="cap" value="{m["point_cap"]}" min="0" step="1" inputmode="numeric">
      </label>
    </form>
  </div>
  <div class="result" data-marathon-result aria-live="polite">
    <dl class="tally">
      <div><dt>通常ポイント</dt><dd data-k="normal">{cheapest.normal_points:,}pt</dd></div>
      <div><dt>買いまわりボーナス</dt><dd data-k="bonus">{cheapest.bonus_points:,}pt</dd></div>
      <div class="is-key"><dt>合計</dt><dd data-k="points">{cheapest.points:,}pt</dd></div>
      <div><dt>実質還元</dt><dd data-k="rate">{cheapest.effective_rate * 100:.1f}%</dd></div>
    </dl>
    <p class="note" data-k="cap"></p>
  </div>
</section>

{ranking_section(extras.get("rankings"))}

{books_section(extras.get("books"), extras.get("kobo"), config)}

<section class="shelf" aria-labelledby="shelf-title">
  <h2 id="shelf-title">今日の送料込み・1,000円台の候補</h2>
  <div class="shelf-grid">{_shelf(candidates, m["min_per_shop"])}</div>
</section>

{_history_section(history, config)}

{calendar_section(extras.get("calendar"))}

<section class="rules">
  <h2>買いまわりの数え方</h2>
  <ul>
    <li>1ショップ合計1,000円（税込）以上で1カウント。送料・ラッピング料は含みません。</li>
    <li>同じショップで注文を分けても、カウントは1つです。</li>
    <li>楽天ふるさと納税は2025年10月から原則ポイント付与の対象外です。</li>
    <li>ボーナスの上限は開催回ごとに変わります。期間中のエントリーが必要です。</li>
  </ul>
  <p><a href="{e(m["guide_url"])}" rel="noopener" target="_blank">公式のルールを確認する</a></p>
</section>"""


def _rakuyoko_body(config: dict) -> str:
    r = config["rakuyoko"]
    rows = "".join(
        f'<li class="row"><span class="row-tag">例</span><label><span class="visually-hidden">商品の金額（円）</span>'
        f'<input type="number" min="1" step="1" inputmode="numeric" value="{int(p)}"></label>'
        f'<button type="button" class="row-remove">削除</button></li>'
        for p in r.get("example_prices", [])
    )
    if r.get("affiliate_url"):
        cta = (f'<a class="button" href="{e(r["affiliate_url"])}" rel="sponsored noopener" target="_blank">'
               'ラクヨコを開く <span class="pr-tag">PR</span></a>')
    else:
        cta = '<a class="button" href="https://rakuyoko.rakuten.co.jp/" rel="noopener" target="_blank">ラクヨコを開く</a>'

    return f"""<section class="lead">
  <p class="eyebrow">楽天ラクヨコ</p>
  <h1>2,100円から16,666円。<br>送料無料の枠に<span class="nowrap">収める計算機</span></h1>
  <p class="lede">ラクヨコは1回の注文が{r["min_order"]:,}〜{r["max_order"]:,}円（税込）のときだけ注文できます。カートに入れたい商品の金額を並べると、足りない金額と、上限を超えたときの分け方を出します。</p>
</section>

<section class="splitter" data-rakuyoko-calc data-min="{r["min_order"]}" data-max="{r["max_order"]}">
  <div class="rows-wrap">
    <div class="rows-head"><h2>カートの金額</h2><button type="button" class="text-button" data-clear>例を消す</button></div>
    <ol class="rows" data-rows>{rows}</ol>
    <button type="button" class="add" data-add>金額を追加</button>
    <p class="rk-summary" data-summary aria-hidden="true" hidden></p>
  </div>
  <div class="result" data-result aria-live="polite"><p class="note">金額を入れると判定します。</p></div>
</section>

<section class="facts">
  <h2>注文前に知っておくこと</h2>
  <dl>
    <dt>注文できる金額</dt><dd>1回{r["min_order"]:,}円〜{r["max_order"]:,}円（税込）</dd>
    <dt>送料</dt><dd>無料（沖縄・離島・一部地域を除く）</dd>
    <dt>ポイント</dt><dd>税抜100円につき楽天ポイント1ポイント。支払いにも使えます</dd>
    <dt>返品</dt><dd>「Rセレクト」の商品は、発送日から30日以内なら自己都合でも返品できます</dd>
  </dl>
  <p class="note">出典：<a href="{RAKUYOKO_PRESS_URL}" rel="noopener" target="_blank">楽天グループ プレスリリース（2026年8月25日）</a>。ラクヨコの商品情報・画像はこのサイトでは扱っていません。</p>
  <p>{cta}</p>
</section>"""


def _sitemap(urls: list[str], generated_at: datetime) -> str:
    day = generated_at.date().isoformat()
    entries = "".join(f"  <url><loc>{e(url)}</loc><lastmod>{day}</lastmod></url>\n" for url in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{entries}</urlset>\n")


def build_site(out_dir: Path, *, config: dict, plans: dict[str, Plan], candidates: list[dict],
               generated_at: datetime, demo: bool, site_url: str | None = None,
               history: list[dict] | None = None, extras: dict | None = None) -> list[str]:
    """書き出して、運用上の注意（警告）を返す"""
    warnings: list[str] = []
    out_dir = Path(out_dir)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    for asset in ASSETS_DIR.iterdir():
        shutil.copy2(asset, out_dir / "assets" / asset.name)

    site = site_url.rstrip("/") + "/" if site_url else None
    r = config["rakuyoko"]
    images: dict[str, str] = {}
    font = find_font()
    if font:
        render_plan_card(out_dir / "assets" / "og-plan.png", plans["cheapest"], generated_at,
                         shops_target=config["marathon"]["shops_target"], font_path=font)
        render_rakuyoko_card(out_dir / "assets" / "og-rakuyoko.png", r["min_order"], r["max_order"], font_path=font)
        images = {"index.html": "assets/og-plan.png", "rakuyoko.html": "assets/og-rakuyoko.png"}
    else:
        warnings.append("日本語フォントが見つからないため、OGP画像を作れませんでした")
    if not site:
        warnings.append("SITE_URL が無いため、canonical・OGP画像のURL・sitemap.xml を出していません")

    version = generated_at.strftime("%Y%m%d")
    canonical = {"index.html": site, "rakuyoko.html": f"{site}rakuyoko.html" if site else None}

    def og_image(page: str) -> str | None:
        # Threads はリンクカードを保存するので、日付で URL を変えて毎日の数字を出す
        return f"{site}{images[page]}?v={version}" if site and page in images else None

    name = config["site"]["name"]
    pages = {
        "index.html": _page(
            title=f"{name}｜お買い物マラソンの10ショップ",
            description="楽天お買い物マラソンの買いまわりを、送料込み1,000円台の商品で10ショップ埋めるプランを毎日更新。",
            active="index.html", body=_index_body(config, plans, candidates, generated_at, history, extras),
            config=config, generated_at=generated_at, demo=demo,
            canonical=canonical["index.html"], og_image=og_image("index.html"),
        ),
        "rakuyoko.html": _page(
            title=f"ラクヨコ送料無料ライン計算機｜{name}",
            description="楽天ラクヨコの注文条件（2,100〜16,666円）に収まるか判定し、超えたときの分け方を出す計算機。",
            active="rakuyoko.html", body=_rakuyoko_body(config),
            config=config, generated_at=generated_at, demo=demo,
            canonical=canonical["rakuyoko.html"], og_image=og_image("rakuyoko.html"),
        ),
    }
    # GitHub Pages は静的ファイルを約10分キャッシュする。中身が変わったら URL も変えて、古い JS と新しい HTML が混ざらないようにする
    versions = {name: hashlib.sha1((ASSETS_DIR / name).read_bytes()).hexdigest()[:8] for name in ("site.css", "tools.js")}
    for filename, html in pages.items():
        for name, digest in versions.items():
            html = html.replace(f'assets/{name}"', f'assets/{name}?v={digest}"')
        (out_dir / filename).write_text(html, encoding="utf-8")

    if site:
        (out_dir / "sitemap.xml").write_text(_sitemap([canonical["index.html"], canonical["rakuyoko.html"]], generated_at),
                                             encoding="utf-8")

    payload = {
        "generated_at": generated_at.isoformat(),
        "demo": demo,
        "marathon": config["marathon"],
        "plans": {key: plan.to_dict() for key, plan in plans.items()},
    }
    (out_dir / "data" / "plan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if history is not None:
        (out_dir / "data" / "history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return warnings
