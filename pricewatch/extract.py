"""Prijs ophalen en uit een productpagina halen."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}


class PriceNotFound(Exception):
    pass


# ---------------------------------------------------------------- parsing

_NUM_RE = re.compile(r"\d[\d.,\s ']*")


def parse_price(value: Any) -> Optional[float]:
    """Zet tekst als '€ 1.299,-', '1.299,95', '1,299.95' of 12.5 om naar float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).strip()
    m = _NUM_RE.search(text)
    if not m:
        return None
    raw = m.group(0).strip().replace(" ", "").replace(" ", "").replace("'", "")
    raw = raw.rstrip(".,")
    if "," in raw and "." in raw:
        # het laatste scheidingsteken is het decimaalteken
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        head, _, tail = raw.rpartition(",")
        raw = (head.replace(",", "") + "." + tail) if len(tail) in (1, 2) else raw.replace(",", "")
    elif "." in raw:
        head, _, tail = raw.rpartition(".")
        if len(tail) == 3 or raw.count(".") > 1:
            # '1.299' -> duizendtalscheiding (NL notatie)
            raw = raw.replace(".", "")
    try:
        price = float(raw)
    except ValueError:
        return None
    return price if price > 0 else None


def _walk_jsonld(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement", "hasVariant"):
            if key in node:
                yield from _walk_jsonld(node[key])


def _types(node: dict) -> set[str]:
    t = node.get("@type", [])
    return {t} if isinstance(t, str) else set(t)


def _offer_price(offers: Any) -> Optional[float]:
    for offer in offers if isinstance(offers, list) else [offers]:
        if not isinstance(offer, dict):
            continue
        for key in ("price", "lowPrice"):
            p = parse_price(offer.get(key))
            if p:
                return p
        spec = offer.get("priceSpecification")
        for s in spec if isinstance(spec, list) else [spec]:
            if isinstance(s, dict):
                p = parse_price(s.get("price"))
                if p:
                    return p
    return None


def from_jsonld(soup: BeautifulSoup) -> Optional[float]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_jsonld(data):
            types = _types(node)
            if types & {"Product", "ProductGroup", "IndividualProduct"} and "offers" in node:
                p = _offer_price(node["offers"])
                if p:
                    return p
            if types & {"Offer", "AggregateOffer"}:
                p = _offer_price(node)
                if p:
                    return p
    return None


def from_meta(soup: BeautifulSoup) -> Optional[float]:
    selectors = [
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[itemprop="price"]',
        'meta[name="twitter:data1"]',
    ]
    for sel in selectors:
        tag = soup.select_one(sel)
        if tag and tag.get("content"):
            p = parse_price(tag["content"])
            if p:
                return p
    tag = soup.select_one('[itemprop="price"]')
    if tag:
        return parse_price(tag.get("content") or tag.get_text(" ", strip=True))
    return None


def from_selector(soup: BeautifulSoup, selector: str) -> Optional[float]:
    tag = soup.select_one(selector)
    if not tag:
        return None
    return parse_price(tag.get("content") or tag.get("data-price") or tag.get_text(" ", strip=True))


def extract_price(html: str, selector: Optional[str] = None) -> tuple[float, str]:
    """Geeft (prijs, methode) terug of gooit PriceNotFound."""
    soup = BeautifulSoup(html, "html.parser")
    if selector:
        p = from_selector(soup, selector)
        if p:
            return p, "selector"
        raise PriceNotFound(f"CSS-selector '{selector}' gaf geen prijs")
    for method, fn in (("json-ld", from_jsonld), ("meta", from_meta)):
        p = fn(soup)
        if p:
            return p, method
    raise PriceNotFound(
        "Geen prijs gevonden (geen JSON-LD/meta-prijs). Geef een 'selector' op of zet 'render: true'."
    )


# ---------------------------------------------------------------- fetching

def fetch_html(url: str, render: bool = False, timeout: int = 30) -> str:
    if render:
        return _fetch_rendered(url, timeout)
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(3 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def _fetch_rendered(url: str, timeout: int) -> str:
    from playwright.sync_api import sync_playwright  # alleen nodig bij render: true

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="nl-NL")
        page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        html = page.content()
        browser.close()
        return html


def extract_title(html: str) -> Optional[str]:
    """Productnaam uit JSON-LD, og:title of <title>."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_jsonld(data):
            if _types(node) & {"Product", "ProductGroup"} and isinstance(node.get("name"), str):
                return node["name"].strip()[:120]
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        return og["content"].strip()[:120]
    if soup.title and soup.title.string:
        return soup.title.string.strip()[:120]
    return None


def get_price(url: str, selector: Optional[str] = None, render: bool = False) -> tuple[float, str, Optional[str]]:
    html = fetch_html(url, render=render)
    price, method = extract_price(html, selector)
    return price, method, extract_title(html)
