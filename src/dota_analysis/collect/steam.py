from __future__ import annotations

import html
import logging
import re
from typing import Iterable

import lxml.html

from .. import config, quality
from ..net import HttpClient
from ..text import clean_text

log = logging.getLogger("collect.steam")

SEARCH_URL = "https://steamcommunity.com/app/{app}/discussions/search/"


def _tooltip_text(raw: str) -> tuple[str, str]:
    """Return (excerpt, author) from a data-tooltip-forum attribute."""
    if not raw:
        return "", ""
    try:
        frag = lxml.html.fromstring(html.unescape(raw))
    except Exception:
        return clean_text(raw), ""
    excerpt = " ".join(frag.text_content().split())
    author = ""
    m = re.search(r"Posted by:\s*(.+?)\s*,\s*\d", excerpt)
    if m:
        author = m.group(1).strip()
    excerpt = re.sub(r"Posted by:.*$", "", excerpt).strip()
    excerpt = re.sub(r"Last post:.*$", "", excerpt).strip()
    return excerpt, author


def parse_search_page(page_html: str, query: str) -> list[dict]:
    out = []
    try:
        doc = lxml.html.fromstring(page_html)
    except Exception:
        return out
    for block in doc.xpath("//div[contains(@class,'post_searchresult')]"):
        inner = block.xpath(".//div[@data-gidforumtopic]")
        if not inner:
            continue
        holder = inner[0]
        gid = holder.get("data-gidforumtopic") or ""
        if not gid:
            continue
        tooltip = holder.get("data-tooltip-forum") or ""
        excerpt, author = _tooltip_text(tooltip)
        title_el = holder.xpath(".//div[contains(@class,'forum_topic_name')]")
        title = clean_text(title_el[0].text_content()) if title_el else ""
        if not title or len(title) < 15 or title.lower() == query.lower():
            title = excerpt[:160] or title
        link = holder.xpath(".//a[contains(@class,'forum_topic_overlay')]/@href")
        url = link[0] if link else ""
        ts_el = block.xpath(".//*[@data-timestamp]")
        ts = int(ts_el[0].get("data-timestamp")) if ts_el and ts_el[0].get("data-timestamp") else 0
        replies_el = holder.xpath(".//div[contains(@class,'forum_topic_reply_count')]")
        replies = 0
        if replies_el:
            m = re.search(r"\d+", replies_el[0].text_content())
            replies = int(m.group()) if m else 0
        out.append({
            "gid": gid,
            "url": url,
            "title": title,
            "excerpt": excerpt,
            "author": author,
            "created_utc": ts,
            "num_comments": replies,
            "query": query,
        })
    return out


def collect_search(client: HttpClient, queries: Iterable[str], app: int = config.APP_ID,
                   max_pages: int = config.STEAM_MAX_PAGES) -> dict[str, dict]:
    topics: dict[str, dict] = {}
    pages_ok = pages_failed = 0
    for q in queries:
        for p in range(1, max_pages + 1):
            r = client.get(SEARCH_URL.format(app=app), params={"q": q, "p": p}, timeout=60)
            if not r.ok:
                pages_failed += 1
                log.info("steam search %r p%d -> %s", q, p, r.status)
                break
            pages_ok += 1
            rows = parse_search_page(r.text, q)
            if not rows:
                break
            new = 0
            for row in rows:
                if row["gid"] not in topics:
                    topics[row["gid"]] = row
                    new += 1
            log.info("steam search %-26r p%d -> %d results (%d new)", q, p, len(rows), new)
            if new == 0:
                break
    quality.record("steam_search", pages_ok=pages_ok, pages_failed=pages_failed,
                   topics=len(topics))
    return topics


def parse_thread(page_html: str, thread: dict) -> list[dict]:
    docs: list[dict] = []
    try:
        doc = lxml.html.fromstring(page_html)
    except Exception:
        return docs
    thread_title = thread.get("title", "")
    blocks = doc.xpath(
        "//div[contains(@class,'commentthread_comment ') and @id and starts-with(@id,'comment_')]"
    )
    if not blocks:
        body = " ".join(doc.text_content().split())[:20000]
        return [{
            "id": f"steam_{thread['gid']}",
            "source": "Steam Community",
            "source_type": "thread",
            "url": thread.get("url", ""),
            "title": thread_title,
            "body": body,
            "author": thread.get("author", ""),
            "created_utc": int(thread.get("created_utc") or 0),
            "score": 0,
            "num_comments": int(thread.get("num_comments") or 0),
            "query": thread.get("query", ""),
            "extra": {"gid": thread["gid"], "excerpt": thread.get("excerpt", "")},
        }]
    for i, b in enumerate(blocks):
        text_el = b.xpath(".//div[contains(@class,'commentthread_comment_text')]")
        if not text_el:
            continue
        node = text_el[0]
        for quote in node.xpath(".//blockquote[contains(@class,'bb_blockquote')]"):
            quote.drop_tree()
        text = clean_text(node.text_content())
        if not text:
            continue
        author_el = b.xpath(".//a[contains(@class,'commentthread_author_link')]")
        author = clean_text(author_el[0].text_content()) if author_el else ""
        ts = 0
        for el in b.xpath(".//*[@data-timestamp]"):
            v = el.get("data-timestamp")
            if v and v.isdigit():
                ts = int(v)
                break
        if not ts:
            ts = int(thread.get("created_utc") or 0)
        cid = (node.get("id") or f"{thread['gid']}_{i}").replace("comment_content_", "")
        docs.append({
            "id": f"steam_{cid}",
            "source": "Steam Community",
            "source_type": "thread_op" if i == 0 else "thread_comment",
            "url": thread.get("url", ""),
            "title": thread_title if i == 0 else "",
            "body": text,
            "author": author or (thread.get("author", "") if i == 0 else ""),
            "created_utc": ts,
            "score": 0,
            "num_comments": int(thread.get("num_comments") or 0),
            "query": thread.get("query", ""),
            "extra": {"gid": thread["gid"], "thread_title": thread_title},
        })
    return docs


def fetch_threads(client: HttpClient, topics: dict[str, dict], limit: int = 200) -> list[dict]:
    docs: list[dict] = []
    ok = failed = 0
    ordered = sorted(topics.values(), key=lambda t: t.get("created_utc", 0), reverse=True)[:limit]
    for i, t in enumerate(ordered, 1):
        if not t.get("url"):
            continue
        r = client.get(t["url"], timeout=60)
        if not r.ok:
            failed += 1
            log.info("thread %s -> %s", t["gid"], r.status)
            continue
        ok += 1
        docs.extend(parse_thread(r.text, t))
        if i % 10 == 0:
            log.info("steam threads %d/%d, docs=%d", i, len(ordered), len(docs))
    quality.record("steam_threads", ok=ok, failed=failed, docs=len(docs))
    return docs
