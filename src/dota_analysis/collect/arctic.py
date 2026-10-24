from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .. import config, quality
from ..net import HttpClient

log = logging.getLogger("collect.arctic")

FIELDS_COMMENT = "id,author,body,created_utc,score,link_id,parent_id,subreddit"
FIELDS_POST = "id,author,title,selftext,created_utc,score,num_comments,subreddit,permalink,link_flair_text"


def _iso(ts: int | None) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else ""


def _search_comments(client: HttpClient, params: dict) -> tuple[int, list]:
    """Arctic Shift occasionally answers 422 'Timeout' on heavy queries.
    Back off briefly instead of hammering; callers treat failures as gaps."""
    for attempt in range(2):
        r = client.get(config.ARCTIC_BASE + "/api/comments/search", params=params, timeout=90)
        if r.ok:
            try:
                return r.status, (r.json().get("data") or [])
            except Exception:
                return r.status, []
        if r.status == 422 and "Timeout" in (r.text or "") and attempt == 0:
            time.sleep(4)
            continue
        return r.status, []
    return 422, []


def _quarter_windows(date_from: str) -> list[tuple[str, str]]:
    cur = datetime.strptime(date_from, "%Y-%m-%d")
    now = datetime.now()
    out = []
    while cur < now:
        month = cur.month + 3
        year = cur.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        nxt = cur.replace(year=year, month=month, day=1)
        out.append((cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d")))
        cur = nxt
    return out


def collect_comments(client: HttpClient, subreddits: list[str], queries: list[str],
                     date_from: str = config.DATE_FROM, per_window: int = 100,
                     max_windows: int | None = None) -> list[dict]:
    """Systematic time-stratified sample of comments.

    For every (subreddit, query, quarter) cell we take one page of up to
    ``per_window`` matching comments. The sort direction alternates by quarter
    so that the within-quarter sampling is not systematically biased towards
    either end of the quarter. Every requested cell - empty or not - is logged,
    which lets the report quantify coverage and non-response.
    """
    docs: dict[str, dict] = {}
    windows = _quarter_windows(date_from)
    if max_windows:
        windows = windows[-max_windows:]
    cells = ok = failed = 0
    for sub in subreddits:
        for q in queries:
            for i, (start, end) in enumerate(windows):
                sort = "desc" if i % 2 == 0 else "asc"
                params = {
                    "subreddit": sub,
                    "body": q,
                    "limit": per_window,
                    "sort": sort,
                    "fields": FIELDS_COMMENT,
                    "after": start,
                    "before": end,
                }
                cells += 1
                status, data = _search_comments(client, params)
                if status != 200:
                    failed += 1
                    log.info("arctic %s | %-24s | %s -> %s", sub, q, start[:7], status)
                    continue
                ok += 1
                for c in data:
                    cid = str(c.get("id"))
                    if not cid or cid in docs:
                        continue
                    link = str(c.get("link_id") or "").replace("t3_", "")
                    docs[cid] = {
                        "id": f"reddit_comment_{cid}",
                        "source": "Reddit",
                        "source_type": "comment",
                        "url": f"https://www.reddit.com/comments/{link}/_/{cid}/",
                        "title": "",
                        "body": c.get("body") or "",
                        "author": c.get("author") or "",
                        "created_utc": int(c.get("created_utc") or 0),
                        "score": c.get("score") or 0,
                        "num_comments": 0,
                        "query": q,
                        "extra": {
                            "subreddit": c.get("subreddit") or sub,
                            "link_id": c.get("link_id") or "",
                            "parent_id": c.get("parent_id") or "",
                            "window": start[:7],
                        },
                    }
                log.info("arctic %s | %-24s | %s -> %d", sub, q, start[:7], len(data))
    quality.record("arctic", cells=cells, ok=ok, failed=failed, docs=len(docs))
    return list(docs.values())


def collect_posts_by_title(client: HttpClient, subreddit: str, keywords: list[str],
                           date_from: str = config.DATE_FROM) -> list[dict]:
    """Title keyword search. Arctic Shift can time out on very active
    subreddits, so each keyword is queried over monthly windows and failed
    windows are tolerated (they show up as gaps in coverage)."""
    docs: dict[str, dict] = {}
    for kw in keywords:
        for start, end in _quarter_windows(date_from):
            params = {
                "subreddit": subreddit,
                "title": kw,
                "limit": 100,
                "sort": "desc",
                "fields": FIELDS_POST,
                "after": start,
                "before": end,
            }
            r = client.get(config.ARCTIC_BASE + "/api/posts/search", params=params, timeout=75)
            if not r.ok:
                continue
            try:
                data = r.json().get("data") or []
            except Exception:
                continue
            for p in data:
                pid = str(p.get("id"))
                if not pid:
                    continue
                docs[pid] = {
                    "id": f"reddit_post_{pid}",
                    "source": "Reddit",
                    "source_type": "post",
                    "url": f"https://www.reddit.com{(p.get('permalink') or '')}",
                    "title": p.get("title") or "",
                    "body": p.get("selftext") or "",
                    "author": p.get("author") or "",
                    "created_utc": int(p.get("created_utc") or 0),
                    "score": p.get("score") or 0,
                    "num_comments": p.get("num_comments") or 0,
                    "query": kw,
                    "extra": {"subreddit": p.get("subreddit") or subreddit},
                }
            time.sleep(0.6)
    return list(docs.values())
