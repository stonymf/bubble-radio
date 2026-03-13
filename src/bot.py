import re
import logging
import requests
import discord
from discord.ext import commands, tasks
from src.config import SECRET_KEY, DISCORD_BOT_TOKEN, DISCORD_REACT_THRESHOLD

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('bot')

# Maps reaction emoji name → (playlist emoji_name, playlist emoji_id)
EMOJI_MAP = {
    "1radio":       ("1radio", "1217470040685936793"),
    "2radio":       ("2radio", "1217470007378706503"),
    "3radio":       ("3radio", "1217466244350083072"),
}
URL_PATTERN = re.compile(r'https?://\S+')
APP_BASE_URL = "http://corecore-app:5000"
ADD_SONG_URL = f"{APP_BASE_URL}/add_song"
TEST_DOWNLOADS_URL = f"{APP_BASE_URL}/test_downloads"
DM_USERNAME = "tonymf"

# Track submitted (message_id, emoji_name) to avoid duplicate POSTs
submitted = set()

# Mutable threshold — starts from config, changeable via !threshold
react_threshold = DISCORD_REACT_THRESHOLD

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def _get_setting(key):
    try:
        resp = requests.get(
            f"{APP_BASE_URL}/settings/{key}",
            headers={"Authorization": SECRET_KEY},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("value")
    except requests.RequestException:
        pass
    return None


def _set_setting(key, value):
    try:
        requests.put(
            f"{APP_BASE_URL}/settings/{key}",
            json={"value": str(value)},
            headers={"Authorization": SECRET_KEY},
            timeout=5,
        )
    except requests.RequestException as e:
        logger.error(f"Failed to persist setting {key}: {e}")


@tasks.loop(hours=24)
async def daily_download_test():
    logger.info("Running daily download test...")
    try:
        resp = requests.post(
            TEST_DOWNLOADS_URL,
            headers={"Authorization": SECRET_KEY},
            timeout=300,
        )
        results = resp.json()
    except Exception as e:
        logger.error(f"Daily download test request failed: {e}")
        results = {"all": {"status": "error", "message": str(e)}}

    failures = {k: v for k, v in results.items() if v.get("status") != "ok"}
    if not failures:
        logger.info("Daily download test passed for all platforms")
        return

    # DM the admin
    logger.warning(f"Daily download test failures: {failures}")
    user = discord.utils.find(
        lambda u: u.name == DM_USERNAME, bot.get_all_members()
    )
    if not user:
        logger.error(f"Could not find user {DM_USERNAME} to send DM")
        return

    lines = ["**Download test failures:**"]
    for platform, result in failures.items():
        lines.append(f"- **{platform}**: {result.get('message', 'unknown error')}")
    await user.send("\n".join(lines))


@daily_download_test.before_loop
async def before_daily_test():
    await bot.wait_until_ready()
    import asyncio
    await asyncio.sleep(60)  # wait for app container to be ready


@bot.event
async def on_ready():
    global react_threshold
    saved = _get_setting("react_threshold")
    if saved is not None:
        react_threshold = int(saved)
        logger.info(f"Loaded react_threshold={react_threshold} from DB")
    if not daily_download_test.is_running():
        daily_download_test.start()
    logger.info(f"Bot connected as {bot.user}")


COMMAND_CHANNEL = "dev-chat"


@bot.command(name="threshold")
async def set_threshold(ctx, value: int):
    global react_threshold
    if ctx.channel.name != COMMAND_CHANNEL:
        return
    if value < 1:
        await ctx.reply("Threshold must be at least 1")
        return
    react_threshold = value
    _set_setting("react_threshold", value)
    logger.info(f"Threshold changed to {value} by {ctx.author}")
    await ctx.reply(f"React threshold set to **{value}**")


@set_threshold.error
async def threshold_error(ctx, error):
    if ctx.channel.name != COMMAND_CHANNEL:
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.reply(f"Usage: `!threshold <number>` (currently **{react_threshold}**)")


@bot.command(name="testdownloads")
async def run_test_downloads(ctx):
    if ctx.channel.name != COMMAND_CHANNEL:
        return
    msg = await ctx.reply("Running download tests...")
    try:
        resp = requests.post(
            TEST_DOWNLOADS_URL,
            headers={"Authorization": SECRET_KEY},
            timeout=300,
        )
        results = resp.json()
    except Exception as e:
        await msg.edit(content=f"Test request failed: {e}")
        return

    lines = []
    for platform, result in results.items():
        status = "pass" if result.get("status") == "ok" else "FAIL"
        detail = f" — {result.get('message')}" if status == "FAIL" else ""
        lines.append(f"**{platform}**: {status}{detail}")
    await msg.edit(content="\n".join(lines))


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    react_name = payload.emoji.name
    if react_name not in EMOJI_MAP:
        return

    playlist_name, playlist_emoji_id = EMOJI_MAP[react_name]
    key = (payload.message_id, playlist_name)
    if key in submitted:
        return

    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(payload.channel_id)
        except discord.NotFound:
            return

    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    # Find the matching reaction and check count
    for reaction in message.reactions:
        if isinstance(reaction.emoji, str):
            match = reaction.emoji in EMOJI_MAP
        else:
            match = reaction.emoji.name == react_name
        if match and reaction.count >= react_threshold:
            break
    else:
        return

    # Extract URL from message text
    urls = URL_PATTERN.findall(message.content)
    if not urls:
        return

    url = urls[0]

    # POST to the Flask server
    data = {
        "url": url,
        "user": message.author.display_name,
        "timestamp": message.created_at.isoformat(),
        "channel_id": payload.channel_id,
        "server_id": payload.guild_id,
        "emoji_name": playlist_name,
        "emoji_id": playlist_emoji_id,
    }

    status_msg = await message.reply(f"Downloading for **{playlist_name}**...", mention_author=False)

    try:
        resp = requests.post(
            ADD_SONG_URL,
            json=data,
            headers={"Authorization": SECRET_KEY},
            timeout=120,
        )
        result = resp.json()

        if resp.status_code == 200:
            submitted.add(key)
            logger.info(f"Song submitted: {url} -> {playlist_name}")
            await status_msg.edit(content=f"Added to **{playlist_name}**")
        else:
            error_msg = result.get("message", "Unknown error")
            logger.warning(f"Song submission failed: {error_msg}")
            await status_msg.edit(content=f"Failed to add: {error_msg}")

    except requests.RequestException as e:
        logger.error(f"Error posting to add_song: {e}")
        submitted.discard(key)
        await status_msg.edit(content="Something went wrong adding the song. Try again?")


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
