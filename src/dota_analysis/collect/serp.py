from __future__ import annotations

import base64
import hashlib
import logging
import re
from datetime import datetime, timezone

import lxml.html

from .. import config
from ..net import HttpClient
from ..text import clean_text

log = logging.getLogger("collect.serp")

PROVIDERS = {
    "bing": ("https://www.bing.com/search", {"q": None}),
    "duckduckgo": ("https://html.duckduckgo.com/html/", {"q": None}),
    "google": ("https://www.google.com/search", {"q": None, "num": "20"}),
    "yandex": ("https://yandex.ru/search/", {"text": None}),
}

BLOCK_MARKERS = [
    "captcha", "showcaptcha", "are you a robot", "unusual traffic",
    "detected unusual", "consent.google", "before you continue",
    "enable javascript", "access denied", "cf-browser-verification",
]


def _decode_bing(href: str) -> str:
    if "bing.com/ck/a" not in href:
        return href
    m = re.search(r"[?&]u=a1([^&]+)", href)
    if not m:
        return href
    raw = m.group(1)
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw).decode("utf-8", "replace")
    except Exception:
        return href


def _blocked(html: str, provider: str) -> tuple[bool, str]:
    low = html.lower()
    for marker in BLOCK_MARKERS:
        if marker in low:
            return True, marker
    if provider == "yandex" and len(html) < 20000:
        return True, "short response / captcha"
    return False, ""


def parse_results(html: str, provider: str) -> list[dict]:
    out: list[dict] = []
    try:
        doc = lxml.html.fromstring(html)
    except Exception:
        return out
    if provider == "bing":
        for li in doc.xpath("//li[contains(@class,'b_algo')]"):
            a = li.xpath(".//h2//a")
            if not a:
                continue
            href = _decode_bing(a[0].get("href") or "")
            snippet = li.xpath(".//p")
            out.append({
                "url": href,
                "title": clean_text(a[0].text_content()),
                "snippet": clean_text(snippet[0].text_content()) if snippet else "",
            })
    elif provider == "duckduckgo":
        for res in doc.xpath("//div[contains(@class,'result')]"):
            a = res.xpath(".//a[contains(@class,'result__a')]")
            if not a:
                continue
            href = a[0].get("href") or ""
            m = re.search(r"[?&]uddg=([^&]+)", href)
            if m:
                from urllib.parse import unquote
                href = unquote(m.group(1))
            sn = res.xpath(".//a[contains(@class,'result__snippet')]")
            out.append({
                "url": href,
                "title": clean_text(a[0].text_content()),
                "snippet": clean_text(sn[0].text_content()) if sn else "",
            })
    elif provider == "google":
        for g in doc.xpath("//div[@class='g'] | //div[contains(@class,'MjjYud')]"):
            a = g.xpath(".//a[@href]")
            if not a:
                continue
            href = a[0].get("href")
            if not href.startswith("http"):
                continue
            out.append({
                "url": href,
                "title": clean_text(a[0].text_content()),
                "snippet": clean_text(" ".join(g.itertext()))[:400],
            })
    elif provider == "yandex":
        for li in doc.xpath("//li[contains(@class,'serp-item')]"):
            a = li.xpath(".//a[@href]")
            if not a:
                continue
            out.append({
                "url": a[0].get("href"),
                "title": clean_text(a[0].text_content()),
                "snippet": clean_text(" ".join(li.itertext()))[:400],
            })
    # de-duplicate by url preserving order
    seen = set()
    uniq = []
    for r in out:
        if not r["url"] or r["url"] in seen:
            continue
        seen.add(r["url"])
        uniq.append(r)
    return uniq


def collect(client: HttpClient, providers: list[str], queries: list[str]) -> list[dict]:
    records: list[dict] = []
    for provider in providers:
        base, params_tpl = PROVIDERS[provider]
        for q in queries:
            params = {k: (q if v is None else v) for k, v in params_tpl.items()}
            headers = {}
            if provider in ("bing", "duckduckgo", "google"):
                headers["User-Agent"] = config.BROWSER_UA
            r = client.get(base, params=params, timeout=45, headers=headers)
            blocked, marker = _blocked(r.text, provider) if r.ok else (True, f"http {r.status}")
            rows = [] if blocked else parse_results(r.text, provider)
            if not blocked and not rows:
                blocked, marker = True, "no parseable results (JS/consent/empty SERP)"
            if blocked:
                log.info("serp %-10s %-52r -> UNUSABLE (%s)", provider, q[:52], marker)
            else:
                log.info("serp %-10s %-52r -> %d results", provider, q[:52], len(rows))
            qhash = hashlib.sha1(f"{provider}:{q}".encode()).hexdigest()[:12]
            if blocked:
                records.append({
                    "id": f"serp_{qhash}_b",
                    "provider": provider,
                    "query": q,
                    "rank": 0,
                    "url": "",
                    "title": "",
                    "snippet": "",
                    "blocked": 1,
                    "note": marker,
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
            for i, row in enumerate(rows, 1):
                records.append({
                    "id": f"serp_{qhash}_{i}",
                    "provider": provider,
                    "query": q,
                    "rank": i,
                    "url": row["url"],
                    "title": row["title"][:500],
                    "snippet": row["snippet"][:1000],
                    "blocked": 0,
                    "note": "",
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
    return records
