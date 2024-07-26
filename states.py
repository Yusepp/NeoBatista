import discord
import datetime
import logging
import os
from yt_dlp import YoutubeDL
import asyncio

# Constants for configuration
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # Avoids issues with IPv6 addresses
}
FFMPEG_OPTIONS = {'options': '-vn'}


# Update YT-DL options to ignore bug reports
#YoutubeDL.utils.bug_reports_message = lambda: ''

class GuildState:
    def __init__(self, event_loop, ctx):
        self.voice_client: discord.VoiceClient = None
        self.queue: list = []
        self.current_song: str = None
        self.event_loop = event_loop  # Store the event loop
        self.ctx = ctx

    def enqueue_song(self, song):
        self.queue.append(song)
    
    async def play_next_song(self, error=None, loop=None):
        if not self.queue:
            logging.info('The queue is empty, stopping playback.')
            return
        
        self.current_song = self.queue.pop(0)
        try:
            self.current_song = await self.event_loop.run_in_executor(None, lambda: YoutubeDL(YTDL_FORMAT_OPTIONS).extract_info(self.current_song, download=True))
            if 'entries' in self.current_song:
                self.current_song = self.current_song['entries'][0]
            self.current_song = YoutubeDL(YTDL_FORMAT_OPTIONS).prepare_filename(self.current_song)
            song = self.current_song.replace('.webm', '').replace(".mp3", "").replace(".m4a", "")
            await self.ctx.send(f"Playing **{song}**")
            
            source = discord.FFmpegPCMAudio(source=self.current_song, **FFMPEG_OPTIONS)
            
            async def after_playback(error):
                self.update_activity()
                await self.play_next_song(error, loop=self.event_loop)
            
            if self.voice_client:
                self.voice_client.play(source, after=lambda e: self.event_loop.create_task(after_playback(e)))
            else:
                logging.warning("Voice client is not connected.")
        except Exception as e:
            logging.error(f"Error playing next song: {e}")

    async def skip_song(self, ctx, loop=None):
        if self.voice_client.is_playing():
            self.voice_client.stop()
        await self.play_next_song(loop=self.event_loop)

    def clear_queue(self):
        self.queue = []

    def remove_song(self, index: int):
        if index <= len(self.queue):
            del self.queue[index-1]

    def get_queue(self):
        return self.queue
    
    
    def is_playing(self):
        return self.voice_client and self.voice_client.is_playing()
    
    
    def update_activity(self):
        self.last_activity = datetime.datetime.now()
        
    def clear_song_files(self):
        for song in os.listdir('.'):
            if song.endswith('.mp3') or song.endswith('.webm') or song.endswith('.m4a'):
                os.remove(song)
           
