"""Prijshistorie analyseren en nepkortingen herkennen.

De historie bevat alleen punten waarop de prijs veranderde (plus af en toe een
'hartslag'). Elk punt geldt dus tot het volgende punt. Statistieken worden
daarom *tijdgewogen* berekend: een prijs die 1 dag gold telt 1/30 mee in een
venster van 30 dagen. Een korte prijsverhoging vlak voor een 'actie' verschuift
de referentieprijs daardoor nauwelijks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


def _eur(v: float) -> str:
    return f"€ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def segments(history: list[dict], start: datetime, end: datetime) -> list[tuple[float, float]]:
    """(prijs, duur in seconden) voor elk stuk historie binnen [start, end)."""
    out = []
    for i, pt in enumerate(history):
        t0 = parse_ts(pt["t"])
        t1 = parse_ts(history[i + 1]["t"]) if i + 1 < len(history) else end
        a, b = max(t0, start), min(t1, end)
        if b > a:
            out.append((pt["p"], (b - a).total_seconds()))
    return out


def weighted_median(segs: list[tuple[float, float]]) -> Optional[float]:
    if not segs:
        return None
    total = sum(d for _, d in segs)
    acc = 0.0
    for price, dur in sorted(segs):
        acc += dur
        if acc >= total / 2:
            return price
    return segs[-1][0]


@dataclass
class Assessment:
    price: float
    reference_price: Optional[float]      # tijdgewogen mediaan van het venster
    lowest_window: Optional[float]
    highest_recent: Optional[float]
    all_time_low: Optional[float]
    real_discount_pct: float               # t.o.v. referentieprijs
    vs_lowest_pct: Optional[float]         # t.o.v. laagste prijs in venster
    history_days: float
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)  # waarom er gealarmeerd wordt

    @property
    def triggered(self) -> bool:
        return bool(self.reasons)


def assess(
    history: list[dict],
    price: float,
    now: datetime,
    cfg: dict,
) -> Assessment:
    """Beoordeel de nieuwe prijs tegen de historie van vóór dit moment."""
    window_days = float(cfg.get("reference_days", 30))
    spike_days = float(cfg.get("spike_days", 14))
    min_hist_days = float(cfg.get("min_history_days", 3))

    prior = [pt for pt in history if parse_ts(pt["t"]) < now]
    window = segments(prior, now - timedelta(days=window_days), now)
    recent = segments(prior, now - timedelta(days=spike_days), now)

    ref = weighted_median(window)
    low = min((p for p, _ in window), default=None)
    high_recent = max((p for p, _ in recent), default=None)
    atl = min((pt["p"] for pt in prior), default=None)
    hist_days = (now - parse_ts(prior[0]["t"])).total_seconds() / 86400 if prior else 0.0

    real_disc = round((ref - price) / ref * 100, 1) if ref else 0.0
    vs_low = round((low - price) / low * 100, 1) if low else None

    a = Assessment(price, ref, low, high_recent, atl, real_disc, vs_low, round(hist_days, 1))

    # --- waarschuwingen: nepkorting / weinig data
    if ref and high_recent and high_recent >= ref * 1.05:
        a.warnings.append(
            f"Prijs is in de afgelopen {spike_days:g} dagen verhoogd tot {_eur(high_recent)}. "
            f"Korting wordt berekend t.o.v. de {window_days:g}-dagen mediaan ({_eur(ref)}), niet t.o.v. die piek."
        )
    if low is not None and price > low:
        a.warnings.append(
            f"Niet de laagste prijs: binnen {window_days:g} dagen was het al {_eur(low)}."
        )
    if hist_days < min_hist_days:
        a.warnings.append(f"Nog maar {hist_days:.1f} dag(en) historie; korting is minder betrouwbaar.")

    # --- alarmregels
    min_disc = cfg.get("min_discount_percent")
    if min_disc is not None and ref and real_disc >= float(min_disc):
        a.reasons.append(f"{real_disc:.1f}% onder de {window_days:g}-dagen mediaan (drempel {float(min_disc):g}%)")
    target = cfg.get("target_price")
    if target is not None and price <= float(target):
        a.reasons.append(f"prijs ≤ doelprijs € {float(target):.2f}")
    if cfg.get("alert_on_all_time_low") and atl is not None and price < atl:
        a.reasons.append(f"laagste prijs ooit gemeten (vorige laagste {_eur(atl)})")
    if cfg.get("require_lowest_in_window") and low is not None and price > low:
        # strenger: alleen alarm als het ook echt de laagste prijs van het venster is
        a.reasons.clear()
    return a


def stats_for_dashboard(history: list[dict], now: datetime, cfg: dict) -> dict:
    if not history:
        return {}
    window_days = float(cfg.get("reference_days", 30))
    segs = segments(history, now - timedelta(days=window_days), now)
    current = history[-1]["p"]
    prices = [p for p, _ in segs] + [current]
    return {
        "current": current,
        "median_window": weighted_median(segs) or current,
        "lowest_window": min(prices),
        "highest_window": max(prices),
        "all_time_low": min(pt["p"] for pt in history),
        "window_days": window_days,
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
