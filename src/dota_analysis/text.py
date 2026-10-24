from __future__ import annotations

import hashlib
import html
import re
from typing import Iterable

import lxml.html

_WS = re.compile(r"\s+")
_CYR = re.compile(r"[а-яёА-ЯЁ]")
_LAT = re.compile(r"[A-Za-z]")
_TAG = re.compile(r"<[^>]+>")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    if "<" in raw:
        try:
            doc = lxml.html.fromstring(f"<div>{raw}</div>")
            raw = doc.text_content()
        except Exception:
            raw = _TAG.sub(" ", raw)
    raw = html.unescape(raw)
    raw = raw.replace("\u00a0", " ")
    return _WS.sub(" ", raw).strip()


def clean_text(raw: str) -> str:
    txt = strip_html(raw or "")
    txt = re.sub(r"\[removed\]|\[deleted\]", " ", txt)
    txt = re.sub(r"https?://\S+", " ", txt)
    txt = re.sub(r"\s+([,.!?;:])", r"\1", txt)
    return _WS.sub(" ", txt).strip()


def detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cyr = len(_CYR.findall(text))
    lat = len(_LAT.findall(text))
    total = cyr + lat
    if total < 3:
        return "unknown"
    if cyr / total >= 0.35:
        return "ru"
    if lat / total >= 0.9:
        return "en"
    return "mixed"


def content_hash(text: str) -> str:
    norm = re.sub(r"[^0-9a-zа-яё]+", "", (text or "").lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:20]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[0-9a-zа-яё]{2,}", (text or "").lower())


def _shingles(tokens: Iterable[str], k: int = 5) -> set[str]:
    toks = list(tokens)
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


class MinHash:
    """Small deterministic MinHash + LSH for near-duplicate detection."""

    def __init__(self, perms: int = 64, bands: int = 16):
        self.perms = perms
        self.bands = bands
        self.rows = perms // bands
        self._seeds = [int(hashlib.md5(str(i).encode()).hexdigest()[:8], 16) for i in range(perms)]
        self.buckets: dict[tuple[int, int], list[int]] = {}

    @staticmethod
    def _hash64(s: str) -> int:
        return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")

    def signature(self, text: str) -> tuple[int, ...]:
        sh = _shingles(_tokens(text))
        if not sh:
            return tuple([0] * self.perms)
        hashes = [self._hash64(s) for s in sh]
        mask = (1 << 64) - 1
        return tuple(min((h ^ seed) & mask for h in hashes) for seed in self._seeds)

    def add(self, idx: int, sig: tuple[int, ...]) -> set[int]:
        candidates: set[int] = set()
        for b in range(self.bands):
            chunk = sig[b * self.rows:(b + 1) * self.rows]
            key = (b, chunk)
            for other in self.buckets.get(key, []):
                candidates.add(other)
            self.buckets.setdefault(key, []).append(idx)
        return candidates

    @staticmethod
    def jaccard(a: tuple[int, ...], b: tuple[int, ...]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        same = sum(1 for x, y in zip(a, b) if x == y)
        return same / len(a)


def is_probable_spam(text: str) -> bool:
    t = (text or "").lower()
    if len(t) < 12:
        return True
    if len(set(_tokens(t))) < 4:
        return True
    linkish = len(re.findall(r"https?://|www\.", t))
    if linkish >= 3 and len(t) < 400:
        return True
    if re.search(r"(free (skins|items|mmr)|boost your|cheap mmr|купи(ть)? (аккаунт|mmr|буст))", t):
        return True
    return False
