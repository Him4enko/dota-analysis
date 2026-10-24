from __future__ import annotations

import logging
from datetime import datetime, timezone

from .. import config, quality
from ..net import HttpClient
from ..text import clean_text

log = logging.getLogger("collect.github")

API = "https://api.github.com/search/issues"


def collect(client: HttpClient, repos: list[str], queries: list[str],
            per_page: int = 100, max_pages: int = 2) -> list[dict]:
    docs: dict[str, dict] = {}
    failed = 0
    for repo in repos:
        for q in queries:
            for page in range(1, max_pages + 1):
                params = {
                    "q": f'repo:{repo} "{q}"',
                    "per_page": per_page,
                    "page": page,
                    "sort": "created",
                    "order": "desc",
                }
                r = client.get(API, params=params, timeout=45,
                               headers={"Accept": "application/vnd.github+json"})
                if not r.ok:
                    failed += 1
                    log.info("github %s %r p%d -> %s %s", repo, q, page, r.status, r.text[:120])
                    break
                try:
                    payload = r.json()
                except Exception:
                    break
                items = payload.get("items") or []
                for it in items:
                    created = it.get("created_at") or ""
                    try:
                        ts = int(datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
                                 .replace(tzinfo=timezone.utc).timestamp())
                    except Exception:
                        ts = 0
                    if ts and ts < 1672531200:  # 2023-01-01
                        continue
                    docs[it["id"]] = {
                        "id": f"github_{it['id']}",
                        "source": "GitHub (Dota 2 tracker)",
                        "source_type": "issue",
                        "url": it.get("html_url", ""),
                        "title": it.get("title") or "",
                        "body": clean_text(it.get("body") or ""),
                        "author": (it.get("user") or {}).get("login", ""),
                        "created_utc": ts,
                        "score": it.get("reactions", {}).get("total_count", 0) or 0,
                        "num_comments": it.get("comments", 0) or 0,
                        "query": q,
                        "extra": {"repo": repo, "state": it.get("state"),
                                  "labels": [l["name"] for l in it.get("labels") or []]},
                    }
                if len(items) < per_page:
                    break
    quality.record("github", failed=failed, docs=len(docs))
    log.info("github docs=%d", len(docs))
    return list(docs.values())
