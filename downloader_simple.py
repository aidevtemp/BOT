"""
Simple downloader for Instagram and TikTok
"""

import os
import yt_dlp
from typing import Dict

class ContentDownloader:
    """Simple content downloader"""
    
    def __init__(self):
        self.instagram_user = os.getenv("INSTAGRAM_USERNAME")
        self.instagram_pass = os.getenv("INSTAGRAM_PASSWORD")
    
    def download(self, url: str, download_path: str) -> Dict:
        """Download content from URL"""
        try:
            os.makedirs(download_path, exist_ok=True)
            
            ydl_opts = {
                'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                'format': 'best',
                'quiet': False,
            }
            
            if "instagram.com" in url and self.instagram_user and self.instagram_pass:
                ydl_opts['username'] = self.instagram_user
                ydl_opts['password'] = self.instagram_pass
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                files = []
                for f in os.listdir(download_path):
                    filepath = os.path.join(download_path, f)
                    if os.path.isfile(filepath):
                        files.append(filepath)
                
                if not files:
                    return {"success": False, "error": "No files downloaded"}
                
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
            return {"success": False, "error": str(e)}
    
    def is_supported_url(self, url: str) -> bool:
        """Check if URL is supported"""
        supported_domains = ['instagram.com', 'tiktok.com']
        url_lower = url.lower()
        return any(domain in url_lower for domain in supported_domains)
