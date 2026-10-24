from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import config, db
from ..net import HttpClient
from . import arctic, github_valve, players, reddit_rss, ru_dota2, serp, steam

log = logging.getLogger("collect")


def _dump(name: str, rows: list[dict]) -> None:
    path = config.RAW_DIR / f"{name}.jsonl"
    if not rows:
        path.unlink(missing_ok=True)
        log.info("skip empty raw export: %s", path.name)
        return
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("saved %s -> %s (%d rows)", name, path.name, len(rows))


def collect_players(client: HttpClient, con) -> dict:
    data = players.collect(client)
    if data["players"]:
        db.upsert_players(con, data["players"])
        _dump("players", data["players"])
    if data["events"]:
        db.upsert_events(con, data["events"])
        _dump("events", data["events"])
    return {"months": len(data["players"]), "events": len(data["events"]),
            "current": data["current"]}


def collect_github(client: HttpClient, con) -> int:
    rows = github_valve.collect(client, config.GITHUB_REPOS, config.GITHUB_QUERIES)
    db.upsert_documents(con, rows)
    _dump("github", rows)
    return len(rows)


def collect_steam(client: HttpClient, con, thread_limit: int, queries: list[str] | None = None) -> int:
    queries = queries or config.STEAM_SEARCH_QUERIES
    topics = steam.collect_search(client, queries)
    # topic-level documents are always usable (title + search excerpt)
    topic_docs = [{
        "id": f"steam_topic_{t['gid']}",
        "source": "Steam Community",
        "source_type": "thread",
        "url": t.get("url", ""),
        "title": t.get("title", ""),
        "body": t.get("excerpt", ""),
        "author": t.get("author", ""),
        "created_utc": int(t.get("created_utc") or 0),
        "score": 0,
        "num_comments": int(t.get("num_comments") or 0),
        "query": t.get("query", ""),
        "extra": {"gid": t["gid"], "level": "topic"},
    } for t in topics.values()]
    db.upsert_documents(con, topic_docs)
    docs = steam.fetch_threads(client, topics, limit=thread_limit)
    db.upsert_documents(con, docs)
    _dump("steam", topic_docs + docs)
    return len(topic_docs) + len(docs)


def collect_arctic(client: HttpClient, con, comments: bool = True, posts: bool = False) -> int:
    total = 0
    for sub, queries in config.ARCTIC_QUERIES_BY_SUB.items():
        rows = arctic.collect_comments(client, [sub], queries)
        db.upsert_documents(con, rows)
        _dump(f"reddit_comments_{sub}", rows)
        log.info("arctic %s -> %d docs (total in DB: %d)", sub, len(rows),
                 db.table_counts(con)["documents"])
        total += len(rows)
    if posts:
        rows = arctic.collect_posts_by_title(client, "DotA2", config.RSS_QUERIES)
        db.upsert_documents(con, rows)
        _dump("reddit_posts_arctic", rows)
        total += len(rows)
    return total


def collect_rss(client: HttpClient, con) -> int:
    rows = reddit_rss.collect(client, ["DotA2", "TrueDoTA2"],
                              config.RSS_QUERIES[:6] + config.RSS_QUERIES_RU[:2], max_pages=2)
    db.upsert_documents(con, rows)
    _dump("reddit_rss", rows)
    return len(rows)


def collect_dota2ru(client: HttpClient, con) -> int:
    rows = ru_dota2.collect(client, max_threads=150, max_pages=10)
    db.upsert_documents(con, rows)
    _dump("dota2ru", rows)
    return len(rows)


def collect_serp(client: HttpClient, con) -> int:
    rows = serp.collect(client, config.SERP_PROVIDERS, config.SERP_QUERIES)
    db.upsert_serp(con, rows)
    _dump("serp", rows)
    return len(rows)
