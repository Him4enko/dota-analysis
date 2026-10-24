from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config

PATH = config.DATA_DIR / "collection_quality.json"


def record(name: str, **counters) -> None:
    data = {}
    if PATH.exists():
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    entry = data.setdefault(name, {})
    for k, v in counters.items():
        if isinstance(v, (int, float)):
            entry[k] = entry.get(k, 0) + v
        else:
            entry[k] = v
    entry["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def reset(names: list[str]) -> None:
    data = load()
    changed = False
    for n in names:
        if n in data:
            data.pop(n, None)
            changed = True
    if changed:
        PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> dict:
    if not PATH.exists():
        return {}
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
