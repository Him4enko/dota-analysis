"""Recover Reddit comments present in the HTTP cache but absent from the corpus.

Strictly offline: this script reads only data/cache and never constructs an
HTTP client or makes network requests.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dota_analysis import config, db, quality  # noqa: E402


def main() -> None:
    con = db.connect()
    existing = {r[0] for r in con.execute(
        "SELECT id FROM documents WHERE source='Reddit'").fetchall()}
    min_ts = int(datetime.strptime(config.DATE_FROM, "%Y-%m-%d")
                 .replace(tzinfo=timezone.utc).timestamp())
    recovered: dict[str, dict] = {}
    rows_scanned = 0
    cache_files = 0

    for path in config.CACHE_DIR.rglob("*.json"):
        try:
            response = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if response.get("status") != 200 or "/api/comments/search" not in response.get("url", ""):
            continue
        if "arctic-shift.photon-reddit.com" not in response.get("url", ""):
            continue
        cache_files += 1
        try:
            comments = json.loads(response.get("text", "")).get("data") or []
        except Exception:
            continue
        rows_scanned += len(comments)
        for c in comments:
            cid = str(c.get("id") or "")
            body = c.get("body") or ""
            ts = int(c.get("created_utc") or 0)
            if not cid or not body or ts < min_ts or f"reddit_comment_{cid}" in existing:
                continue
            link_id = str(c.get("link_id") or "")
            post_id = link_id.removeprefix("t3_")
            subreddit = c.get("subreddit") or "unknown (cached response omitted field)"
            recovered[cid] = {
                "id": f"reddit_comment_{cid}",
                "source": "Reddit",
                "source_type": "comment",
                "url": f"https://www.reddit.com/comments/{post_id}/_/{cid}/" if post_id else "",
                "title": "",
                "body": body,
                "author": c.get("author") or "",
                "created_utc": ts,
                "score": c.get("score") or 0,
                "num_comments": 0,
                "query": "recovered-from-local-http-cache",
                "extra": {
                    "subreddit": subreddit,
                    "link_id": link_id,
                    "parent_id": c.get("parent_id") or "",
                    "recovered_from_cache": True,
                },
            }

    docs = list(recovered.values())
    db.upsert_documents(con, docs)
    out = config.RAW_DIR / "reddit_comments_cache_supplement.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
    quality.reset(["arctic_cache_import"])
    quality.record("arctic_cache_import", cache_files=cache_files,
                   cached_rows_scanned=rows_scanned, new_unique_documents=len(docs))
    print(f"scanned {cache_files} cached responses / {rows_scanned} rows; "
          f"recovered {len(docs)} new Reddit comments -> {out}")
    print(f"database documents: {db.table_counts(con)['documents']}")


if __name__ == "__main__":
    main()
