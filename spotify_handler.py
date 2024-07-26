import asyncio
from typing import Optional, Union

import discord
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


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


SPOTIFY_CLIENT_ID = "d6e98a42c52c4dff9cb2b09822b46423"
SPOTIFY_CLIENT_SECRET = "59125220c60d4006aa9edf67d2b66d44"
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
spotify_client = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))

    
def format_name(track):
    if 'track' in track:
        track = track['track']
    
    if not track:
        return None
    
    name = track['name']
    artists = ", ".join([artist['name'] for artist in track['artists']])
    return f"{name} - {artists} Lyrics"

def get_track_info(url):
    track_id = url.split("/")[-1].split("?")[0]  # Assumes URL format is "https://open.spotify.com/track/{track_id}"
    data = spotify_client.track(track_id)
    filename = format_name(data)
    return [filename]

def get_playlist_info(url):
    playlist_id = url.split("/")[-1].split("?")[0]  # Assumes URL format is "https://open.spotify.com/playlist/{playlist_id}"
    result = spotify_client.playlist_items(playlist_id, limit=100)
    
    data = result['items']               
    while result['next']:
        result = spotify_client.next(result)
        data.extend(result['items'])

    return [format_name(track) for track in data if format_name(track)]
    

class SpotifySource(discord.PCMVolumeTransformer):
    """
    This class represents an audio source from Spotify, focused on fetching track metadata.
    """
    def __init__(self, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

        

    @classmethod
    async def from_url(cls, url: str, *, loop: Optional[asyncio.AbstractEventLoop] = None) -> Union[str, 'SpotifySource']:
        """
        Creates an instance from a given Spotify track URL.

        :param url: URL of the Spotify track.
        :param loop: Event loop to use for asynchronous operations.
        :return: An instance of SpotifySource.
        """
        loop = loop or asyncio.get_event_loop()
        
        if "playlist" not in url:
            filename = await loop.run_in_executor(None, lambda: get_track_info(url))
            
        elif "playlist" in url:
            filename = await loop.run_in_executor(None, lambda: get_playlist_info(url))        
        
        return filename

