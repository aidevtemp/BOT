"""
URL storage for handling long URLs in Telegram callbacks and fetch history
"""

import hashlib
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

URL_STORAGE_FILE = os.path.join("downloads", "url_storage.json")
HISTORY_FILE = os.path.join("downloads", "fetch_history.json")

class URLStorage:
    """Store URLs with short hashes for callback data"""
    
    def __init__(self):
        self.urls = self._load_urls()
        self.history = self._load_history()
    
    def _load_urls(self) -> dict:
        """Load stored URLs"""
        try:
            if os.path.exists(URL_STORAGE_FILE):
                with open(URL_STORAGE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    logger.warning("Invalid URL storage format, using empty dict")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading URL storage: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading URL storage: {e}")
        return {}
    
    def _load_history(self) -> list:
        """Load fetch history"""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    logger.warning("Invalid history format, using empty list")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading history: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading history: {e}")
        return []
    
    def _save_urls(self):
        """Save URLs to file"""
        try:
            Path(URL_STORAGE_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(URL_STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.urls, f, indent=2)
        except (IOError, OSError) as e:
            logger.error(f"Error saving URL storage: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving URL storage: {e}")
    
    def _save_history(self):
        """Save fetch history to file"""
        try:
            Path(HISTORY_FILE).parent.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except (IOError, OSError) as e:
            logger.error(f"Error saving history: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving history: {e}")
    
    def store_url(self, url: str) -> str:
        """Store URL and return short hash"""
        try:
            if not url or not isinstance(url, str):
                raise ValueError("URL must be a non-empty string")
            
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
            self.urls[url_hash] = url
            self._save_urls()
            return url_hash
        except Exception as e:
            logger.error(f"Error storing URL: {e}")
            return ""
    
    def get_url(self, url_hash: str) -> str:
        """Get URL from hash"""
        try:
            if not url_hash or not isinstance(url_hash, str):
                return ""
            return self.urls.get(url_hash, "")
        except Exception as e:
            logger.error(f"Error retrieving URL for hash {url_hash}: {e}")
            return ""
    
    def add_to_history(self, url: str, user_id: int, username: str, platform: str, title: str = ""):
        """Add a fetched URL to history"""
        try:
            if not url or not isinstance(url, str):
                raise ValueError("URL must be a non-empty string")
            if not isinstance(user_id, int):
                raise ValueError("User ID must be an integer")
            
            entry = {
                "url": url,
                "user_id": user_id,
                "username": username or "Unknown",
                "platform": platform or "Unknown",
                "title": title or "No title",
                "timestamp": datetime.now().isoformat()
            }
            
            # Add to beginning of list
            self.history.insert(0, entry)
            
            # Keep only last 10 entries
            self.history = self.history[:10]
            
            self._save_history()
        except Exception as e:
            logger.error(f"Error adding to history: {e}")
    
    def clear_history(self):
        """Clear all fetch history"""
        try:
            self.history = []
            self._save_history()
            logger.info("History cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing history: {e}")
            raise
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent fetch history"""
        try:
            if not isinstance(limit, int) or limit < 0:
                limit = 10
            return self.history[:limit]
        except Exception as e:
            logger.error(f"Error retrieving history: {e}")
            return []
    
    def get_chat_history(self, chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get history for a specific chat (for future use if needed)"""
        try:
            if not isinstance(chat_id, int) or not isinstance(limit, int) or limit < 0:
                return []
            # For now, return global history
            return self.get_history(limit)
        except Exception as e:
            logger.error(f"Error retrieving chat history for {chat_id}: {e}")
            return []