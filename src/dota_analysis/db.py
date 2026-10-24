from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    url          TEXT,
    title        TEXT,
    body         TEXT,
    author       TEXT,
    created_utc  INTEGER,
    lang         TEXT,
    score        INTEGER,
    num_comments INTEGER,
    query        TEXT,
    extra        TEXT,
    collected_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_doc_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_doc_created ON documents(created_utc);

CREATE TABLE IF NOT EXISTS players (
    month      TEXT PRIMARY KEY,
    avg_players REAL,
    peak_players REAL,
    gain_pct    REAL,
    source      TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id       TEXT PRIMARY KEY,
    date_utc INTEGER,
    title    TEXT,
    url      TEXT,
    kind     TEXT
);

CREATE TABLE IF NOT EXISTS serp (
    id       TEXT PRIMARY KEY,
    provider TEXT,
    query    TEXT,
    rank     INTEGER,
    url      TEXT,
    title    TEXT,
    snippet  TEXT,
    blocked  INTEGER,
    note     TEXT,
    fetched_at TEXT
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def upsert_documents(con: sqlite3.Connection, docs: Iterable[dict]) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for d in docs:
        rows.append((
            d["id"], d["source"], d["source_type"], d.get("url", ""),
            (d.get("title") or "")[:2000], (d.get("body") or "")[:20000],
            d.get("author", ""), int(d.get("created_utc") or 0), d.get("lang", "unknown"),
            int(d.get("score") or 0), int(d.get("num_comments") or 0),
            d.get("query", ""), json.dumps(d.get("extra") or {}, ensure_ascii=False)[:4000],
            d.get("collected_at") or now,
        ))
    if not rows:
        return 0
    con.executemany(
        """INSERT INTO documents
           (id, source, source_type, url, title, body, author, created_utc, lang,
            score, num_comments, query, extra, collected_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             title=excluded.title, body=excluded.body, score=excluded.score,
             num_comments=excluded.num_comments""",
        rows,
    )
    con.commit()
    return len(rows)


def load_documents(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM documents", con)
    if not df.empty:
        df["extra"] = df["extra"].apply(lambda s: json.loads(s) if s else {})
    return df


def upsert_players(con: sqlite3.Connection, rows: list[dict]) -> int:
    con.executemany(
        """INSERT INTO players (month, avg_players, peak_players, gain_pct, source)
           VALUES (?,?,?,?,?)
           ON CONFLICT(month) DO UPDATE SET
             avg_players=excluded.avg_players, peak_players=excluded.peak_players,
             gain_pct=excluded.gain_pct, source=excluded.source""",
        [(r["month"], r["avg_players"], r["peak_players"], r.get("gain_pct"), r.get("source", "steamcharts"))
         for r in rows],
    )
    con.commit()
    return len(rows)


def upsert_events(con: sqlite3.Connection, rows: list[dict]) -> int:
    con.executemany(
        """INSERT INTO events (id, date_utc, title, url, kind) VALUES (?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET title=excluded.title, kind=excluded.kind""",
        [(r["id"], int(r["date_utc"]), r["title"], r.get("url", ""), r.get("kind", "patch"))
         for r in rows],
    )
    con.commit()
    return len(rows)


def upsert_serp(con: sqlite3.Connection, rows: list[dict]) -> int:
    con.executemany(
        """INSERT OR REPLACE INTO serp
           (id, provider, query, rank, url, title, snippet, blocked, note, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [(r["id"], r["provider"], r["query"], r.get("rank", 0), r.get("url", ""),
          r.get("title", ""), r.get("snippet", ""), int(r.get("blocked", 0)),
          r.get("note", ""), r.get("fetched_at", "")) for r in rows],
    )
    con.commit()
    return len(rows)


def table_counts(con: sqlite3.Connection) -> dict:
    out = {}
    for t in ("documents", "players", "events", "serp"):
        out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return out
