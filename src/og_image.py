"""Threads のリンクカードや SNS 共有で表示される OGP 画像（1200×630）を作る"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
GROUND = (237, 241, 238)
PAPER = (251, 252, 250)
INK = (27, 38, 35)
MUTED = (86, 100, 95)
LINE = (203, 213, 208)
STAMP = (50, 70, 166)
STAMP_SOFT = (226, 230, 246)

FONT_CANDIDATES = (
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/BIZ-UDGothicB.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
)


def find_font() -> Path | None:
    return next((Path(p) for p in FONT_CANDIDATES if Path(p).exists()), None)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _canvas(font_path: Path, eyebrow: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), GROUND)
    d = ImageDraw.Draw(img)
    d.ellipse((64, 52, 116, 104), outline=STAMP, width=4)
    d.text((90, 78), "10", font=_font(font_path, 22), fill=STAMP, anchor="mm")
    d.text((134, 78), "買いまわり帳", font=_font(font_path, 32), fill=INK, anchor="lm")
    d.rounded_rectangle((1058, 58, 1136, 98), radius=6, outline=MUTED, width=2)
    d.text((1097, 78), "PR", font=_font(font_path, 22), fill=MUTED, anchor="mm")
    d.text((64, 150), eyebrow, font=_font(font_path, 28), fill=STAMP, anchor="la")
    return img, d


def _save(img: Image.Image, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)


def render_plan_card(path: Path, plan, generated_at: datetime, *, shops_target: int = 10,
                     font_path: Path | None = None) -> bool:
    """今日のプランの数字とスタンプカード。フォントが無ければ作らずに False"""
    font_path = font_path or find_font()
    if not font_path:
        return False
    img, d = _canvas(font_path, "お買い物マラソンの買いまわり")
    d.text((64, 196), f"1,000円を{shops_target}ショップ。", font=_font(font_path, 68), fill=INK, anchor="la")

    d.rounded_rectangle((64, 318, 680, 566), radius=20, fill=PAPER, outline=LINE, width=2)
    label = _font(font_path, 24)
    d.text((100, 346), "合計（税込）", font=label, fill=MUTED, anchor="la")
    d.text((100, 380), f"¥{plan.total:,}", font=_font(font_path, 64), fill=INK, anchor="la")
    d.text((100, 470), "獲得見込み", font=label, fill=MUTED, anchor="la")
    d.text((100, 500), f"{plan.points:,}pt", font=_font(font_path, 44), fill=STAMP, anchor="la")
    d.text((390, 470), "実質還元", font=label, fill=MUTED, anchor="la")
    d.text((390, 500), f"{plan.effective_rate * 100:.1f}%", font=_font(font_path, 44), fill=INK, anchor="la")

    size, gap, x0, y0 = 72, 16, 712, 338
    number = _font(font_path, 28)
    for i in range(min(shops_target, 10)):
        x = x0 + (i % 5) * (size + gap)
        y = y0 + (i // 5) * (size + gap + 24)
        center = (x + size / 2, y + size / 2)
        if i < plan.shops:
            d.ellipse((x, y, x + size, y + size), fill=STAMP_SOFT, outline=STAMP, width=4)
            d.text(center, str(i + 1), font=number, fill=STAMP, anchor="mm")
        else:
            d.ellipse((x, y, x + size, y + size), outline=LINE, width=3)
            d.text(center, str(i + 1), font=number, fill=MUTED, anchor="mm")

    d.text((64, 604), f"{generated_at.month}/{generated_at.day} 更新　送料込み・1,000円台から毎朝選び直し",
           font=_font(font_path, 24), fill=MUTED, anchor="ls")
    _save(img, path)
    return True


def render_rakuyoko_card(path: Path, min_order: int, max_order: int, *, font_path: Path | None = None) -> bool:
    font_path = font_path or find_font()
    if not font_path:
        return False
    img, d = _canvas(font_path, "楽天ラクヨコ")
    d.text((64, 196), f"{min_order:,}円から{max_order:,}円。", font=_font(font_path, 64), fill=INK, anchor="la")
    d.text((64, 292), "送料無料の枠に収める計算機", font=_font(font_path, 46), fill=INK, anchor="la")

    left, right, top, bottom = 64, 1136, 424, 452
    d.rounded_rectangle((left, top, right, bottom), radius=14, fill=STAMP_SOFT)
    d.rounded_rectangle((left, top, left + int((right - left) * 0.72), bottom), radius=14, fill=STAMP)
    min_x = left + int((right - left) * min_order / max_order)
    for x in (min_x, right - 2):
        d.line((x, top - 12, x, bottom + 12), fill=INK, width=4)
    scale = _font(font_path, 24)
    d.text((left, 478), "¥0", font=scale, fill=MUTED, anchor="la")
    d.text((min_x, 478), f"¥{min_order:,}", font=scale, fill=MUTED, anchor="ma")
    d.text((right, 478), f"¥{max_order:,}", font=scale, fill=MUTED, anchor="ra")

    d.text((64, 604), "カートの金額を並べると、足りない額と注文の分け方が出ます",
           font=_font(font_path, 24), fill=MUTED, anchor="ls")
    _save(img, path)
    return True
