from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import lxml.etree as ET

from .. import quality
from ..net import HttpClient
from ..text import clean_text

log = logging.getLogger("collect.reddit_rss")

ATOM = "{http://www.w3.org/2005/Atom}"
SEARCH = "https://www.reddit.com/r/{sub}/search.rss"


def parse_feed(xml_text: str) -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except Exception:
        return out
    for e in root.findall(f"{ATOM}entry"):
        eid = (e.findtext(f"{ATOM}id") or "").strip()
        title = clean_text(e.findtext(f"{ATOM}title") or "")
        link_el = e.find(f"{ATOM}link")
        url = link_el.get("href") if link_el is not None else ""
        content = e.findtext(f"{ATOM}content") or ""
        updated = e.findtext(f"{ATOM}updated") or ""
        author = e.findtext(f"{ATOM}author/{ATOM}name") or ""
        ts = 0
        if updated:
            try:
                ts = int(datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp())
            except Exception:
                ts = 0
        if not eid.startswith("t3_"):
            continue
        out.append({
            "id": eid,
            "title": title,
            "url": url,
            "body": clean_text(content),
            "author": author.replace("/u/", ""),
            "created_utc": ts,
            "updated": updated,
        })
    return out


def collect(client: HttpClient, subreddits: list[str], queries: list[str],
            max_pages: int = 2) -> list[dict]:
    docs: dict[str, dict] = {}
    ok = failed = 0
    for sub in subreddits:
        for q in queries:
            after = None
            for page in range(max_pages):
                params = {"q": q, "restrict_sr": 1, "sort": "relevance", "t": "all",
                          "limit": 100, "raw_json": 1}
                if after:
                    params["after"] = after
                r = client.get(SEARCH.format(sub=sub), params=params, timeout=45,
                               headers={"Accept": "application/atom+xml,application/xml;q=0.9"})
                if not r.ok:
                    failed += 1
                    log.info("rss %s %r p%d -> %s", sub, q, page, r.status)
                    break
                ok += 1
                rows = parse_feed(r.text)
                if not rows:
                    break
                new = 0
                for row in rows:
                    if row["id"] in docs:
                        continue
                    docs[row["id"]] = {
                        "id": f"reddit_post_{row['id']}",
                        "source": "Reddit",
                        "source_type": "post",
                        "url": row["url"],
                        "title": row["title"],
                        "body": row["body"],
                        "author": row["author"],
                        "created_utc": row["created_utc"],
                        "score": 0,
                        "num_comments": 0,
                        "query": q,
                        "extra": {"subreddit": sub, "via": "rss"},
                    }
                    new += 1
                log.info("rss %-10s %-30r p%d -> %d (%d new)", sub, q[:30], page, len(rows), new)
                after = row_id(rows[-1]) if rows else None
                if not after or new == 0:
                    break
    quality.record("reddit_rss", pages_ok=ok, failed=failed, docs=len(docs))
    return list(docs.values())


def row_id(row: dict) -> str:
    return row["id"]
