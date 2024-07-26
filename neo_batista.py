import discord
import asyncio
import datetime
from discord.ext import commands
from youtube_handler import YTDLSource
from spotify_handler import SpotifySource
from states import GuildState
import os
from random import sample

class MyBot(commands.Bot):
    async def setup_hook(self):
        # Schedule the background task
        self.loop.create_task(self.check_voice_state())
        self.event_loop = asyncio.get_running_loop()  # Store the running event loop

    async def check_voice_state(self):
        while True:
            for guild in self.guilds:
                guild_state = get_guild_state(guild)
                if not guild_state or not guild_state.voice_client or not guild_state.voice_client.is_connected():
                    continue
                
                if len(guild_state.voice_client.channel.members) == 1 and not guild_state.is_playing():
                    await guild_state.voice_client.disconnect()
                    guild_state.voice_client = None
                    guild_state.clear_song_files()
                    guild_states.pop(guild, None)
                    
                if (datetime.datetime.now() - guild_state.last_activity).total_seconds() > 300*1.5 and not guild_state.is_playing():
                    await guild_state.voice_client.disconnect()
                    guild_state.voice_client = None
                    guild_state.clear_song_files()
                    guild_states.pop(guild, None)
                    
            await asyncio.sleep(60)  # Check every 60 seconds

bot = MyBot(command_prefix='!', intents=discord.Intents.all())

# Dictionary to store the state of each server
guild_states = {}

# Helper function to get the state of a server
def get_guild_state(guild: discord.Guild, ctx = None) -> GuildState:
    if guild not in guild_states:
        if ctx:
            guild_states[guild] = GuildState(bot.event_loop, ctx)
        else:
            return None
    return guild_states[guild]



############################################################################################################
############################################################################################################
# BOT COMMANDS FUNCTIONS
############################################################################################################
############################################################################################################

@bot.command(name='p', help='To play a song')
async def play(ctx: commands.Context, url: str):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()

    # Connect to the voice channel if not already connected
    if not ctx.author.voice:
        await ctx.send("LA **NEO**BOMBA BATISTA DICE QUE NO ESTAS CONECTADO A NINGUN CANAL DE VOZ!.")
        return
    
    if not guild_state.voice_client:
        guild_state.voice_client = await ctx.author.voice.channel.connect()
        await ctx.send("LA **NEO**BOMBA BATISTA YA ESTA AQUI!")

        
    elif not guild_state.voice_client.is_connected():
        await guild_state.voice_client.disconnect()
        guild_state.voice_client = await ctx.author.voice.channel.connect()
        await ctx.send("LA **NEO**BOMBA BATISTA YA ESTA AQUI!")

        
    # Add song to queue
    async with ctx.typing():
        if "youtube" in url or "youtu.be" in url:
            filename = await YTDLSource.from_url(url, loop=bot.loop, stream=False)
        elif "spotify" in url:
            filename = await SpotifySource.from_url(url, loop=bot.loop)
        
        else:
            filename = [url]
        
        for song in filename:
            guild_state.enqueue_song(song)

    # If a song is not already playing, start playback
    if not guild_state.is_playing():
        await guild_state.play_next_song(loop=bot.loop)

    if len(filename) == 1:
        await ctx.send(f'**Song added to queue:** {filename[0]}')
    else:
        await ctx.send(f'**Playlist added to queue:** {len(filename)} songs')


@bot.command(name='queue', help='Shows the current song queue')
async def queue(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    
    queue_list = guild_state.get_queue()
    if not queue_list:
        await ctx.send("The queue is currently empty.")
        return

    # Create a message for each chunk of the queue list
    chunk_size = 2000  # Discord message character limit is 4000, so we use 2000 to be safe
    message_chunks = []
    current_chunk = "Current queue:\n"
    
    for idx, song in enumerate(queue_list):
        song_line = f"{idx + 1}. {song}\n"
        if len(current_chunk) + len(song_line) > chunk_size:
            message_chunks.append(current_chunk)
            current_chunk = song_line
        else:
            current_chunk += song_line
    
    if current_chunk:
        message_chunks.append(current_chunk)
    
    # Send each chunk as a separate message
    for chunk in message_chunks:
        await ctx.send(chunk)

@bot.command(name='skip', help='Skips the current song')
async def skip(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    await guild_state.skip_song(ctx, loop=bot.loop)
    await ctx.send("Skipped to the next song.")
    
    
@bot.command(name='remove', help='Removes a song from the queue by its position')
async def remove(ctx: commands.Context, position: int):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    guild_state.remove_song(position)  # Adjusting for zero-based indexing
    await ctx.send(f"Removed song number {position} from the queue.")
    
    
@bot.command(name='pause', help='Pauses the song')
async def pause(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    if guild_state.voice_client and guild_state.voice_client.is_playing():
        guild_state.voice_client.pause()
        await ctx.send("Paused the song.")
    else:
        await ctx.send("The bot is not playing anything at the moment.")

@bot.command(name='resume', help='Resumes the song')
async def resume(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    if guild_state.voice_client and guild_state.voice_client.is_paused():
        guild_state.voice_client.resume()
        await ctx.send("Resumed the song.")
    else:
        await ctx.send("The bot was not playing anything before this. Use the play command.")

@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    if guild_state.voice_client and guild_state.voice_client.is_connected():
        await guild_state.voice_client.disconnect()
        # Clean up the guild state
        guild_state.voice_client = None
        guild_state.clear_queue()
        guild_states.pop(ctx.guild, None)  # Remove guild state after leaving
        await ctx.send("I've left the voice channel.")
        guild_state.clear_song_files()
    else:
        await ctx.send("I'm not in a voice channel.")

@bot.command(name='shuffle', help="To suffle current queue.")
async def shuffle(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    q = guild_state.get_queue()
    q_size =  len(q)

    if guild_state.voice_client and q_size >= 2:
        guild_state.queue = sample(q, q_size)
        await ctx.send("Current queue has been shuffled succesfully!")
    else:
        await ctx.send("Failed to shuffle the current queue!")

@bot.command(name='stop', help='Stops the song')
async def stop(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild, ctx)
    guild_state.update_activity()
    if guild_state.voice_client and guild_state.voice_client.is_playing():
        guild_state.voice_client.stop()
        # Optionally, clear the queue to stop further playback
        guild_state.clear_queue()
        await ctx.send("Stopped the song and cleared the queue.")
        guild_state.clear_song_files()
    else:
        await ctx.send("The bot is not playing anything at the moment.")




# Run the bot instance
if __name__ == "__main__":
    # Constants for configuration
    DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
    bot.run(DISCORD_TOKEN)
