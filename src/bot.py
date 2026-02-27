import re
import logging
import requests
import discord
from discord.ext import commands
from src.config import SECRET_KEY, DISCORD_BOT_TOKEN, DISCORD_REACT_THRESHOLD

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('bot')

# Maps reaction emoji name → (playlist emoji_name, playlist emoji_id)
EMOJI_MAP = {
    "\u2764\ufe0f": ("1radio", "1217470040685936793"),
    "\u2764":       ("1radio", "1217470040685936793"),  # heart without variation selector
    "2radio":       ("2radio", "1217470007378706503"),
    "3radio":       ("3radio", "1217466244350083072"),
}
URL_PATTERN = re.compile(r'https?://\S+')
ADD_SONG_URL = "http://bubble-radio-app:5000/add_song"

# Track submitted (message_id, emoji_name) to avoid duplicate POSTs
submitted = set()

# Mutable threshold — starts from config, changeable via !threshold
react_threshold = DISCORD_REACT_THRESHOLD

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user}")


@bot.command(name="threshold")
@commands.has_permissions(manage_guild=True)
async def set_threshold(ctx, value: int):
    global react_threshold
    if value < 1:
        await ctx.reply("Threshold must be at least 1")
        return
    react_threshold = value
    logger.info(f"Threshold changed to {value} by {ctx.author}")
    await ctx.reply(f"React threshold set to **{value}**")


@set_threshold.error
async def threshold_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("You need Manage Server permission to change the threshold")
    elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.reply(f"Usage: `!threshold <number>` (currently **{react_threshold}**)")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    react_name = payload.emoji.name
    logger.info(f"Reaction received: name={react_name!r} id={payload.emoji.id} message={payload.message_id}")
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
        logger.warning("Message not found")
        return

    # Find the matching reaction and check count
    for reaction in message.reactions:
        if isinstance(reaction.emoji, str):
            match = reaction.emoji in EMOJI_MAP
        else:
            match = reaction.emoji.name == react_name
        logger.info(f"  Checking reaction: {reaction.emoji!r} count={reaction.count} match={match} threshold={react_threshold}")
        if match and reaction.count >= react_threshold:
            break
    else:
        logger.info("No matching reaction met threshold")
        return

    # Extract URL from message text
    urls = URL_PATTERN.findall(message.content)
    logger.info(f"URLs found in message: {urls}")
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
            await message.reply(f"Added to **{playlist_name}**", mention_author=False)
        else:
            error_msg = result.get("message", "Unknown error")
            logger.warning(f"Song submission failed: {error_msg}")
            await message.reply(f"Failed to add: {error_msg}", mention_author=False)

    except requests.RequestException as e:
        logger.error(f"Error posting to add_song: {e}")
        submitted.discard(key)


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
