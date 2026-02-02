"""
Downloader module for Instagram and TikTok with progress tracking
"""

import os
import asyncio
import logging
import time
import subprocess
from typing import Dict, List, Callable, Optional
from dotenv import load_dotenv

import yt_dlp

load_dotenv()
logger = logging.getLogger(__name__)


class ProgressTracker:
    """Track download progress for yt-dlp"""
    
    def __init__(self, callback: Callable[[str], None], loop: asyncio.AbstractEventLoop):
        self.callback = callback
        self.loop = loop
        self.update_interval = 2.0
    
    def _create_progress_bar(self, percent: float, width: int = 20) -> str:
        filled = int(width * percent / 100)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}] {percent:.1f}%"
    
    def _format_size(self, bytes_val: int) -> str:
        if bytes_val is None:
            return "Unknown"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f}TB"
    
    def progress_hook(self, d: dict):
        """Hook called by yt-dlp during download"""
        current_time = time.time()
        
        if d['status'] == 'downloading':
            if hasattr(self, '_last_update_time'):
                if current_time - self._last_update_time < self.update_interval:
                    return
            self._last_update_time = current_time
            
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            
            if total > 0:
                percent = (downloaded / total) * 100
                bar = self._create_progress_bar(percent)
                speed = d.get('speed', 0)
                speed_str = f"{self._format_size(speed)}/s" if speed else "Unknown"
                
                message = (
                    f"⏳ Downloading...\n"
                    f"{bar}\n"
                    f"📊 {self._format_size(downloaded)} / {self._format_size(total)}\n"
                    f"🚀 {speed_str}"
                )
            else:
                message = f"⏳ Downloading... {self._format_size(downloaded)} downloaded"
            
            try:
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(self.callback, message)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
        
        elif d['status'] == 'finished':
            try:
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(self.callback, "✅ Download complete! Processing...")
            except Exception as e:
                logger.error(f"Progress callback error: {e}")


class ContentDownloader:
    """Handle content downloading from Instagram, TikTok, and YouTube"""
    
    def __init__(self):
        self.instagram_user = os.getenv("INSTAGRAM_USERNAME")
        self.instagram_pass = os.getenv("INSTAGRAM_PASSWORD")
        self.youtube_enabled = os.getenv("YOUTUBE_SUPPORT", "false").lower() == "true"
        
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'retries': 3,
            'fragment_retries': 3,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'force_ipv4': True,
        }
    
    async def download(self, url: str, download_path: str, 
                      progress_callback: Optional[Callable[[str], None]] = None,
                      format_type: str = "video", quality: str = "best") -> Dict:
        """Download content from URL with progress tracking"""
        try:
            os.makedirs(download_path, exist_ok=True)
            
            if not self.is_supported_url(url):
                return {"success": False, "error": "Unsupported URL"}
            
            return await self._download_with_ytdlp(url, download_path, progress_callback, quality)
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _download_with_ytdlp(self, url: str, download_path: str, 
                                   progress_callback: Optional[Callable[[str], None]], quality: str = "best") -> Dict:
        """Download using yt-dlp"""
        opts = self.base_opts.copy()
        opts['outtmpl'] = os.path.join(download_path, '%(id)s.%(ext)s')
        
        # Add progress hook if callback provided
        if progress_callback:
            loop = asyncio.get_event_loop()
            tracker = ProgressTracker(progress_callback, loop)
            opts['progress_hooks'] = [tracker.progress_hook]
        
        # Platform specific options
        if "instagram.com" in url:
            if self.instagram_user and self.instagram_pass:
                opts['username'] = self.instagram_user
                opts['password'] = self.instagram_pass
            opts['format'] = 'best'
        elif "tiktok.com" in url:
            opts['format'] = 'best'
        elif "soundcloud.com" in url:
            # Download best audio from SoundCloud
            opts['format'] = 'bestaudio/best'
            # Use simpler template that works better with yt-dlp
            opts['outtmpl'] = os.path.join(download_path, '%(title)s.%(ext)s')
            
            # Add SoundCloud specific options
            opts['extractor_retries'] = 3
            
            # Check if FFmpeg is available for conversion
            if quality == "mp3":
                # User selected MP3 format
                try:
                    import subprocess
                    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
                    # FFmpeg available - convert to 320kbps MP3
                    opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '320',
                    }]
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # FFmpeg not available - download original format
                    logger.warning("FFmpeg not found, downloading original audio format")
                    pass
            else:
                # User selected Original format - download without conversion
                # Keep original format (opus/m4a)
                pass
        elif any(domain in url for domain in ['youtube.com', 'youtu.be']):
            if os.path.exists('cookies.txt'):
                opts['cookiefile'] = 'cookies.txt'
            
            # Quality-based format selection
            if quality == "720p":
                opts['format'] = 'best[ext=mp4][height<=720]/mp4[height<=720]/best[ext=mp4]'
            elif quality == "480p":
                opts['format'] = 'best[ext=mp4][height<=480]/mp4[height<=480]/best[ext=mp4]'
            elif quality == "360p":
                opts['format'] = 'best[ext=mp4][height<=360]/mp4[height<=360]/best[ext=mp4]'
            elif quality == "audio":
                opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
            else:  # best
                opts['format'] = 'best[ext=mp4]/mp4/best'
            
            opts['extractor_args'] = {'youtube': {'js_runtimes': 'node'}}
            opts['remote_components'] = {'ejs': 'github'}
        
        # Run in executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self._sync_ytdlp_download, 
            url, opts, download_path
        )

    def _sync_ytdlp_download(self, url: str, opts: dict, download_path: str) -> Dict:
        """Synchronous yt-dlp download"""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                logger.info(f"Downloading: {url}")
                logger.info(f"Output template: {opts.get('outtmpl', 'default')}")
                
                # Test extract info first
                logger.info("Extracting video info...")
                info = ydl.extract_info(url, download=False)
                logger.info(f"Extracted info: title={info.get('title', 'Unknown')}, id={info.get('id', 'Unknown')}")
                
                # Now do the actual download
                logger.info("Starting download...")
                ydl.download([url])
                
                logger.info("Download completed, looking for files...")
                
                files = []
                is_soundcloud = 'soundcloud.com' in url.lower()
                
                if 'entries' in info:
                    for entry in info['entries']:
                        if entry:
                            if is_soundcloud:
                                # For SoundCloud, find files by title
                                files.extend(self._find_soundcloud_files(download_path, entry))
                            else:
                                files.extend(self._find_downloaded_files(download_path, entry.get('id', '')))
                else:
                    if is_soundcloud:
                        # For SoundCloud, find files by title
                        files = self._find_soundcloud_files(download_path, info)
                    else:
                        files = self._find_downloaded_files(download_path, info.get('id', ''))

                files = list(dict.fromkeys(files))
                
                logger.info(f"Found files: {files}")

                if not files:
                    return {"success": False, "error": "No files were downloaded"}

                return {
                    "success": True,
                    "files": files,
                    "info": {
                        "caption": info.get('description') or info.get('title') or 'No caption',
                        "likes": info.get('like_count', 0),
                        "owner": info.get('uploader') or info.get('uploader_id') or 'Unknown',
                        "date": info.get('upload_date', 'Unknown'),
                        "title": info.get('title', 'Unknown')
                    }
                }
        except Exception as e:
            logger.error(f"yt-dlp error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _find_soundcloud_files(self, download_path: str, info: dict) -> List[str]:
        """Find SoundCloud files by title"""
        title = info.get('title', '')
        track_id = info.get('id', '')
        
        logger.info(f"Looking for SoundCloud files in {download_path}")
        logger.info(f"Title: {title}, ID: {track_id}")
        
        found_files = []
        try:
            files_in_dir = os.listdir(download_path)
            logger.info(f"Files in directory: {files_in_dir}")
            
            for f in files_in_dir:
                filepath = os.path.join(download_path, f)
                if not os.path.isfile(filepath):
                    continue
                
                # Check if it's an audio file
                ext = f.lower().split('.')[-1] if '.' in f else ''
                audio_exts = ['mp3', 'm4a', 'opus', 'ogg', 'wav', 'flac', 'aac']
                if ext not in audio_exts:
                    continue
                
                # Check if filename contains title
                if title:
                    expected_pattern = f"{title}"
                    if expected_pattern in f:
                        logger.info(f"Found matching file: {f}")
                        found_files.append(filepath)
                        return found_files
                
                # Check by ID
                if track_id and f.startswith(track_id):
                    logger.info(f"Found file by ID: {f}")
                    found_files.append(filepath)
                    return found_files
                
                # Last resort: any audio file in the directory
                logger.info(f"Found audio file: {f}")
                found_files.append(filepath)
                return found_files
        except Exception as e:
            logger.error(f"Error finding SoundCloud files: {e}")
        
        logger.warning(f"No SoundCloud files found in {download_path}")
        return found_files

    def _find_downloaded_files(self, download_path: str, base_name: str) -> List[str]:
        """Find downloaded files by matching base name"""
        if not base_name:
            return []
            
        found_files = []
        for f in os.listdir(download_path):
            if f.startswith(base_name):
                filepath = os.path.join(download_path, f)
                if os.path.isfile(filepath):
                    found_files.append(filepath)
        
        return found_files
    
    def _find_all_files(self, download_path: str) -> List[str]:
        """Find all files in download directory (for post-processed files)"""
        found_files = []
        try:
            for f in os.listdir(download_path):
                filepath = os.path.join(download_path, f)
                if os.path.isfile(filepath):
                    found_files.append(filepath)
        except:
            pass
        return found_files
    
    def is_supported_url(self, url: str) -> bool:
        """Check if URL is supported"""
        supported_domains = ['instagram.com', 'tiktok.com', 'soundcloud.com']
        if self.youtube_enabled:
            supported_domains.extend(['youtube.com', 'youtu.be'])
        url_lower = url.lower()
        return any(domain in url_lower for domain in supported_domains)
