from datetime import datetime

from src.checks import has_blocking, run_checks
from src.drafts import build_drafts
from src.schedule import JST, format_period, next_event, parse_events, slots_for

EVENTS = parse_events([
    {"name": "2026年9月 お買い物マラソン", "start": "2026-09-19T20:00", "end": "2026-09-24T01:59", "point_cap": 7000},
])
PLAN = {
    "generated_at": "2026-09-19T05:30:00+09:00",
    "demo": False,
    "plans": {
        "cheapest": {"shops": 10, "total": 10175, "points": 924, "effective_rate": 0.0908,
                     "items": [{"label": "スイーツ"}, {"label": "ペット"}, {"label": "食品"}, {"label": "ペット"}]},
        "reviewed": {"shops": 10, "total": 10330, "points": 938, "effective_rate": 0.0908, "items": [{"label": "飲料"}]},
    },
}
SITE = "https://example.github.io/kaimawari/"


def test_slots_cover_the_marathon():
    slots = dict(slots_for(EVENTS[0]))
    assert slots["eve"] == datetime(2026, 9, 18, 21, 0, tzinfo=JST)
    assert slots["hour_before"] == datetime(2026, 9, 19, 19, 0, tzinfo=JST)
    assert slots["kickoff"] == datetime(2026, 9, 19, 20, 5, tzinfo=JST)
    assert slots["final_day"] == datetime(2026, 9, 23, 12, 10, tzinfo=JST)
    assert slots["last_2h"] == datetime(2026, 9, 23, 23, 59, tzinfo=JST)
    assert all(at < EVENTS[0].end for at in slots.values())


def test_format_period_has_correct_weekdays():
    assert format_period(EVENTS[0]) == "2026年9月19日（土）20:00 〜 9月24日（木）01:59"


def test_next_event_skips_finished_rounds():
    assert next_event(EVENTS, datetime(2026, 9, 20, tzinfo=JST)) is EVENTS[0]
    assert next_event(EVENTS, datetime(2026, 9, 25, tzinfo=JST)) is None


def test_drafts_only_inside_horizon():
    early = build_drafts(EVENTS, PLAN, now=datetime(2026, 9, 18, 5, 30, tzinfo=JST), horizon_hours=36, site_url=SITE)
    assert [d["id"] for d in early] == ["20260919-eve"]
    same_day = build_drafts(EVENTS, PLAN, now=datetime(2026, 9, 19, 5, 30, tzinfo=JST), horizon_hours=36, site_url=SITE)
    assert [d["id"] for d in same_day] == ["20260919-hour_before", "20260919-kickoff"]


def test_every_template_passes_all_checks():
    drafts = build_drafts(EVENTS, PLAN, now=datetime(2026, 9, 18, tzinfo=JST), horizon_hours=24 * 7, site_url=SITE)
    assert len(drafts) == 7
    for draft in drafts:
        checks = run_checks(draft["text"], fact=draft["fact"], link_url=draft["link_url"])
        assert all(c["status"] == "ok" for c in checks), (draft["id"], checks)


def test_kickoff_uses_plan_numbers_and_labels():
    drafts = {d["id"]: d for d in build_drafts(EVENTS, PLAN, now=datetime(2026, 9, 18, tzinfo=JST),
                                               horizon_hours=24 * 7, site_url=SITE)}
    kickoff = drafts["20260919-kickoff"]["text"]
    assert "¥10,175" in kickoff and "924pt" in kickoff and "スイーツ、ペット、食品" in kickoff
    assert "約2,450pt" in drafts["20260919-midway"]["text"]
    assert "約85,600円" in drafts["20260919-midway"]["text"]
    assert drafts["20260919-rakuyoko"]["link_url"] == SITE + "rakuyoko.html"


def test_checks_block_missing_pr_and_risky_words():
    checks = {c["label"]: c for c in run_checks("ラクヨコは絶対いちばんお得")}
    assert checks["PR表記"]["status"] == "block" and checks["PR表記"]["fix"] == "pr"
    assert checks["断定・誇大表現"]["status"] == "block"
    assert checks["リンク"]["status"] == "ok"
    assert checks["数字と条件の出典"]["status"] == "warn"


def test_only_number_posts_carry_links_and_every_post_has_topic_tag():
    drafts = {d["id"].split("-", 1)[1]: d for d in build_drafts(
        EVENTS, PLAN, now=datetime(2026, 9, 18, tzinfo=JST), horizon_hours=24 * 7, site_url=SITE)}
    assert {slot for slot, d in drafts.items() if d["link_url"]} == {"kickoff", "midway", "rakuyoko"}
    assert drafts["rakuyoko"]["topic_tag"] == "楽天ラクヨコ"
    assert all(d["topic_tag"] for d in drafts.values())
    assert all("." not in d["topic_tag"] and "&" not in d["topic_tag"] for d in drafts.values())
    assert drafts["eve"]["text"].rstrip("#PR").rstrip().endswith("？")


def test_checks_block_long_text_and_too_many_links():
    long_text = "あ" * 501 + "\n#PR"
    assert has_blocking(run_checks(long_text, fact="x", link_url=SITE))
    links = " ".join(f"https://example.com/{i}" for i in range(5)) + "\n#PR"
    checks = {c["label"]: c for c in run_checks(links, fact="x", link_url=SITE)}
    assert checks["リンク"]["status"] == "block"
