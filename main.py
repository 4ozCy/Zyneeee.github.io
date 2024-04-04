import discord
from discord.ext import commands
import youtube_dl
import asyncio

# Define the bot and its command prefix
bot = commands.Bot(command_prefix='!')

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or bot.loop
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Queue system
queue = asyncio.Queue()
current = None

async def play_next(ctx):
    global current
    if current:
        current.cleanup()
    current = await queue.get()
    ctx.voice_client.play(current, after=lambda _: bot.loop.create_task(play_next(ctx)))

@bot.command(name='autoplay', help='Enables autoplay of queued songs')
async def autoplay(ctx):
    await play_next(ctx)

@bot.command(name='pitch', help='Changes the pitch of the music')
async def pitch(ctx, *, semitones: float):
    if ctx.voice_client is None or not ctx.voice_client.is_playing():
        await ctx.send("I'm not connected to a voice channel or there is no music playing.")
        return

    # Calculate the new sample rate based on the number of semitones
    semitone_ratio = 2 ** (semitones / 12)
    new_sample_rate = int(ctx.voice_client.source.original.sample_rate * semitone_ratio)

    # Create FFmpeg options with the new sample rate
    ffmpeg_options = {
        'before_options': f'-filter:a "asetrate={new_sample_rate}"',
        'options': '-vn'
    }

    # Stop the current player
    ctx.voice_client.stop()

    # Create a new player with the adjusted pitch and play
    player = await YTDLSource.from_url(ctx.voice_client.source.original.url, loop=bot.loop, stream=True)
    ctx.voice_client.play(discord.FFmpegPCMAudio(player.original.filename, **ffmpeg_options))

    await ctx.send(f'Pitch shifted by {semitones} semitones.')

@bot.command(name='volume', help='Changes the volume of the music')
async def volume(ctx, *, level: float):
    if ctx.voice_client is None:
        await ctx.send("I'm not connected to a voice channel.")
        return

    ctx.voice_client.source.volume = level / 100
    await ctx.send(f'Set the volume to {level}%')

@bot.command(name='play', help='Plays a song')
async def play(ctx, *, url):
    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop)
        await queue.put(player)

    if not ctx.voice_client.is_playing():
        await play_next(ctx)

    await ctx.send(f'Now playing: {player.title}')

@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx):
    await ctx.voice_client.disconnect()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

bot.run('YOUR_BOT_TOKEN')
