from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
RAW_DIR = DATA_DIR / "raw"
PROC_DIR = DATA_DIR / "processed"
VAL_DIR = DATA_DIR / "validation"
REPORT_DIR = ROOT / "reports"
FIG_DIR = REPORT_DIR / "figures"
DB_PATH = DATA_DIR / "dota_analysis.sqlite"
STATUS_PATH = DATA_DIR / "collection_status.json"

for _p in (CACHE_DIR, RAW_DIR, PROC_DIR, VAL_DIR, REPORT_DIR, FIG_DIR):
    _p.mkdir(parents=True, exist_ok=True)

APP_ID = 570
CONTACT = os.environ.get("DOTA_RESEARCH_CONTACT", "research@example.org")
USER_AGENT = (
    "DotaConductResearch/1.0 (non-commercial media analysis; "
    f"contact: {CONTACT}) python-requests"
)
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Analysis window. Upper bound is "now" at collection time.
DATE_FROM = "2023-01-01"
DATE_TO = None  # None -> now

# Reddit
SUBREDDITS = ["DotA2", "TrueDoTA2"]

# Arctic Shift API (public Reddit archive). Used for comments full-text search.
ARCTIC_BASE = "https://arctic-shift.photon-reddit.com"

# Exact substrings used for Arctic Shift full-text queries.
ARCTIC_COMMENT_QUERIES = [
    "behavior score",
    "behavior score dropped",
    "conduct summary",
    "communication score",
    "low priority",
    "false report",
    "report system",
    "toxic teammates",
    "reported for no reason",
]

ARCTIC_COMMENT_QUERIES_RU = [
    "рейтинг поведения",
    "низкий приоритет",
    "репорт",
    "токсич",
]

ARCTIC_QUERIES_BY_SUB = {
    "DotA2": ["behavior score", "behavior score dropped", "conduct summary",
              "low priority", "report system", "рейтинг поведения", "репорт"],
    "TrueDoTA2": ["behavior score", "low priority"],
}

# Reddit RSS search (post titles + selftext). Rate limited aggressively.
RSS_QUERIES = [
    '"behavior score"',
    '"conduct summary"',
    '"communication score"',
    '"low priority"',
    '"behavior score" dropped',
    '"behavior score" unfair',
    '"report system"',
    'overwatch dota',
]

RSS_QUERIES_RU = [
    "рейтинг поведения",
    "низкий приоритет дота",
    "токсичность дота 2",
    "бан чата дота",
    "порядочность дота",
]

# Steam Community discussions
STEAM_SEARCH_QUERIES = [
    "behavior score",
    "behavior score dropped",
    "behavior score not updating",
    "conduct summary",
    "communication score",
    "comm score",
    "low priority",
    "overwatch",
    "false report",
    "report system",
    "toxic players",
    "matchmaking ban",
    "commend",
]
STEAM_MAX_PAGES = 6
STEAM_THREAD_LIMIT = 250

# Russian community forum
DOTA2RU_SEARCH = "https://dota2.ru/forum/search/?q={q}"
DOTA2RU_QUERIES = [
    "рейтинг поведения",
    "низкий приоритет",
    "репорты",
    "токсичность",
    "бан чата",
    "порядочность",
]

# GitHub (dev.dota2.com was migrated to ValveSoftware/Dota2 issue tracker)
GITHUB_REPOS = ["ValveSoftware/Dota2-Gameplay"]
GITHUB_QUERIES = [
    "behavior score",
    "conduct",
    "report system",
    "low priority",
    "communication score",
    "overwatch",
    "mute",
]

# Search engines for discovery / coverage audit
SERP_PROVIDERS = ["bing", "duckduckgo", "google", "yandex"]
SERP_QUERIES = [
    'dota 2 "behavior score" проблема',
    'dota 2 "behavior score" unfair',
    'дота 2 "рейтинг поведения" несправедливо',
    'dota 2 "низкий приоритет" форум',
    'dota 2 "conduct summary" complaints',
    'site:reddit.com dota 2 behavior score broken',
    'site:steamcommunity.com dota 2 behavior score',
    'site:dota2.ru рейтинг поведения',
]

# Player statistics
STEAMCHARTS_URL = "https://steamcharts.com/app/570"
STEAM_PLAYERS_API = (
    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)
STEAM_NEWS_API = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

# HTTP politeness
MIN_INTERVAL = {
    "www.reddit.com": 6.0,
    "reddit.com": 6.0,
    "arctic-shift.photon-reddit.com": 3.0,
    "steamcommunity.com": 8.0,
    "steamcharts.com": 3.0,
    "api.steampowered.com": 1.0,
    "dota2.ru": 4.0,
    "www.bing.com": 5.0,
    "html.duckduckgo.com": 5.0,
    "www.google.com": 5.0,
    "yandex.ru": 5.0,
    "api.github.com": 2.5,
}
DEFAULT_INTERVAL = 3.0

# Classification vocabulary
CONDUCT_TERMS = [
    # EN
    "behavior score", "behaviour score", "conduct summary", "commend", "commendation",
    "communication score", "comm score", "low priority", "lp ", "overwatch",
    "report", "reported", "reporting", "toxic", "toxicity", "grief", "griefing",
    "mute", "muted", "ban", "banned", "penalty", "punish", "punished", "abandon",
    "abandoned", "matchmaking ban", "behavior", "behaviour", "conduct",
    # RU
    "рейтинг поведения", "уровень поведения", "поведени", "порядочн",
    "низкий приоритет", "приоритет", "репорт", "репорты", "токсич", "токсик",
    "бан", "забан", "мьют", "мут", "комменд", "наказан", "штраф", "абуз",
    "жалоб", "пожаловал", "лиф",
]

NEGATIVE_TERMS = [
    "broken", "unfair", "unjust", "ridiculous", "absurd", "garbage", "trash",
    "useless", "terrible", "awful", "horrible", "worst", "scam", "scammed",
    "punished for nothing", "no reason", "for nothing", "false", "wrongly",
    "not updating", "doesn't update", "does not update", "dropped", "drop",
    "decreased", "decrease", "went down", "goes down", "lost points", "rigged",
    "ignored", "no explanation", "no transparency", "opaque", "abuse",
    "stuck", "stuck at", "not going up", "isn't going up", "is not going up",
    "doesn't go up", "not moving", "keeps going down", "keeps dropping",
    "only going down", "going down", "no matter how", "no appeal", "no explanation",
    "revert", "rework", "remove the system", "disable the system", "unfairness",
    "reported me", "reported for", "got reported", "wrongly banned", "mistakenly",
    "penalty", "punished", "punishment", "suspension", "suspended", "restricted",
    "blocked from playing", "unable to play", "can't play", "cannot play", "can't chat",
    "incorrect", "mistake", "mistakenly", "wrong penalty", "no reason given",
    "наказали", "ограничени", "заблокировали", "не могу играть", "не могу общать",
    "недоволен", "не устраивает", "не нравится", "жалуюсь",

    "fed up", "sick of", "tired of", "frustrating", "frustrated", "annoying",
    "angry", "pissed", "hate", "ruined", "ruining", "cancer", "dead game",
    "quit", "uninstall", "support is useless", "valve doesn't care", "valve dont care",
    "не работает", "несправедлив", "нечестн", "сломан", "сломали", "ужас",
    "кошмар", "бред", "абсурд", "мусор", "отстой", "терпеть", "надоел",
    "задолбал", "бесит", "бесят", "злюсь", "ненавиж", "кинули", "за что",
    "ни за что", "без причины", "снизил", "снизился", "упал", "упало",
    "понизил", "понизился", "не повышается", "не растёт", "не растет",
    "не обновляется", "забанили", "забанил", "неправильн", "произвол",
    "игнорир", "нет прозрачности", "непонятн", "обидно",
    "застрял", "не растет", "не растёт", "не повышается", "не поднимается",
    "снижают", "снимают", "понижают", "не меняется", "не обновляется",
    "почините", "исправьте", "уберите", "переработайте", "верните",
    "достало", "надоело", "задолбало", "идиотизм", "ублюдочная", "конченная",

]

COMPLAINT_PATTERNS = [
    r"why (was|did|am|are) .{0,40}(banned|muted|reported|lp|low priority)",
    r"why .{0,30}(score|behavior|behaviour).{0,30}(drop|decreas|went down|fell|lower)",
    r"(how|why) .{0,40}(fair|possible|allowed).{0,40}(ban|report|mute|score)",
    r"(fix|revert|remove|improve)\b.{0,40}\b(system|score|matchmaking|report)",
    r"(got|getting|been)\s+(banned|muted|reported|lp|low priority)",
    r"(lost|dropped|decreased|fell|went down)\s.{0,30}(score|points|behavior|behaviour)",
    r"(support|valve|devs?)\s.{0,30}(ignore|don'?t care|useless|silent)",
    r"нет\s+(смысла|толка|обратной связи|ответа)",
    r"(за|из-за)\s+(репорт|жалоб|токсич).{0,40}(бан|наказан|приоритет)",
    r"(почему|за что).{0,40}(бан|репорт|наказан|снизил|упал|несправедлив)",
    r"(снизил|упал|понизил).{0,30}(рейтинг|поведени|очк)",
    r"(система|репорт|поведени).{0,30}(не работа|сломал|несправедлив|произвол)",
    r"(behavior|behaviour|communication|comm|conduct).{0,35}(stuck|not (going|moving|updating|changing)|isn'?t (going|moving|updating)|keeps? (going down|dropping)|only (going down|decreas))",
    r"(порядочн|поведени|вежливост|рейтинг).{0,35}(не (раст|повыш|подним|меня|обновл)|застрял|снижа|снима|понижа)",
    r"(report|reported|репорт).{0,45}(ban|banned|mute|lp|low priority|наказ|бан|мут|лп)",
    r"(please|pls|valve).{0,35}(fix|revert|remove|rework|disable)",
    r"(уберите|удалите|переработайте|почините|исправьте|верните).{0,45}(систем|репорт|вежлив|порядочн|поведени)",
    r"(incorrect|wrong|false|unfair|mistaken).{0,35}(penalt|ban|mute|report|suspend|restrict|score)",
    r"(penalt|ban|mute|suspend|restrict|score).{0,35}(incorrect|wrong|false|unfair|mistake)",
    r"(can't|cannot|unable|blocked).{0,35}(play|chat|communicat|match|queue)",
    r"(please|need help|help me).{0,45}(behavior|behaviour|conduct|comm|score|ban|mute|penalt)",
    r"(жалоб|недоволен|не устраивает|не нравится).{0,45}(систем|репорт|вежлив|порядочн|поведени)",
    r"(систем|репорт|вежлив|порядочн|поведени).{0,45}(убивает|ломает|не решает|не работает|сломали)",
    r"(забан|замьютил|мут|лп|низкий приоритет|наказан).{0,45}(за|из-за|без|ни за что)",
]

QUESTION_PATTERNS = [
    r"^(how|what|why|when|where|which|can|does|do|is|are|should|anyone|has anyone)\b",
    r"^(как|что|кто|где|почему|зачем|когда|какой|можно|стоит|нужно|есть ли|подскажите|объясните)\b",
]

POSITIVE_TERMS = [
    "works well", "working as intended", "fair system", "good system",
    "improved", "thanks valve", "well deserved", "deserved ban", "good job",
    "справедлив", "работает", "хорошая система", "заслуженн", "спасибо",
    "улучшил", "помогло", "правильн",
]
