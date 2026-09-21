"""인디알리미 디스코드 봇.

슬래시 커맨드:
  /add-source link:<URL>   - 모니터링할 게시판 링크 추가
  /all-source               - 현재 모니터링 중인 소스 전체 출력
  /all-alim                 - 현재 모집 중인 공고 전체 출력

+ 백그라운드에서 주기적으로 새 공고를 확인해서 Webhook으로 알려줍니다
  (기존 scraper.py와 동일한 로직/저장 파일을 공유).

실행 전에 .env에 DISCORD_BOT_TOKEN이 필요합니다. (README 참고)
"""

import os
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from scraper import check_and_notify
from scraping import fetch_all
from store import load_sources, save_sources

load_dotenv()

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "게임").split(",") if k.strip()]
REQUIRE_KEYWORDS = [
    k.strip() for k in os.environ.get("REQUIRE_KEYWORDS", "게임").split(",") if k.strip()
]
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def slugify(url: str) -> str:
    host = urlparse(url).netloc or url
    return host.replace("www.", "").replace(".", "-")


def format_item_line(item: dict) -> str:
    period = f" ({item['period']})" if item["period"] else ""
    return f"- [{item['title']}]({item['url']}) — {item['source_label']}{period}"


async def send_long_message(interaction: discord.Interaction, text: str, first: bool = True) -> None:
    chunk = text[:1900]
    rest = text[1900:]
    if first:
        await interaction.followup.send(chunk)
    else:
        await interaction.channel.send(chunk)
    if rest:
        await send_long_message(interaction, rest, first=False)


@tree.command(name="add-source", description="새로운 공고 게시판 링크를 모니터링 대상으로 추가합니다.")
@app_commands.describe(link="모니터링할 게시판/목록 페이지 URL")
async def add_source(interaction: discord.Interaction, link: str):
    if not (link.startswith("http://") or link.startswith("https://")):
        await interaction.response.send_message(
            "http:// 또는 https://로 시작하는 URL을 입력해주세요.", ephemeral=True
        )
        return

    sources = load_sources()
    if any(s["url"] == link for s in sources):
        await interaction.response.send_message("이미 등록되어 있는 링크예요.", ephemeral=True)
        return

    source_id = slugify(link)
    label = source_id
    suffix = 2
    existing_ids = {s["id"] for s in sources}
    while source_id in existing_ids:
        source_id = f"{slugify(link)}-{suffix}"
        suffix += 1

    sources.append({"id": source_id, "label": label, "url": link, "parser": "generic"})
    save_sources(sources)
    require_text = ", ".join(REQUIRE_KEYWORDS) if REQUIRE_KEYWORDS else "(없음)"
    await interaction.response.send_message(
        f"추가 완료! `{link}` 를 모니터링 목록에 넣었어요. (id: `{source_id}`)\n"
        f"이 사이트는 구조를 모르니 일반 파서로 동작해요 — 페이지의 링크 텍스트 중 "
        f"**{require_text}**가 반드시 포함된 것만 공고로 잡습니다. 메뉴/배너 링크가 섞여 들어오면 "
        f"알려주세요, 전용 파서를 만들어 드릴게요."
    )


@tree.command(name="all-source", description="현재 모니터링 중인 모든 소스 링크를 보여줍니다.")
async def all_source(interaction: discord.Interaction):
    sources = load_sources()
    if not sources:
        await interaction.response.send_message("등록된 소스가 없어요.")
        return
    lines = [f"- **{s['label']}** ({s['parser']}): {s['url']}" for s in sources]
    await interaction.response.send_message("**모니터링 중인 소스**\n" + "\n".join(lines))


@tree.command(name="all-alim", description="현재 모집 중인 공고를 전부 보여줍니다.")
async def all_alim(interaction: discord.Interaction):
    await interaction.response.defer()
    sources = load_sources()
    items = fetch_all(sources, KEYWORDS, REQUIRE_KEYWORDS)

    if not items:
        await interaction.followup.send("현재 조건(키워드)에 맞는 모집 중인 공고가 없어요.")
        return

    text = f"**현재 모집 중인 공고 ({len(items)}건)**\n" + "\n".join(
        format_item_line(item) for item in items
    )
    await send_long_message(interaction, text)


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def periodic_check():
    sent = check_and_notify()
    if sent:
        print(f"[주기 체크] 새 공고 {sent}건 전송")


@client.event
async def on_guild_join(guild: discord.Guild):
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)


@client.event
async def on_ready():
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    if not periodic_check.is_running():
        periodic_check.start()
    guild_names = ", ".join(g.name for g in client.guilds) or "(가입된 서버 없음)"
    print(f"인디알리미 로그인 완료: {client.user} / 서버: {guild_names}")


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN이 .env에 설정되어 있지 않습니다. README를 참고해 발급해주세요.")
    client.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
