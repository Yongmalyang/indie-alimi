"""인디알리미 디스코드 봇 — 여러 서버가 봇 하나를 공유하는 구조.

서버 관리자 커맨드:
  /sources                  - 이 서버에서 켜져있는/꺼져있는 소스 목록
  /source-on name:<소스>     - 특정 소스 알림 켜기
  /source-off name:<소스>    - 특정 소스 알림 끄기
  /set-channel               - 이 채널을 알림 채널로 지정
  /all-alim                  - 이 서버에 켜진 소스 기준으로 현재 모집 중인 공고 전부 출력

마스터 소스 목록(sources.json)은 개발자가 직접 큐레이션합니다(코드로 추가) — 일반 유저는
/source-on, /source-off로 "받을지 말지"만 고를 수 있어요. (디스코드 커맨드로 소스를 추가하는
기능은 없음)

실행 전에 .env에 DISCORD_BOT_TOKEN이 필요합니다. (README 참고)
"""

import os

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from scraping import fetch_all
from store import (
    get_guild_entry,
    load_guild_state,
    load_sources,
    save_guild_state,
    sync_guild_with_master,
)

load_dotenv()

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "게임").split(",") if k.strip()]
REQUIRE_KEYWORDS = [
    k.strip() for k in os.environ.get("REQUIRE_KEYWORDS", "게임").split(",") if k.strip()
]
EXCLUDE_KEYWORDS = [
    k.strip() for k in os.environ.get("EXCLUDE_KEYWORDS", "").split(",") if k.strip()
]
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def format_item_line(item: dict) -> str:
    period = f" ({item['period']})" if item["period"] else ""
    return f"- [{item['title']}]({item['url']}) — {item['source_label']}{period}"


def build_embed(item: dict) -> discord.Embed:
    embed = discord.Embed(title=item["title"], url=item["url"], color=0x5865F2)
    embed.add_field(name="출처", value=item["source_label"], inline=True)
    if item["category"]:
        embed.add_field(name="구분", value=item["category"], inline=True)
    if item["period"]:
        embed.add_field(name="접수기간", value=item["period"], inline=False)
    elif item["posted"]:
        embed.add_field(name="등록일", value=item["posted"], inline=True)
    embed.set_footer(text=f"인디알리미 · 키워드: {item['keyword']}")
    return embed


async def send_long_message(interaction: discord.Interaction, text: str, first: bool = True) -> None:
    chunk = text[:1900]
    rest = text[1900:]
    if first:
        await interaction.followup.send(chunk)
    else:
        await interaction.channel.send(chunk)
    if rest:
        await send_long_message(interaction, rest, first=False)


def is_admin(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild) and interaction.user.guild_permissions.manage_guild


def seed_sources(entry: dict, master_sources: list, source_ids: set) -> None:
    """새로 켠 소스의 '지금 있는 글'은 알림 없이 이미 본 것으로만 표시 (스팸 방지)."""
    sources = [s for s in master_sources if s["id"] in source_ids]
    if not sources:
        return
    items = fetch_all(sources, KEYWORDS, REQUIRE_KEYWORDS, EXCLUDE_KEYWORDS)
    seen = set(entry.get("seen", []))
    seen.update(item["id"] for item in items)
    entry["seen"] = sorted(seen)


async def _enabled_choices(interaction: discord.Interaction, current: str):
    master_sources = load_sources()
    guild_state = load_guild_state()
    entry = guild_state.get(str(interaction.guild_id)) or {"enabled": [s["id"] for s in master_sources]}
    enabled = set(entry.get("enabled", []))
    matches = [s for s in master_sources if s["id"] in enabled and current.lower() in s["label"].lower()]
    return [app_commands.Choice(name=s["label"], value=s["id"]) for s in matches[:25]]


async def _disabled_choices(interaction: discord.Interaction, current: str):
    master_sources = load_sources()
    guild_state = load_guild_state()
    entry = guild_state.get(str(interaction.guild_id)) or {"enabled": [s["id"] for s in master_sources]}
    enabled = set(entry.get("enabled", []))
    matches = [s for s in master_sources if s["id"] not in enabled and current.lower() in s["label"].lower()]
    return [app_commands.Choice(name=s["label"], value=s["id"]) for s in matches[:25]]


@tree.command(name="sources", description="이 서버에서 켜져있는/꺼져있는 소스 목록을 보여줍니다.")
async def sources_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("서버 안에서만 쓸 수 있어요.", ephemeral=True)
        return
    master_sources = load_sources()
    guild_state = load_guild_state()
    entry = get_guild_entry(guild_state, str(interaction.guild_id), master_sources)
    save_guild_state(guild_state)

    enabled = set(entry["enabled"])
    lines = [
        f"{'✅' if s['id'] in enabled else '⬜'} **{s['label']}** (`{s['id']}`)" for s in master_sources
    ]
    note = ""
    if not entry.get("channel_id"):
        note = "\n\n⚠️ 알림 채널이 아직 설정 안 됐어요. `/set-channel`을 이 채널에서 실행해주세요."
    await interaction.response.send_message("**소스 목록**\n" + "\n".join(lines) + note)


@tree.command(name="source-off", description="[관리자] 특정 소스의 알림을 끕니다.")
@app_commands.describe(name="끌 소스")
@app_commands.autocomplete(name=_enabled_choices)
async def source_off(interaction: discord.Interaction, name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("서버 관리 권한이 있는 사람만 설정할 수 있어요.", ephemeral=True)
        return
    master_sources = load_sources()
    guild_state = load_guild_state()
    entry = get_guild_entry(guild_state, str(interaction.guild_id), master_sources)
    if name in entry["enabled"]:
        entry["enabled"].remove(name)
        save_guild_state(guild_state)
    label = next((s["label"] for s in master_sources if s["id"] == name), name)
    await interaction.response.send_message(f"🔕 **{label}** 알림을 껐어요.")


@tree.command(name="source-on", description="[관리자] 특정 소스의 알림을 켭니다.")
@app_commands.describe(name="켤 소스")
@app_commands.autocomplete(name=_disabled_choices)
async def source_on(interaction: discord.Interaction, name: str):
    if not is_admin(interaction):
        await interaction.response.send_message("서버 관리 권한이 있는 사람만 설정할 수 있어요.", ephemeral=True)
        return
    await interaction.response.defer()
    master_sources = load_sources()
    guild_state = load_guild_state()
    entry = get_guild_entry(guild_state, str(interaction.guild_id), master_sources)
    if name not in entry["enabled"]:
        entry["enabled"].append(name)
        seed_sources(entry, master_sources, {name})
        save_guild_state(guild_state)
    label = next((s["label"] for s in master_sources if s["id"] == name), name)
    await interaction.followup.send(f"🔔 **{label}** 알림을 켰어요. (지금 있는 글은 건너뛰고 새 글부터 알려드려요)")


@tree.command(name="set-channel", description="[관리자] 이 채널을 인디알리미 알림 채널로 지정합니다.")
async def set_channel(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("서버 관리 권한이 있는 사람만 설정할 수 있어요.", ephemeral=True)
        return
    await interaction.response.defer()
    master_sources = load_sources()
    guild_state = load_guild_state()
    entry = get_guild_entry(guild_state, str(interaction.guild_id), master_sources)
    first_setup = entry.get("channel_id") is None
    entry["channel_id"] = interaction.channel_id
    if first_setup:
        seed_sources(entry, master_sources, set(entry["enabled"]))
    save_guild_state(guild_state)

    msg = "✅ 이 채널을 알림 채널로 지정했어요."
    if first_setup:
        msg += " 지금 있는 공고는 건너뛰고, 다음 새 글부터 알려드릴게요."
    await interaction.followup.send(msg)


@tree.command(name="all-alim", description="이 서버에 켜져있는 소스에서 현재 모집 중인 공고를 전부 보여줍니다.")
async def all_alim(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("서버 안에서만 쓸 수 있어요.", ephemeral=True)
        return
    await interaction.response.defer()
    master_sources = load_sources()
    guild_state = load_guild_state()
    entry = get_guild_entry(guild_state, str(interaction.guild_id), master_sources)
    save_guild_state(guild_state)

    sources = [s for s in master_sources if s["id"] in set(entry["enabled"])]
    if not sources:
        await interaction.followup.send("켜져있는 소스가 없어요. `/sources`, `/source-on`으로 켜주세요.")
        return

    items = fetch_all(sources, KEYWORDS, REQUIRE_KEYWORDS, EXCLUDE_KEYWORDS)
    if not items:
        await interaction.followup.send("현재 켜져있는 소스 기준으로 모집 중인 공고가 없어요.")
        return

    text = f"**현재 모집 중인 공고 ({len(items)}건)**\n" + "\n".join(
        format_item_line(item) for item in items
    )
    await send_long_message(interaction, text)


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def periodic_check():
    master_sources = load_sources()
    guild_state = load_guild_state()
    any_change = False

    for guild in client.guilds:
        gid = str(guild.id)
        entry = get_guild_entry(guild_state, gid, master_sources)

        newly_added = sync_guild_with_master(entry, master_sources)
        if newly_added:
            seed_sources(entry, master_sources, newly_added)
            any_change = True

        channel_id = entry.get("channel_id")
        if not channel_id:
            continue
        channel = client.get_channel(channel_id)
        if channel is None:
            continue

        sources = [s for s in master_sources if s["id"] in set(entry["enabled"])]
        if not sources:
            continue

        items = fetch_all(sources, KEYWORDS, REQUIRE_KEYWORDS, EXCLUDE_KEYWORDS)
        seen = set(entry.get("seen", []))
        new_items = [item for item in items if item["id"] not in seen]
        if not new_items:
            continue

        for item in new_items:
            await channel.send(embed=build_embed(item))
            seen.add(item["id"])
        entry["seen"] = sorted(seen)
        any_change = True
        print(f"[{guild.name}] 새 공고 {len(new_items)}건 전송")

    if any_change:
        save_guild_state(guild_state)


@client.event
async def on_guild_join(guild: discord.Guild):
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)
    master_sources = load_sources()
    guild_state = load_guild_state()
    get_guild_entry(guild_state, str(guild.id), master_sources)
    save_guild_state(guild_state)


@client.event
async def on_ready():
    master_sources = load_sources()
    guild_state = load_guild_state()
    changed = False
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        entry = get_guild_entry(guild_state, str(guild.id), master_sources)
        newly_added = sync_guild_with_master(entry, master_sources)
        if newly_added:
            seed_sources(entry, master_sources, newly_added)
        changed = True
    if changed:
        save_guild_state(guild_state)

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
