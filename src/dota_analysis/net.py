from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from . import config

log = logging.getLogger("net")


@dataclass
class Response:
    url: str
    status: int
    text: str
    headers: dict
    from_cache: bool = False
    fetched_at: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self.error

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass
class HttpStats:
    requests: int = 0
    cache_hits: int = 0
    errors: int = 0
    rate_limited: int = 0
    blocked: int = 0
    per_host: dict = field(default_factory=dict)

    def note(self, host: str, key: str) -> None:
        h = self.per_host.setdefault(host, {"requests": 0, "cache_hits": 0, "errors": 0, "rate_limited": 0, "blocked": 0})
        h[key] += 1

    def as_dict(self) -> dict:
        return {
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "errors": self.errors,
            "rate_limited": self.rate_limited,
            "blocked": self.blocked,
            "per_host": self.per_host,
        }


class HttpClient:
    """HTTP client with polite rate limiting, retries and an on-disk response cache.

    The cache makes the whole study reproducible offline: a second run with
    ``offline=True`` reads exactly the same bytes that were analysed.
    """

    def __init__(self, cache_dir: Path | None = None, offline: bool = False,
                 ttl_days: int = 30, max_retries: int = 2,
                 cooldown_minutes: int = 25):
        self.cache_dir = Path(cache_dir or config.CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.ttl = ttl_days * 86400
        self.max_retries = max_retries
        self.cooldown = cooldown_minutes * 60
        self._cooldown_path = config.DATA_DIR / "host_cooldowns.json"
        self.cooldowns: dict[str, float] = {}
        if self._cooldown_path.exists():
            try:
                self.cooldowns = json.loads(self._cooldown_path.read_text(encoding="utf-8"))
            except Exception:
                self.cooldowns = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        })
        self.stats = HttpStats()
        self._last_call: dict[str, float] = {}

    def _save_cooldowns(self) -> None:
        try:
            self._cooldown_path.write_text(json.dumps(self.cooldowns, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _cooling(self, host: str) -> float:
        until = self.cooldowns.get(host, 0)
        return max(0.0, until - time.time())

    def _start_cooldown(self, host: str) -> None:
        self.cooldowns[host] = time.time() + self.cooldown
        self._save_cooldowns()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    @staticmethod
    def _key(url: str, params: dict | None, data: dict | None) -> str:
        raw = json.dumps([url, params or {}, data or {}], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _throttle(self, host: str) -> None:
        interval = config.MIN_INTERVAL.get(host, config.DEFAULT_INTERVAL)
        interval *= 1 + random.uniform(0.0, 0.35)
        last = self._last_call.get(host)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_call[host] = time.monotonic()

    def get(self, url: str, params: dict | None = None, *, allow_redirects: bool = True,
            ttl_days: int | None = None, headers: dict | None = None,
            timeout: int = 45, host_key: str | None = None) -> Response:
        key = self._key(url, params, None)
        path = self._cache_path(key)
        ttl = (ttl_days if ttl_days is not None else self.ttl // 86400) * 86400

        if path.exists():
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                age = time.time() - blob.get("_ts", 0)
                if self.offline or age <= ttl:
                    self.stats.requests += 1
                    self.stats.cache_hits += 1
                    host = host_key or urlparse(url).netloc
                    self.stats.note(host, "cache_hits")
                    return Response(url=url, status=blob["status"], text=blob["text"],
                                    headers=blob.get("headers", {}), from_cache=True,
                                    fetched_at=blob.get("fetched_at", ""))
            except Exception:
                pass

        if self.offline:
            return Response(url=url, status=0, text="", headers={},
                            error="offline and not cached")

        host = host_key or urlparse(url).netloc
        wait_cd = self._cooling(host)
        if wait_cd > 0:
            log.info("skip %s (cooldown %d min left)", host, int(wait_cd // 60) + 1)
            self.stats.requests += 1
            self.stats.note(host, "rate_limited")
            return Response(url=url, status=429, text="", headers={},
                            error=f"cooldown {int(wait_cd)}s")

        attempt = 0
        last_err = ""
        while attempt <= self.max_retries:
            self._throttle(host)
            self.stats.requests += 1
            self.stats.note(host, "requests")
            try:
                r = self.session.get(url, params=params, timeout=timeout,
                                     allow_redirects=allow_redirects,
                                     headers=headers or {})
            except requests.RequestException as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                self.stats.errors += 1
                self.stats.note(host, "errors")
                time.sleep(2 * (attempt + 1))
                attempt += 1
                continue

            if r.status_code in (429, 403):
                self.stats.rate_limited += (r.status_code == 429)
                self.stats.blocked += (r.status_code == 403)
                self.stats.note(host, "rate_limited" if r.status_code == 429 else "blocked")
                self._start_cooldown(host)
                log.warning("HTTP %s on %s -> skip host for %d min", r.status_code,
                            host, int(self.cooldown // 60))
                return self._store(key, r, url)

            if r.status_code == 503:
                self.stats.blocked += 1
                self.stats.note(host, "blocked")
                self._start_cooldown(host)
                return self._store(key, r, url)

            if r.status_code >= 500:
                self.stats.errors += 1
                self.stats.note(host, "errors")
                if attempt >= self.max_retries:
                    return self._store(key, r, url)
                time.sleep(3 * (attempt + 1))
                attempt += 1
                continue

            return self._store(key, r, url)

        return Response(url=url, status=0, text="", headers={}, error=last_err)

    def _store(self, key: str, r: requests.Response, url: str) -> Response:
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if 200 <= r.status_code < 300:
            path = self._cache_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.write_text(json.dumps({
                    "status": r.status_code,
                    "text": r.text,
                    "headers": {k: v for k, v in r.headers.items()
                                if k.lower() in ("content-type", "retry-after", "date")},
                    "fetched_at": fetched_at,
                    "_ts": time.time(),
                    "url": url,
                }, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:  # pragma: no cover
                log.warning("cache write failed: %s", exc)
        return Response(url=url, status=r.status_code, text=r.text,
                        headers=dict(r.headers), from_cache=False, fetched_at=fetched_at)

    def save_status(self) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "offline": self.offline,
            "stats": self.stats.as_dict(),
        }
        config.STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
