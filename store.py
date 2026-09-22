"""sources.json(마스터 소스 목록) / seen_ids.json(scraper.py 개인용) /
guild_state.json(서버별 on-off + 채널 + 알림기록) 읽고 쓰기."""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
SOURCES_FILE = BASE_DIR / "sources.json"
SEEN_FILE = BASE_DIR / "seen_ids.json"
GUILD_STATE_FILE = BASE_DIR / "guild_state.json"


def load_sources() -> list:
    if SOURCES_FILE.exists():
        return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return []


def save_sources(sources: list) -> None:
    SOURCES_FILE.write_text(
        json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_guild_state() -> dict:
    if GUILD_STATE_FILE.exists():
        return json.loads(GUILD_STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_guild_state(state: dict) -> None:
    GUILD_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def default_guild_entry(master_sources: list) -> dict:
    ids = [s["id"] for s in master_sources]
    return {
        "enabled": list(ids),
        "known": list(ids),
        "channel_id": None,
        "seen": [],
    }


def get_guild_entry(guild_state: dict, guild_id: str, master_sources: list) -> dict:
    if guild_id not in guild_state:
        guild_state[guild_id] = default_guild_entry(master_sources)
    return guild_state[guild_id]


def sync_guild_with_master(entry: dict, master_sources: list) -> set:
    """마스터 소스 목록(sources.json)에 새로 추가된 소스가 있으면 이 서버에도
    기본값(켜짐)으로 반영. 유저가 끈 적 있는(known에는 있지만 enabled엔 없는)
    소스는 건드리지 않음. 새로 켜진 소스 id 집합을 반환(= seed 대상)."""
    known = set(entry.get("known", entry.get("enabled", [])))
    enabled = set(entry.get("enabled", []))
    newly_added = set()
    for s in master_sources:
        if s["id"] not in known:
            enabled.add(s["id"])
            known.add(s["id"])
            newly_added.add(s["id"])
    entry["enabled"] = sorted(enabled)
    entry["known"] = sorted(known)
    return newly_added
