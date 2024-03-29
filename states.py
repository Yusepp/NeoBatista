import discord
import datetime
import logging
import os

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
    def __init__(self):
        self.voice_client: discord.VoiceClient = None
        self.queue: list = []
        self.current_song: str = None

    def enqueue_song(self, song):
        self.queue.append(song)
    
    def play_next_song(self, error=None):            
        if not self.queue:
            logging.info('The queue is empty, stopping playback.')
            return
        
        self.current_song = self.queue.pop(0)
        logging.info(f"About to play: {self.current_song}")
        
        # Adjust the source path according to your setup
        source = discord.FFmpegPCMAudio(executable="F:\\Descargas\\externals\\ffmpeg.exe", source=self.current_song, **FFMPEG_OPTIONS)
        
        def after_playback(error):
            self.play_next_song(error)
        
        if self.voice_client:
            self.voice_client.play(source, after=after_playback)
        else:
            logging.warning("Voice client is not connected.")

    def skip_song(self, ctx):
        if self.voice_client.is_playing():
            self.voice_client.stop()
            self.play_next_song(ctx)

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
            if song.endswith('.mp3') or song.endswith('.webm'):
                os.remove(song)
           
