import re
import logging
import requests
import discord
from src.config import SECRET_KEY, DISCORD_BOT_TOKEN, DISCORD_REACT_THRESHOLD

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('bot')

RADIO_EMOJIS = {"1radio", "2radio", "3radio"}
URL_PATTERN = re.compile(r'https?://\S+')
ADD_SONG_URL = "http://bubble-radio-app:5000/add_song"

# Track submitted (message_id, emoji_name) to avoid duplicate POSTs
submitted = set()

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user}")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    emoji_name = payload.emoji.name
    if emoji_name not in RADIO_EMOJIS:
        return

    key = (payload.message_id, emoji_name)
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
        if isinstance(reaction.emoji, discord.PartialEmoji) or isinstance(reaction.emoji, discord.Emoji):
            if reaction.emoji.name == emoji_name and reaction.count >= DISCORD_REACT_THRESHOLD:
                break
        elif isinstance(reaction.emoji, str) and reaction.emoji == emoji_name:
            if reaction.count >= DISCORD_REACT_THRESHOLD:
                break
    else:
        return

    # Extract URL from message text
    urls = URL_PATTERN.findall(message.content)
    if not urls:
        return

    url = urls[0]
    submitted.add(key)

    # POST to the Flask server
    data = {
        "url": url,
        "user": message.author.display_name,
        "timestamp": message.created_at.isoformat(),
        "channel_id": payload.channel_id,
        "server_id": payload.guild_id,
        "emoji_name": emoji_name,
        "emoji_id": str(payload.emoji.id) if payload.emoji.id else emoji_name,
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
            logger.info(f"Song submitted: {url} -> {emoji_name}")
            await message.reply(f"Added to **{emoji_name}**", mention_author=False)
        else:
            error_msg = result.get("message", "Unknown error")
            logger.warning(f"Song submission failed: {error_msg}")
            await message.reply(f"Failed to add: {error_msg}", mention_author=False)

    except requests.RequestException as e:
        logger.error(f"Error posting to add_song: {e}")
        submitted.discard(key)


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
