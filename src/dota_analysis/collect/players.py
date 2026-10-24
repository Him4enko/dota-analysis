from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import lxml.html

from .. import config
from ..net import HttpClient

log = logging.getLogger("collect.players")

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


def parse_steamcharts(page_html: str) -> list[dict]:
    rows: list[dict] = []
    try:
        doc = lxml.html.fromstring(page_html)
    except Exception:
        return rows
    for tr in doc.xpath("//table[contains(@class,'common-table')]//tr"):
        cells = [c.text_content().strip() for c in tr.xpath("./td")]
        if len(cells) < 5:
            continue
        label = cells[0]
        if not re.match(r"^[A-Z][a-z]+ \d{4}$", label):
            continue
        month, year = label.split()
        iso = f"{year}-{MONTHS.get(month, 1):02d}"
        try:
            avg = float(cells[1].replace(",", ""))
            peak = int(float(cells[4].replace(",", "")))
            gain = float(cells[3].replace("%", "").replace("+", "").replace(",", ""))
        except ValueError:
            continue
        rows.append({
            "month": iso,
            "avg_players": avg,
            "peak_players": peak,
            "gain_pct": gain,
            "source": "steamcharts.com",
        })
    return sorted(rows, key=lambda r: r["month"])


def collect(client: HttpClient) -> dict:
    out = {"players": [], "current": None, "events": []}
    r = client.get(config.STEAMCHARTS_URL, ttl_days=2, timeout=45)
    if r.ok:
        out["players"] = parse_steamcharts(r.text)
    else:
        log.warning("steamcharts -> %s", r.status)

    r2 = client.get(config.STEAM_PLAYERS_API, params={"appid": config.APP_ID}, timeout=30)
    if r2.ok:
        try:
            out["current"] = r2.json()["response"]["player_count"]
        except Exception:
            pass

    r3 = client.get(config.STEAM_NEWS_API,
                    params={"appid": config.APP_ID, "count": 300, "maxlength": 0},
                    timeout=45)
    if r3.ok:
        try:
            items = r3.json().get("appnews", {}).get("newsitems", [])
        except Exception:
            items = []
        for it in items:
            title = (it.get("title") or "").strip()
            ts = int(it.get("date") or 0)
            if not ts or not title:
                continue
            kind = "patch" if re.search(r"\bupdate\b|\bpatch\b|\b7\.\d", title, re.I) else "news"
            out["events"].append({
                "id": f"steamnews_{it.get('gid')}",
                "date_utc": ts,
                "title": title,
                "url": it.get("url", ""),
                "kind": kind,
            })
    log.info("players: %d months, %d news", len(out["players"]), len(out["events"]))
    return out
