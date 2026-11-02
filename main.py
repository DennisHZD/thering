"""Controleer alle producten uit products.json en verstuur meldingen.

Gebruik:
    python -m pricewatch.main               # alles dat 'aan de beurt' is
    python -m pricewatch.main --force       # alles, interval negeren
    python -m pricewatch.main --only ID     # één product
    python -m pricewatch.main --test-mail   # alleen een testmail sturen
    python -m pricewatch.main --dry-run     # niets mailen, niets opslaan
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

from . import notify
from .analysis import assess, parse_ts, stats_for_dashboard, utcnow
from .extract import get_price

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_FILE = ROOT / "products.json"
HISTORY_FILE = ROOT / "data" / "history.json"

HEARTBEAT = timedelta(hours=6)      # ook bij gelijke prijs af en toe een punt opslaan
ERROR_ALERT_AFTER = 12              # na zoveel fouten op rij één foutmail


def load_config() -> tuple[dict, list[dict]]:
    data = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8")) if PRODUCTS_FILE.exists() else {}
    defaults = data.get("defaults") or {}
    products = []
    for p in data.get("products") or []:
        if not p or not p.get("url"):
            continue
        cfg = {**defaults, **{k: v for k, v in p.items() if v not in (None, "")}}
        cfg.setdefault("id", p["url"])
        products.append(cfg)
    return data.get("settings") or {}, products


def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"products": {}}


def save_history(db: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")


def is_due(entry: dict, cfg: dict, now) -> bool:
    last = entry.get("last_checked")
    if not last:
        return True
    interval = timedelta(minutes=float(cfg.get("interval_minutes") or 0))
    # kleine marge omdat GitHub-runs niet exact op tijd starten
    return now - parse_ts(last) >= interval - timedelta(minutes=2)


def check_product(cfg: dict, entry: dict, now, dry_run: bool, dashboard_url: str | None) -> None:
    pid = cfg["id"]
    entry["url"] = cfg["url"]
    entry["last_checked"] = now.isoformat()
    history = entry.setdefault("history", [])

    try:
        price, method, title = get_price(cfg["url"], cfg.get("selector"), bool(cfg.get("render")))
    except Exception as exc:  # noqa: BLE001 - elke fout loggen, door met volgende product
        entry["name"] = cfg.get("name") or entry.get("name") or pid
        entry["failures"] = entry.get("failures", 0) + 1
        entry["last_error"] = f"{type(exc).__name__}: {exc}"[:300]
        print(f"- {entry['name']}: FOUT ({entry['failures']}x): {entry['last_error']}")
        if entry["failures"] == ERROR_ALERT_AFTER and not dry_run:
            notify.error_alert({**cfg, "name": entry["name"]}, entry["last_error"], entry["failures"])
        return

    if title:
        entry["title"] = title
    entry["name"] = cfg.get("name") or entry.get("title") or pid
    cfg = {**cfg, "name": entry["name"]}
    entry["failures"] = 0
    entry.pop("last_error", None)
    entry["method"] = method
    print(f"- {entry['name']}: € {price:.2f} (via {method})")

    a = assess(history, price, now, cfg)
    state = entry.setdefault("alert", {"active": False, "price": None})

    if a.triggered:
        new_low = state.get("price") is None or price < state["price"] - 0.005
        if not state.get("active") or new_low:
            print(f"  ALARM: {'; '.join(a.reasons)}")
            if not dry_run:
                notify.price_alert(cfg, a, dashboard_url)
            state.update(active=True, price=price, at=now.isoformat())
        else:
            print("  alarm al eerder verstuurd voor deze prijs")
    elif state.get("active"):
        state.update(active=False, price=None)

    last = history[-1] if history else None
    if not last or abs(last["p"] - price) > 0.005 or now - parse_ts(last["t"]) >= HEARTBEAT:
        history.append({"t": now.isoformat(), "p": price})

    entry["stats"] = stats_for_dashboard(history, now, cfg)
    entry["stats"].update(real_discount_pct=a.real_discount_pct, warnings=a.warnings)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-mail", action="store_true")
    args = ap.parse_args(argv)

    settings, products = load_config()
    dashboard_url = os.environ.get("DASHBOARD_URL") or settings.get("dashboard_url") or None

    if args.test_mail:
        ok = notify.send_email(
            "Price Watch: testmail",
            "Het werkt! Je ontvangt hier een melding zodra een product echt in prijs daalt.",
            "<p style='font-family:Segoe UI,Arial,sans-serif'>Het werkt! Je ontvangt hier een melding "
            "zodra een product echt in prijs daalt.</p>",
        )
        return 0 if ok else 1

    db = load_history()
    now = utcnow()
    active_ids = set()
    for cfg in products:
        if cfg.get("active", True) is False:
            continue
        active_ids.add(cfg["id"])
        if args.only and cfg["id"] != args.only:
            continue
        entry = db["products"].setdefault(cfg["id"], {})
        if args.force or args.only or is_due(entry, cfg, now):
            check_product(cfg, entry, now, args.dry_run, dashboard_url)

    known = {p["id"] for p in products}
    for pid in list(db["products"]):
        if pid not in known:               # verwijderd in de webapp
            del db["products"][pid]
        else:
            db["products"][pid]["active"] = pid in active_ids
    db["updated"] = now.isoformat()

    if not args.dry_run:
        save_history(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
