import asyncio
from typing import Optional, Union

import discord
from yt_dlp import YoutubeDL

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
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}


# Update YT-DL options to ignore bug reports
#YoutubeDL.utils.bug_reports_message = lambda: ''

class YTDLSource(discord.PCMVolumeTransformer):
    """
    This class represents an audio source from YouTube, transformed into a format playable by Discord.
    """
    def __init__(self, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

    @classmethod
    async def from_url(cls, url: str, *, loop: Optional[asyncio.AbstractEventLoop] = None, stream: bool = False) -> Union[str, 'YTDLSource']:
        """
        Creates an instance from a given URL.

        :param url: URL of the YT video.
        :param loop: Event loop to use for asynchronous operations.
        :param stream: Indicates if streaming is preferred over downloading.
        :return: An instance of YTDLSource or the filename if stream is False.
        """
        # Extract the video information using YTDL
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: YoutubeDL(YTDL_FORMAT_OPTIONS).extract_info(url, download=not stream))
        
        # Check possible results and select the first entry
        if 'entries' in data:
            data = data['entries'][0]

        # Get the filename and return the source or filename
        filename = data['title'] if stream else YoutubeDL(YTDL_FORMAT_OPTIONS).prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data) if stream else filename