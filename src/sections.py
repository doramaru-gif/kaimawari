"""トップページに足すセクション：ポイント倍率などのバッジ、売れ筋ランキング、本と電子書籍"""

from __future__ import annotations

from html import escape

from .planner import price_with_tax

MARATHON_GUIDE_URL = "https://event.rakuten.co.jp/campaign/point-up/marathon/guide/"


def _e(value) -> str:
    return escape(str(value), quote=True)


def _yen(n: int) -> str:
    return f"¥{n:,}"


def badges(item: dict) -> list[str]:
    """いま有効なポイント倍率（期限つき）と、ショップ・オブ・ザ・イヤー受賞"""
    out = []
    rate = item.get("point_rate_active", 1)
    if rate > 1:
        end = item.get("point_rate_end", "")
        until = f"〜{int(end[5:7])}/{int(end[8:10])}" if len(end) >= 10 and not end.startswith("9999") else ""
        out.append(f'<span class="chip is-point">ポイント{rate}倍{until}</span>')
    if item.get("shop_of_the_year"):
        out.append('<span class="chip is-soy">ショップ・オブ・ザ・イヤー受賞店</span>')
    return out


def ranking_section(rankings: list[dict] | None) -> str:
    rankings = [r for r in (rankings or []) if r.get("items")]
    if not rankings:
        return ""
    tabs, panels = [], []
    for i, tab in enumerate(rankings):
        selected = "true" if i == 0 else "false"
        tabs.append(f'<button type="button" role="tab" aria-selected="{selected}" data-tab="{i}">{_e(tab["label"])}</button>')
        rows = []
        for item in tab["items"]:
            thumb = (f'<img class="rank-thumb" src="{_e(item["image"])}" alt="" width="48" height="48" loading="lazy">'
                     if item.get("image") else '<span class="rank-thumb" aria-hidden="true"></span>')
            postage = "送料込み" if item.get("postage_included") else "送料別"
            meta = [f'<span class="p">{_yen(price_with_tax(item))}</span>', f"<span>{postage}</span>", *badges(item)]
            rows.append(
                f'<li class="rank-item"><span class="rank-no">{item.get("rank") or ""}</span>{thumb}'
                f'<div class="rank-body"><a class="rank-name" href="{_e(item["url"])}" rel="sponsored noopener" target="_blank">{_e(item["name"])}</a>'
                f'<div class="rank-meta">{"".join(meta)}</div></div></li>'
            )
        hidden = "" if i == 0 else " hidden"
        panels.append(f'<ol class="rank-list" role="tabpanel" data-panel="{i}"{hidden}>{"".join(rows)}</ol>')

    return f"""<section class="ranking" aria-labelledby="ranking-title" data-tabs>
  <h2 id="ranking-title">本命探しに、今日の売れ筋</h2>
  <p class="lede">10ショップを埋めたら、あとは本命の買い物です。楽天市場のデイリーランキング上位を並べています。送料とポイント倍率はショップごとに違うので、リンク先で確かめてください。</p>
  <div class="seg" role="tablist" aria-label="ランキングの種類">{"".join(tabs)}</div>
  {"".join(panels)}
</section>"""


def _book_thumb(book: dict) -> str:
    if book.get("image"):
        return f'<img class="book-thumb" src="{_e(book["image"])}" alt="" width="44" height="62" loading="lazy">'
    return '<span class="book-thumb" aria-hidden="true"></span>'


def books_section(books: list[dict] | None, kobo: list[dict] | None, config: dict) -> str:
    columns = []
    for title, items, note in (
        ("楽天ブックス（漫画・売れている順）", books, "全品送料無料"),
        ("楽天Kobo（電子書籍）", kobo, "買ってすぐ読める"),
    ):
        if not items:
            continue
        rows = "".join(
            f'<li class="book">{_book_thumb(it)}<div class="book-body">'
            f'<a href="{_e(it["url"])}" rel="sponsored noopener" target="_blank">{_e(it["name"])}</a>'
            f'<span class="author">{_e(it.get("author", ""))}</span></div>'
            f'<span class="p">{_yen(it["price"])}</span></li>'
            for it in items
        )
        columns.append(f'<div class="book-col"><h3>{title}<small>{note}</small></h3><ol class="book-list">{rows}</ol></div>')
    if not columns:
        return ""

    return f"""<section class="books" aria-labelledby="books-title">
  <h2 id="books-title">本と電子書籍で、あと2ショップ</h2>
  <p class="lede">楽天ブックスと楽天Koboも、買いまわりの対象です。日用品で埋まらない枠は、読みたかった本で。どちらも1,000円（税込）以上の発売済みの本から選んでいます。</p>
  <div class="book-grid">{"".join(columns)}</div>
  <p class="note">一部に対象外の条件があります。<a href="{MARATHON_GUIDE_URL}" rel="noopener" target="_blank">公式ガイドで確かめる</a></p>
</section>"""
