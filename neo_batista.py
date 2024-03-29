import discord
import asyncio
import datetime
from discord.ext import commands
from youtube_handler import YTDLSource
from states import GuildState
import os


class MyBot(commands.Bot):
    async def setup_hook(self):
        # Schedule the background task
        self.loop.create_task(self.check_voice_state())
        pass

    async def check_voice_state(self):
        while True:
            for guild in self.guilds:
                guild_state = get_guild_state(guild)
                if not guild_state.voice_client or not guild_state.voice_client.is_connected():
                    continue
                
                if len(guild_state.voice_client.channel.members) == 1:
                    await guild_state.voice_client.disconnect()
                    guild_state.voice_client = None
                    guild_states.pop(guild, None)
                    
                if (datetime.datetime.now() - guild_state.last_activity).total_seconds() > 300:
                    await guild_state.voice_client.disconnect()
                    guild_state.voice_client = None
                    guild_states.pop(guild, None)
                    
            await asyncio.sleep(60)  # Check every 60 seconds

bot = MyBot(command_prefix='!', intents=discord.Intents.all())

# Dictionary to store the state of each server
guild_states = {}

# Helper function to get the state of a server
def get_guild_state(guild: discord.Guild) -> GuildState:
    if guild not in guild_states:
        guild_states[guild] = GuildState()
    return guild_states[guild]



############################################################################################################
############################################################################################################
# BOT COMMANDS FUNCTIONS
############################################################################################################
############################################################################################################

@bot.command(name='p', help='To play a song')
async def play(ctx: commands.Context, url: str):
    guild_state = get_guild_state(ctx.guild)
    guild_state.update_activity()

    # Connect to the voice channel if not already connected
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if not guild_state.voice_client:
        guild_state.voice_client = await ctx.author.voice.channel.connect()
        
    elif not guild_state.voice_client.is_connected():
        await guild_state.voice_client.disconnect()
        guild_state.voice_client = await ctx.author.voice.channel.connect()
        
    # Add song to queue
    async with ctx.typing():
        filename = await YTDLSource.from_url(url, loop=bot.loop, stream=False)
        guild_state.enqueue_song(filename)  # Assume URL or filename is used here

    # If a song is not already playing, start playback
    if not guild_state.is_playing():
        guild_state.play_next_song(ctx)

    await ctx.send(f'**Song added to queue:** {filename}')


@bot.command(name='queue', help='Shows the current song queue')
async def queue(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild)
    guild_state.update_activity()
    
    if guild_state.get_queue():
        message = "Current queue:\n" + "\n".join([f"{idx + 1}. {song}" for idx, song in enumerate(guild_state.get_queue())])
        await ctx.send(message)
    else:
        await ctx.send("The queue is currently empty.")

@bot.command(name='skip', help='Skips the current song')
async def skip(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild)
    guild_state.update_activity()
    guild_state.skip_song(ctx)
    await ctx.send("Skipped to the next song.")
    
    
@bot.command(name='remove', help='Removes a song from the queue by its position')
async def remove(ctx: commands.Context, position: int):
    guild_state = get_guild_state(ctx.guild)
    guild_state.update_activity()
    guild_state.remove_song(position)  # Adjusting for zero-based indexing
    await ctx.send(f"Removed song number {position} from the queue.")
    
    
@bot.command(name='pause', help='Pauses the song')
async def pause(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild)
    guild_state.update_activity()
    if guild_state.voice_client and guild_state.voice_client.is_playing():
        guild_state.voice_client.pause()
        await ctx.send("Paused the song.")
    else:
        await ctx.send("The bot is not playing anything at the moment.")

@bot.command(name='resume', help='Resumes the song')
async def resume(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild)
    guild_state.update_activity()
    if guild_state.voice_client and guild_state.voice_client.is_paused():
        guild_state.voice_client.resume()
        await ctx.send("Resumed the song.")
    else:
        await ctx.send("The bot was not playing anything before this. Use the play command.")

@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild)
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


@bot.command(name='stop', help='Stops the song')
async def stop(ctx: commands.Context):
    guild_state = get_guild_state(ctx.guild)
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
    DISCORD_TOKEN = os.environ.get('DISCORDTOKEN')
    bot.run(DISCORD_TOKEN)
