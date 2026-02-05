import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import asyncio

with open("config.json") as f:
    config = json.load(f)

TOKEN = config["TOKEN"]
DEFAULT_CHANNEL = config["DEFAULT_COUNT_CHANNEL"]
RESET_ON_INCORRECT = config.get("RESET_ON_INCORRECT", True)
HIDE_FROM_LEADERBOARD = config.get("HIDE_FROM_LEADERBOARD", False)
SKIP_LEADERBOARD = set(config.get("SKIP_LEADERBOARD_FOR_SERVERS", []))

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Global storage (in-memory)
server_data = {}  # {guild_id: {"count": int, "last_user": int, "hide_from_leaderboard": bool}}

webhook_cache = {}

async def get_webhook(channel):
    if channel.id in webhook_cache:
        return webhook_cache[channel.id]
    hooks = await channel.webhooks()
    for hook in hooks:
        if hook.name == "Counter Bot":
            webhook_cache[channel.id] = hook
            return hook
    hook = await channel.create_webhook(name="Counter Bot")
    webhook_cache[channel.id] = hook
    return hook

def get_server_data(guild_id):
    if guild_id not in server_data:
        server_data[guild_id] = {
            "count": 0,
            "last_user": None,
            "hide_from_leaderboard": HIDE_FROM_LEADERBOARD,
            "count_channel": DEFAULT_CHANNEL,
            "reset_on_incorrect": RESET_ON_INCORRECT
        }
    return server_data[guild_id]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = message.guild.id
    data = get_server_data(guild_id)
    count_channel_name = data["count_channel"]

    if message.channel.name != count_channel_name:
        return

    if not message.content.isdigit():
        await message.delete()
        return

    number = int(message.content)

    # Same user twice
    if message.author.id == data["last_user"]:
        await message.delete()
        return

    if number == data["count"] + 1:
        data["count"] = number
        data["last_user"] = message.author.id
        webhook = await get_webhook(message.channel)
        await message.delete()
        await webhook.send(
            content=str(number),
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url
        )
    else:
        # Wrong number → delete message and optionally reset
        await message.delete()
        if data["reset_on_incorrect"]:
            data["count"] = 0
            data["last_user"] = None

# --------------------------
# Slash Commands
# --------------------------

@tree.command(name="disable", description="Disable counting and delete all counting data")
async def disable(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    server_data.pop(guild_id, None)
    await interaction.response.send_message("✅ Counting disabled and data cleared.", ephemeral=True)

@tree.command(name="howitworks", description="Explain how the counting bot works")
async def howitworks(interaction: discord.Interaction):
    msg = (
        "📜 **How It Works**:\n"
        "- Count upward messages in order.\n"
        "- Wrong numbers are deleted.\n"
        "- Correct numbers are reposted via webhook.\n"
        "- Same user cannot count twice in a row.\n"
        "- Optional reset on incorrect count.\n"
        "- Leaderboard tracks counts globally."
    )
    await interaction.response.send_message(msg, ephemeral=True)

@tree.command(name="info", description="Bot info")
async def info(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🔢 **Counter Bot**\nMade by Tyler and Chloe\nCurrent guild: {interaction.guild.name}",
        ephemeral=True
    )

@tree.command(name="leaderboard", description="View the global counting leaderboard")
async def leaderboard(interaction: discord.Interaction):
    lines = []
    for guild_id, data in server_data.items():
        if data.get("hide_from_leaderboard"):
            continue
        guild_name = bot.get_guild(guild_id).name if bot.get_guild(guild_id) else str(guild_id)
        lines.append(f"{guild_name}: {data['count']}")
    if not lines:
        lines = ["No servers currently tracked."]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@tree.command(name="leaderboard-visibility", description="Toggle whether this server is hidden from leaderboard")
async def leaderboard_visibility(interaction: discord.Interaction):
    data = get_server_data(interaction.guild.id)
    data["hide_from_leaderboard"] = not data.get("hide_from_leaderboard", False)
    await interaction.response.send_message(f"Hide from leaderboard: {data['hide_from_leaderboard']}", ephemeral=True)

@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)

@tree.command(name="setup", description="Setup counting channel and options")
@app_commands.describe(
    channel="Channel to use for counting",
    reset_on_incorrect="Reset counter if someone counts wrong?",
    hide_from_leaderboard="Hide this server from leaderboard?"
)
async def setup(interaction: discord.Interaction, channel: discord.TextChannel = None, reset_on_incorrect: bool = True, hide_from_leaderboard: bool = False):
    data = get_server_data(interaction.guild.id)
    data["count_channel"] = channel.name if channel else DEFAULT_CHANNEL
    data["reset_on_incorrect"] = reset_on_incorrect
    data["hide_from_leaderboard"] = hide_from_leaderboard
    await interaction.response.send_message(f"✅ Setup complete for channel #{data['count_channel']}", ephemeral=True)

# --------------------------

bot.run(TOKEN)
