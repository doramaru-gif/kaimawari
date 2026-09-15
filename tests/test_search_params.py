from pathlib import Path

import yaml

from main import build_search_params

CONFIG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8"))


def test_every_slot_is_narrowed_by_genre():
    search = CONFIG["search"]
    genres = {}
    for query in search["queries"]:
        params = build_search_params(search, query)
        assert isinstance(params["genreId"], int), query["label"]
        assert params["postageFlag"] == 1 and params["minPrice"] == search["min_price"]
        genres[query["label"]] = params["genreId"]
    assert genres["ペット"] == 101213
    assert genres["飲料"] == 100316
    assert len(set(genres.values())) == len(genres)  # 枠どうしでジャンルが重ならない


def test_query_without_genre_still_works():
    params = build_search_params(CONFIG["search"], {"label": "その他", "keyword": "1000円ポッキリ"})
    assert "genreId" not in params
