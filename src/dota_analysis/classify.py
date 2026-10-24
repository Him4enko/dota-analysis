from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import config
from .text import detect_lang

THEME_RULES: list[tuple[str, list[str]]] = [
    ("behavior_score", [
        "behavior score", "behaviour score", "conduct summary", "рейтинг поведения",
        "уровень поведения", "behavior", "поведени", "порядочн", "bs ",
    ]),
    ("communication_score", [
        "communication score", "comm score", "comms score", "commend", "коммуникац",
        "комменд", "общение",
    ]),
    ("false_reports", [
        "false report", "reported for no reason", "wrongly report", "report abuse",
        "ложн", "кинули репорт", "ни за что", "без причины", "несправедлив",
    ]),
    ("low_priority", [
        "low priority", "lp ", "low-prio", "низкий приоритет", "лиф", "lpq",
    ]),
    ("overwatch", [
        "overwatch", "овервоч", "review case", "convict", "replay review",
    ]),
    ("mute_chat", [
        "chat ban", "muted", "mute", "comm ban", "бан чата", "мьют", "мут",
        "communication ban",
    ]),
    ("bans", [
        "matchmaking ban", "6 month", "ban wave", "banned", "забанил", "забанен",
        "vak", "vac",
    ]),
    ("matchmaking", [
        "matchmaking", "mmr", "smurf", "booster", "подбор", "смурф", "буст",
    ]),
    ("toxicity", [
        "toxic", "toxicity", "grief", "griefer", "токсич", "руин", "тролл",
    ]),
]


def _compile(terms: list[str], word_boundary: bool = False) -> re.Pattern:
    parts = []
    for t in terms:
        esc = re.escape(t.strip())
        parts.append(rf"\b{esc}" if word_boundary else esc)
    return re.compile("|".join(parts), re.I)


_RELEVANCE = _compile(config.CONDUCT_TERMS)
_NEG = _compile(config.NEGATIVE_TERMS)
_POS = _compile(config.POSITIVE_TERMS)
_PATTERNS = [re.compile(p, re.I | re.S) for p in config.COMPLAINT_PATTERNS]
_QUESTIONS = [re.compile(p, re.I) for p in config.QUESTION_PATTERNS]


@dataclass
class Classification:
    relevant: bool
    stance: str
    theme: str
    lang: str
    neg_hits: list[str] = field(default_factory=list)
    pos_hits: list[str] = field(default_factory=list)
    patterns: int = 0
    confidence: float = 0.0
    neg_score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "relevant": self.relevant,
            "stance": self.stance,
            "theme": self.theme,
            "lang": self.lang,
            "neg_hits": self.neg_hits,
            "pos_hits": self.pos_hits,
            "patterns": self.patterns,
            "confidence": self.confidence,
            "neg_score": self.neg_score,
        }


def _uniq(matches: list[str]) -> list[str]:
    out = []
    seen = set()
    for m in matches:
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def detect_theme(text: str) -> str:
    low = text.lower()
    best = ("other", 0)
    for theme, terms in THEME_RULES:
        score = sum(len(re.findall(re.escape(t), low)) for t in terms)
        if score > best[1]:
            best = (theme, score)
    return best[0]


def classify(title: str, body: str, source_type: str = "") -> Classification:
    text = f"{title or ''}. {body or ''}".strip()
    lang = detect_lang(text)
    rel = [m.group(0) for m in _RELEVANCE.finditer(text)]
    relevant = bool(rel) and len(text) >= 15
    neg = _uniq([m.group(0) for m in _NEG.finditer(text)])
    pos = _uniq([m.group(0) for m in _POS.finditer(text)])
    patterns = sum(1 for p in _PATTERNS if p.search(text))
    q_text = ((title or "").strip() or (body or "").strip())[:220]
    question = any(p.search(q_text) for p in _QUESTIONS)

    neg_score = len(neg) + 1.5 * patterns
    pos_score = len(pos)

    if not relevant:
        stance = "off_topic"
    elif pos_score > neg_score and pos_score >= 1:
        stance = "positive"
    elif question and neg_score < 1.5:
        stance = "question"
    elif neg_score >= 1.5:
        stance = "complaint"
    else:
        stance = "neutral"

    confidence = min(0.99, 0.35 + 0.12 * abs(neg_score - pos_score) + 0.05 * patterns)
    return Classification(
        relevant=relevant,
        stance=stance,
        theme=detect_theme(text),
        lang=lang,
        neg_hits=neg,
        pos_hits=pos,
        patterns=patterns,
        confidence=round(confidence, 3),
        neg_score=neg_score,
    )
