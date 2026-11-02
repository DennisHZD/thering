"""Meldingen versturen: e-mail (SMTP) en optioneel push via ntfy.sh."""
from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage

import requests


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name, default)
    return val.strip() if isinstance(val, str) and val.strip() else default


def _secrets() -> dict:
    try:
        return json.loads(os.environ.get("SECRETS_JSON") or "{}")
    except json.JSONDecodeError:
        return {}


def _personal(base: str, user: str | None) -> str | None:
    """Persoonlijke instelling (bijv. MAIL_TO_DENNIS), anders de algemene (MAIL_TO)."""
    if user:
        val = _secrets().get(f"{base}_{user.upper()}") or os.environ.get(f"{base}_{user.upper()}")
        if val and val.strip():
            return val.strip()
    return _env(base)


def recipient(user: str | None) -> str | None:
    return _personal("MAIL_TO", user)


def send_email(subject: str, text: str, html_body: str, to: str | None = None) -> bool:
    host = _env("SMTP_HOST")
    to = to or _env("MAIL_TO")
    if not host or not to:
        print("  [mail] SMTP_HOST of MAIL_TO niet ingesteld, mail overgeslagen")
        return False
    port = int(_env("SMTP_PORT", "587"))
    user = _env("SMTP_USER")
    password = _env("SMTP_PASSWORD")
    sender = _env("MAIL_FROM", user or to)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            if user:
                s.login(user, password or "")
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            if user:
                s.login(user, password or "")
            s.send_message(msg)
    print(f"  [mail] verstuurd naar {to}")
    return True


def send_push(title: str, message: str, url: str | None = None, user: str | None = None) -> None:
    topic = _personal("NTFY_TOPIC", user)
    if not topic:
        return
    headers = {"Title": title.encode("utf-8"), "Priority": "high", "Tags": "moneybag"}
    if url:
        headers["Click"] = url
    try:
        requests.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"), headers=headers, timeout=15)
        print("  [push] verstuurd")
    except requests.RequestException as exc:
        print(f"  [push] mislukt: {exc}")


def _eur(v) -> str:
    return "–" if v is None else f"€ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def price_alert(product: dict, a, dashboard_url: str | None, user: str | None = None) -> None:
    name = product["name"]
    url = product["url"]
    subject = f"Prijsalarm: {name} nu {_eur(a.price)} ({a.real_discount_pct:.0f}% onder mediaan)"

    rows = [
        ("Huidige prijs", _eur(a.price)),
        ("Mediaan (tijdgewogen)", _eur(a.reference_price)),
        ("Echte korting t.o.v. mediaan", f"{a.real_discount_pct:.1f}%"),
        ("Laagste in venster", _eur(a.lowest_window)),
        ("Laagste ooit (vóór nu)", _eur(a.all_time_low)),
        ("Historie", f"{a.history_days:g} dagen"),
    ]
    text = "\n".join(
        [f"{name}", url, "", "Waarom: " + "; ".join(a.reasons), ""]
        + [f"{k}: {v}" for k, v in rows]
        + ([""] + ["Let op: " + w for w in a.warnings] if a.warnings else [])
    )
    warn_html = "".join(
        f'<p style="background:#fff4e5;border-left:4px solid #f59e0b;padding:8px 12px;margin:8px 0">⚠️ {html.escape(w)}</p>'
        for w in a.warnings
    )
    rows_html = "".join(
        f'<tr><td style="padding:4px 16px 4px 0;color:#555">{k}</td><td style="padding:4px 0"><b>{v}</b></td></tr>'
        for k, v in rows
    )
    dash = f'<p><a href="{html.escape(dashboard_url)}">Bekijk prijsgeschiedenis</a></p>' if dashboard_url else ""
    body = f"""<div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#222;max-width:560px">
<h2 style="margin:0 0 4px">{html.escape(name)}</h2>
<p style="margin:0 0 12px;color:#c6613f;font-size:22px"><b>{_eur(a.price)}</b></p>
<p><b>Waarom:</b> {html.escape('; '.join(a.reasons))}</p>
<table>{rows_html}</table>
{warn_html}
<p><a href="{html.escape(url)}" style="display:inline-block;background:#c6613f;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none">Naar de winkel</a></p>
{dash}
</div>"""
    send_email(subject, text, body, recipient(user))
    send_push(subject, "; ".join(a.reasons), url, user)


def error_alert(product: dict, error: str, failures: int, user: str | None = None) -> None:
    subject = f"Price watch: {product['name']} kan niet meer gelezen worden"
    text = (
        f"{product['name']}\n{product['url']}\n\n"
        f"Na {failures} mislukte pogingen op rij kon de prijs niet worden opgehaald.\n"
        f"Laatste fout: {error}\n\n"
        "Mogelijke oplossingen: voeg een 'selector' toe, zet 'render: true', of controleer de URL."
    )
    send_email(subject, text, "<pre style='font-family:inherit'>" + html.escape(text) + "</pre>", recipient(user))
