"""開催予定と今日のプランから Threads 投稿の下書きを作る（テンプレートなのでAPI費用はかからない）

Threads はリンク付き投稿の表示が伸びにくく、返信（会話）が多い投稿を広げる。
そのため数字を見せる投稿（開始直後・中日・ラクヨコ）だけリンクカードを付け、
ほかは問いかけで終えてプロフィールのリンクへ誘導する。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urljoin

from .schedule import MarathonEvent, format_period, slots_for

MARATHON_TAG = "楽天お買い物マラソン"
RAKUYOKO_TAG = "楽天ラクヨコ"

KINDS = {
    "eve": "前日告知",
    "hour_before": "開始1時間前",
    "kickoff": "開始直後・今日の10ショップ",
    "midway": "中日・本命と合わせる",
    "rakuyoko": "ラクヨコ計算機の紹介",
    "final_day": "最終日",
    "last_2h": "残り2時間",
}
SOURCES = {
    "eve": "開催予定（開始前夜）",
    "hour_before": "開催予定（開始1時間前）",
    "kickoff": "今日のプラン（合計が安い順）",
    "midway": "倍率計算（開催予定のボーナス上限）",
    "rakuyoko": "ラクヨコの注文条件（公式発表）",
    "final_day": "今日のプラン（レビュー評価順）",
    "last_2h": "開催予定（終了2時間前）",
}


def _yen(n: int) -> str:
    return f"¥{n:,}"


def _round(n: float, unit: int) -> int:
    return int(round(n / unit) * unit)


def _labels(plan: dict, limit: int = 3) -> list[str]:
    labels = []
    for item in plan.get("items", []):
        label = item.get("label")
        if label and label not in labels:
            labels.append(label)
        if len(labels) == limit:
            break
    return labels


def _stamp(payload: dict) -> str:
    generated = datetime.fromisoformat(payload["generated_at"])
    return f"{generated.month}/{generated.day} {generated:%H:%M}"


def _eve(ev: MarathonEvent, payload: dict, site: str, calc: str):
    text = (f"明日の夜{ev.start.hour}時から、お買い物マラソン。\n\n"
            "今夜のうちにやっておくのは2つだけ。\n"
            "・どうせ買う日用品をカートに入れる\n"
            "・1,000円に届かない物は、同じショップでまとめる\n\n"
            "みんなは毎回、何ショップまで回してる？\n#PR")
    return text, f"開催期間：{format_period(ev)}", None


def _hour_before(ev: MarathonEvent, payload: dict, site: str, calc: str):
    text = ("あと1時間でマラソン。\n\n"
            "毎回いちばん多い失敗は、エントリーし忘れて倍率が付かないこと。\n"
            "買う前にエントリーを押しておくだけで防げる。\n\n"
            "送料込み1,000円台の10ショップ候補は、プロフィールのリンクに毎朝置いてる。\n#PR")
    return text, "エントリーが必要：公式ガイド", None


def _kickoff(ev: MarathonEvent, payload: dict, site: str, calc: str):
    plan = payload["plans"]["cheapest"]
    labels = "、".join(_labels(plan)) or "日用品"
    text = (f"マラソン始まった。\n\n"
            f"送料込み1,000円台だけで{plan['shops']}ショップ埋めると、合計{_yen(plan['total'])}。\n"
            f"見込みは{plan['points']:,}pt、実質{plan['effective_rate'] * 100:.0f}%くらい。\n\n"
            f"{labels}。どうせ買う物だけで組んだ。\n"
            "在庫切れは毎朝入れ替わる。\n#PR")
    return text, f"合計と見込み：{_stamp(payload)} 時点のプラン（税抜は10%で割り戻した概算）", site


def _midway(ev: MarathonEvent, payload: dict, site: str, calc: str):
    cap = ev.point_cap
    bonus = (30000 * 10 // 11) * 9 // 100
    ex_needed = -(-cap * 100 // 9)
    total_needed = -(-ex_needed * 11 // 10)
    text = (f"10ショップ埋めたあとに本命の3万円を買うと、ボーナスだけで約{_round(bonus, 10):,}pt。\n\n"
            f"ボーナスの上限は{cap:,}pt。\n"
            f"税込で合計約{_round(total_needed, 100):,}円までは、買うほどボーナスが増える計算。\n\n"
            "計算機に金額を入れると、上限まであといくらか出る。\n#PR")
    return text, f"ボーナス上限{cap:,}pt：開催予定（告知ページで確認）", site


def _rakuyoko(ev: MarathonEvent, payload: dict, site: str, calc: str):
    text = ("ラクヨコは1回の注文が2,100円から16,666円まで。その範囲なら送料無料（一部地域を除く）。\n\n"
            "カートが上限を超えたとき、どう分ければ全部送料無料で頼めるかを出す計算機を作った。\n#PR")
    return text, "注文条件：楽天プレスリリース（2026年8月25日）", calc


def _final_day(ev: MarathonEvent, payload: dict, site: str, calc: str):
    reviewed = payload["plans"].get("reviewed") or payload["plans"]["cheapest"]
    text = (f"今日が実質最終日（{ev.end.month}/{ev.end.day} {ev.end:%H:%M}まで）。\n\n"
            "まだショップ数が足りない人は、レビュー評価が高い1,000円台で残りを埋めるのが早い。\n"
            f"今朝のレビュー順の{reviewed['shops']}ショップは合計{_yen(reviewed['total'])}。\n\n"
            "いま何ショップまで来た？\n#PR")
    return text, f"レビュー順の合計：{_stamp(payload)} 時点のプラン", None


def _last_2h(ev: MarathonEvent, payload: dict, site: str, calc: str):
    text = ("マラソン、残り2時間。\n\n"
            "1,000円に数十円足りないショップがあったら、同じショップで小物を足すと1カウントになる。\n"
            "送料は1,000円の判定に含まれないので注意。\n\n"
            "駆け込みで何を足した？\n#PR")
    return text, "判定条件：公式ガイド（送料・ラッピング料は含まない）", None


TEMPLATES = {
    "eve": _eve,
    "hour_before": _hour_before,
    "kickoff": _kickoff,
    "midway": _midway,
    "rakuyoko": _rakuyoko,
    "final_day": _final_day,
    "last_2h": _last_2h,
}


def build_drafts(events: list[MarathonEvent], payload: dict, *, now: datetime, horizon_hours: float,
                 site_url: str) -> list[dict]:
    site = site_url if site_url.endswith("/") else site_url + "/"
    calc = urljoin(site, "rakuyoko.html")
    limit = now + timedelta(hours=horizon_hours)

    drafts = []
    for ev in events:
        for slot, at in slots_for(ev):
            if not (now < at <= limit):
                continue
            text, fact, link = TEMPLATES[slot](ev, payload, site, calc)
            drafts.append({
                "id": f"{ev.key}-{slot}",
                "at": at.isoformat(),
                "kind": KINDS[slot],
                "source": SOURCES[slot],
                "event": ev.name,
                "text": text,
                "link_url": link,
                "topic_tag": RAKUYOKO_TAG if slot == "rakuyoko" else MARATHON_TAG,
                "fact": fact,
            })
    return drafts
