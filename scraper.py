"""인디알리미: sources.json에 등록된 모든 사이트를 모니터링해서
새 공고가 올라오면 Discord Webhook으로 알려주는 스크립트.

사용법:
    python scraper.py

설정은 .env 파일(DISCORD_WEBHOOK_URL, KEYWORDS)에서 읽습니다.
슬래시 커맨드(/add-source 등)로 사용하려면 bot.py를 실행하세요.
"""

import os

import requests
from dotenv import load_dotenv

from scraping import fetch_all
from store import SEEN_FILE, load_seen, load_sources, save_seen

load_dotenv()

KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "게임").split(",") if k.strip()]
REQUIRE_KEYWORDS = [
    k.strip() for k in os.environ.get("REQUIRE_KEYWORDS", "게임").split(",") if k.strip()
]
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def send_to_discord(item: dict) -> None:
    if not WEBHOOK_URL:
        print(f"[DRY RUN, 웹훅 미설정] {item['title']} -> {item['url']}")
        return

    embed = {
        "title": item["title"],
        "url": item["url"],
        "color": 0x5865F2,
        "fields": [
            {"name": "출처", "value": item["source_label"], "inline": True},
            {"name": "구분", "value": item["category"] or "-", "inline": True},
            {"name": "접수기간", "value": item["period"] or "-", "inline": False},
        ],
        "footer": {"text": f"인디알리미 · 키워드: {item['keyword']}"},
    }
    resp = requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
    resp.raise_for_status()


def check_and_notify() -> int:
    """sources.json의 모든 소스를 확인하고, 새 공고면 전송. 새로 보낸 건수를 반환."""
    first_run = not SEEN_FILE.exists()
    seen = load_seen()
    new_seen = set(seen)
    sent = 0

    for item in fetch_all(load_sources(), KEYWORDS, REQUIRE_KEYWORDS):
        if item["id"] in new_seen:
            continue
        new_seen.add(item["id"])
        if not first_run:
            send_to_discord(item)
            sent += 1

    save_seen(new_seen)
    return sent


def main() -> None:
    first_run = not SEEN_FILE.exists()
    sent = check_and_notify()
    if first_run:
        print("초기 세팅 완료: 기존 공고를 확인된 것으로 저장했습니다. 다음 실행부터 새 글만 알려드려요.")
    else:
        print(f"완료: 새 공고 {sent}건 전송 (키워드: {', '.join(KEYWORDS)})")


if __name__ == "__main__":
    main()
