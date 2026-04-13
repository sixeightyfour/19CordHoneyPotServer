import os
import aiohttp
import discord
from discord.ext import tasks
from discord import app_commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

CHECK_URL = "https://scp-wiki.wikidot.com/"
CHECK_INTERVAL_SECONDS = 60
FAIL_THRESHOLD = 10

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

http_session: aiohttp.ClientSession | None = None

consecutive_failures = 0
outage_announced = False

last_status = "Unknown"
last_detail = "No checks yet"


async def get_http_session() -> aiohttp.ClientSession:
    global http_session
    if http_session is None or http_session.closed:
        timeout = aiohttp.ClientTimeout(total=10)
        http_session = aiohttp.ClientSession(timeout=timeout)
    return http_session


async def check_site() -> tuple[bool, str]:

    session = await get_http_session()

    try:
        async with session.get(
            CHECK_URL,
            headers={"User-Agent": "scp-status-bot/1.0"}
        ) as resp:
            if 200 <= resp.status < 400:
                return True, f"HTTP {resp.status}"
            return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def build_status_embed() -> discord.Embed:
    embed = discord.Embed(title="Wiki Status")
    embed.add_field(name="State", value=last_status, inline=False)
    embed.add_field(name="Last Result", value=last_detail, inline=False)
    embed.add_field(
        name="Failure Streak",
        value=f"{consecutive_failures}/{FAIL_THRESHOLD}",
        inline=False
    )
    return embed


def build_outage_embed(detail: str) -> discord.Embed:
    embed = discord.Embed(title="IT'S SO OVER")
    embed.description = (
        f"The site failed {consecutive_failures} checks in a row."
    )
    embed.add_field(name="Latest Result", value=detail, inline=False)
    embed.set_image(url="attachment://image.png")
    
    return embed


def build_recovery_embed(detail: str) -> discord.Embed:
    embed = discord.Embed(title="WE ARE SO BACK")
    embed.description = "The site appears to be back up!"
    embed.add_field(name="Latest Result", value=detail, inline=False)
    return embed


@tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
async def monitor_site():
    global consecutive_failures, outage_announced, last_status, last_detail

    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found. Check CHANNEL_ID and bot permissions.")
        return

    is_healthy, detail = await check_site()
    last_detail = detail

    if is_healthy:
        last_status = "UP"

        if outage_announced:
            await channel.send(embed=build_recovery_embed(detail))

        consecutive_failures = 0
        outage_announced = False
        print(f"[OK] {detail}")
        return

    last_status = "DOWN/DEGRADED"
    consecutive_failures += 1
    print(f"[FAIL {consecutive_failures}/{FAIL_THRESHOLD}] {detail}")

    if consecutive_failures >= FAIL_THRESHOLD and not outage_announced:
        file = discord.File("image.png", filename="image.png")
        embed = build_outage_embed(detail)

        await channel.send(embed=embed, file=file)
        outage_announced = True


@monitor_site.before_loop
async def before_monitor_site():
    await client.wait_until_ready()


@client.event
async def on_ready():
    print(f"Logged in as {client.user} ({client.user.id})")

    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    if not monitor_site.is_running():
        monitor_site.start()


@tree.command(name="status", description="Show the result of the last ping.")
async def status_command(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_status_embed())


@tree.command(name="forcecheck", description="Run a live check of the wiki's status right now.")
async def forcecheck_command(interaction: discord.Interaction):
    global consecutive_failures, outage_announced, last_status, last_detail

    await interaction.response.defer(thinking=True)

    is_healthy, detail = await check_site()
    last_detail = detail

    if is_healthy:
        last_status = "UP"
        consecutive_failures = 0
        outage_announced = False
    else:
        last_status = "DOWN/DEGRADED"
        consecutive_failures += 1

    embed = discord.Embed(title="SCP Wiki Live Check")
    embed.add_field(name="State", value=last_status, inline=False)
    embed.add_field(name="Result", value=last_detail, inline=False)
    embed.add_field(
        name="Failure Streak",
        value=f"{consecutive_failures}/{FAIL_THRESHOLD}",
        inline=False
    )

    await interaction.followup.send(embed=embed)


@client.event
async def on_disconnect():
    print("Bot disconnected.")


async def close_http_session():
    global http_session
    if http_session and not http_session.closed:
        await http_session.close()


async def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set.")
    if CHANNEL_ID == 0:
        raise RuntimeError("CHANNEL_ID is not set or invalid.")

    try:
        await client.start(DISCORD_TOKEN)
    finally:
        await close_http_session()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
