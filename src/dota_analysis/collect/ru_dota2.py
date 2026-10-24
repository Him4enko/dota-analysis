from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import lxml.html

from .. import config, quality
from ..net import HttpClient
from ..text import clean_text

log = logging.getLogger("collect.dota2ru")

BASE = "https://dota2.ru"

HDRS = {"User-Agent": config.BROWSER_UA, "Accept-Language": "ru,en;q=0.8"}
SECTIONS = {
    "obschii-voprosy-i-obsuzhdenija.5": "Общие вопросы",
    "obitel-nytja.175": "Обитель нья",
    "obnovlenija-patchi-i-iventy.184": "Патчи и ивенты",
    "texnicheskaja-podderzhka.47": "Тех. поддержка",
}

KEYWORDS = [
    "поведен", "порядочн", "репорт", "жалоб", "токсич", "бан", "забан",
    "приоритет", "низк", "комменд", "мьют", "мут", "наказан", "овервоч",
    "overwatch", "behavior", "conduct", "lp", "лиф",
]


def _matches(text: str) -> str | None:
    low = text.lower()
    for kw in KEYWORDS:
        if kw in low:
            return kw
    return None


def crawl_thread_links(client: HttpClient, max_pages: int = 6) -> dict[str, dict]:
    threads: dict[str, dict] = {}
    for slug, name in SECTIONS.items():
        for page in range(1, max_pages + 1):
            url = f"{BASE}/forum/forums/{slug}/" + ("" if page == 1 else f"page-{page}")
            r = client.get(url, timeout=45, headers=HDRS)
            if not r.ok:
                log.info("dota2.ru %s p%d -> %s", slug, page, r.status)
                break
            try:
                doc = lxml.html.fromstring(r.text)
            except Exception:
                break
            found = 0
            for a in doc.xpath("//a[contains(@href,'/forum/threads/')]"):
                href = a.get("href") or ""
                title = clean_text(a.text_content())
                if not href or not title or len(title) < 8:
                    continue
                hit = _matches(title)
                if not hit:
                    continue
                full = urljoin(BASE, href)
                if full in threads:
                    continue
                threads[full] = {"url": full, "title": title, "query": hit, "section": name}
                found += 1
            log.info("dota2.ru %-34s p%d -> %d matching threads", name, page, found)
            if not doc.xpath("//*[contains(@class,'pagination')]"):
                break
    return threads


def parse_thread(page_html: str, thread: dict) -> list[dict]:
    docs: list[dict] = []
    try:
        doc = lxml.html.fromstring(page_html)
    except Exception:
        return docs
    for post in doc.xpath("//div[contains(@class,'forum-theme__item') and @data-id]"):
        body_el = post.xpath(".//blockquote[starts-with(@id,'message-content-')]")
        if not body_el:
            continue
        node = body_el[0]
        for quote in node.xpath(".//div[contains(@class,'bbCodeQuote')]"):
            quote.drop_tree()
        text = clean_text(node.text_content())
        if not text:
            continue
        author = post.get("data-username") or ""
        mid = post.get("data-id") or ""
        ts = 0
        time_el = post.xpath(".//time[@data-time]")
        if time_el:
            try:
                ts = int(time_el[0].get("data-time"))
            except Exception:
                ts = 0
        if not mid:
            mid = f"{abs(hash(text)) % 10**12}"
        docs.append({
            "id": f"dota2ru_{mid}",
            "source": "Dota2.ru",
            "source_type": "forum_post",
            "url": thread["url"],
            "title": thread["title"] if not docs else "",
            "body": text,
            "author": author,
            "created_utc": ts,
            "score": 0,
            "num_comments": 0,
            "query": thread.get("query", ""),
            "extra": {"section": thread.get("section", "")},
        })
    return docs


def collect(client: HttpClient, max_threads: int = 120, max_pages: int = 6) -> list[dict]:
    threads = crawl_thread_links(client, max_pages=max_pages)
    log.info("dota2.ru threads to fetch: %d", len(threads))
    docs: list[dict] = []
    ok = failed = 0
    for i, t in enumerate(list(threads.values())[:max_threads], 1):
        r = client.get(t["url"], timeout=45, headers=HDRS)
        if not r.ok:
            failed += 1
            continue
        ok += 1
        docs.extend(parse_thread(r.text, t))
        if i % 10 == 0:
            log.info("dota2.ru %d/%d docs=%d", i, min(len(threads), max_threads), len(docs))
    quality.record("dota2ru", threads_found=len(threads), threads_ok=ok,
                   threads_failed=failed, docs=len(docs))
    return docs
