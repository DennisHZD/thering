from datetime import datetime, timedelta, timezone

import pytest

from pricewatch.analysis import assess
from pricewatch.extract import PriceNotFound, extract_price, extract_title, parse_price

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


@pytest.mark.parametrize("raw,expected", [
    ("€ 1.299,-", 1299.0), ("1.299,95", 1299.95), ("1,299.95", 1299.95), ("€ 12,5", 12.5),
    ("249", 249.0), ("249.00", 249.0), ("EUR 89,99", 89.99), (34.5, 34.5), ("gratis", None),
    ("1 299,00 €", 1299.0), ("2.499", 2499.0),
])
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


def test_jsonld_graph():
    html = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
      {"@type":"BreadcrumbList"},{"@type":"Product","name":"X","offers":{"@type":"Offer","price":"199.99","priceCurrency":"EUR"}}]}</script>"""
    assert extract_price(html) == (199.99, "json-ld")


def test_jsonld_aggregate_offer():
    html = """<script type="application/ld+json">[{"@type":["Product"],"offers":[{"@type":"AggregateOffer","lowPrice":"45,00"}]}]</script>"""
    assert extract_price(html)[0] == 45.0


def test_meta_and_selector():
    assert extract_price('<meta property="product:price:amount" content="79.95">') == (79.95, "meta")
    assert extract_price('<span class="p">€ 1.049,-</span>', ".p") == (1049.0, "selector")
    with pytest.raises(PriceNotFound):
        extract_price("<p>geen prijs</p>")


def test_fake_discount_is_not_alerted():
    # 30 dagen €100, dan 2 dagen opgehoogd naar €150, nu 'actie' €120
    hist = [{"t": ts(30), "p": 100.0}, {"t": ts(2), "p": 150.0}]
    a = assess(hist, 120.0, NOW, {"min_discount_percent": 10})
    assert a.reference_price == 100.0
    assert a.real_discount_pct == -20.0
    assert not a.triggered
    assert any("verhoogd" in w for w in a.warnings)


def test_real_discount_is_alerted():
    hist = [{"t": ts(30), "p": 100.0}]
    a = assess(hist, 85.0, NOW, {"min_discount_percent": 10})
    assert a.triggered and a.real_discount_pct == 15.0


def test_short_spike_barely_moves_median():
    hist = [{"t": ts(30), "p": 100.0}, {"t": ts(5), "p": 130.0}, {"t": ts(4), "p": 100.0}]
    a = assess(hist, 89.0, NOW, {"min_discount_percent": 10})
    assert a.reference_price == 100.0 and a.triggered


def test_target_price_and_strict_mode():
    hist = [{"t": ts(30), "p": 100.0}, {"t": ts(10), "p": 70.0}, {"t": ts(5), "p": 100.0}]
    a = assess(hist, 80.0, NOW, {"target_price": 80})
    assert a.triggered
    strict = assess(hist, 80.0, NOW, {"target_price": 80, "require_lowest_in_window": True})
    assert not strict.triggered


def test_extract_title():
    html = """<meta property="og:title" content="OG naam"><script type="application/ld+json">{"@type":"Product","name":"Sony WH-1000XM5"}</script>"""
    assert extract_title(html) == "Sony WH-1000XM5"
    assert extract_title('<title> Pagina </title>') == "Pagina"


def test_personal_recipient(monkeypatch):
    from pricewatch import notify
    monkeypatch.setenv("MAIL_TO", "algemeen@x.nl")
    monkeypatch.setenv("SECRETS_JSON", '{"MAIL_TO_SANNE": "sanne@x.nl"}')
    assert notify.recipient("sanne") == "sanne@x.nl"
    assert notify.recipient("dennis") == "algemeen@x.nl"
    assert notify.recipient(None) == "algemeen@x.nl"
