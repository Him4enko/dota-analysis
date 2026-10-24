"""Collect raw material for the Dota 2 conduct-system complaint study.

Usage:
    python scripts/collect.py --only players,github,steam
    python scripts/collect.py --offline          # replay cached responses only
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dota_analysis import collect, config, db, quality  # noqa: E402
from dota_analysis.net import HttpClient, setup_logging  # noqa: E402

ALL = ["players", "github", "steam", "arctic", "dota2ru", "serp", "rss"]

QUALITY_KEYS = {
    "steam": ["steam_search", "steam_threads"],
    "arctic": ["arctic"],
    "dota2ru": ["dota2ru"],
    "github": ["github"],
    "rss": ["reddit_rss"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(ALL))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--steam-threads", type=int, default=180)
    ap.add_argument("--arctic-posts", action="store_true",
                    help="also try Arctic Shift post-title search (often times out)")
    args = ap.parse_args()
    setup_logging()
    log = logging.getLogger("collect")

    steps = [s.strip() for s in args.only.split(",") if s.strip()]
    client = HttpClient(offline=args.offline)
    con = db.connect()
    summary: dict[str, object] = {}

    for step in steps:
        log.info("=== %s ===", step)
        quality.reset(QUALITY_KEYS.get(step, []))
        try:
            if step == "players":
                summary[step] = collect.collect_players(client, con)
            elif step == "github":
                summary[step] = collect.collect_github(client, con)
            elif step == "steam":
                summary[step] = collect.collect_steam(client, con, args.steam_threads)
            elif step == "arctic":
                summary[step] = collect.collect_arctic(client, con, posts=args.arctic_posts)
            elif step == "dota2ru":
                summary[step] = collect.collect_dota2ru(client, con)
            elif step == "serp":
                summary[step] = collect.collect_serp(client, con)
            elif step == "rss":
                summary[step] = collect.collect_rss(client, con)
            else:
                log.warning("unknown step %s", step)
        except Exception as exc:  # keep going: one source failing must not kill the run
            log.exception("step %s failed: %s", step, exc)
            summary[step] = f"FAILED: {exc}"

    client.save_status()
    log.info("counts: %s", db.table_counts(con))
    log.info("summary: %s", summary)


if __name__ == "__main__":
    main()
