"""
Authorization module for group access control
"""

import os
import json
import logging
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

AUTH_FILE = os.path.join("downloads", "authorized_groups.json")
VALID_API_KEY = os.getenv("API_KEY")

if not VALID_API_KEY:
    logger.error("API_KEY environment variable not set!")
    raise ValueError("API_KEY environment variable is required")

# Log that API key is loaded (without exposing the key)
logger.info("API key loaded successfully")


class Authorization:
    """Handle group authorization"""
    
    def __init__(self):
        self.authorized_groups = self._load_authorized_groups()
    
    def _load_authorized_groups(self) -> set:
        """Load authorized groups from file"""
        try:
            if os.path.exists(AUTH_FILE):
                with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    groups = data.get('groups', [])
                    if not isinstance(groups, list):
                        logger.warning("Invalid groups format in auth file, using empty set")
                        return set()
                    return set(groups)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading auth file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading auth file: {e}")
        return set()
    
    def _save_authorized_groups(self):
        """Save authorized groups to file"""
        try:
            # Ensure downloads directory exists
            Path(AUTH_FILE).parent.mkdir(parents=True, exist_ok=True)
            
            with open(AUTH_FILE, 'w', encoding='utf-8') as f:
                json.dump({'groups': list(self.authorized_groups)}, f, indent=2)
        except (IOError, OSError) as e:
            logger.error(f"Error saving auth file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving auth file: {e}")
    
    def authorize_group(self, api_key: str, chat_id: int) -> bool:
        """Authorize a chat (group or private) with API key"""
        try:
            if not api_key or not isinstance(chat_id, int):
                return False
            
            if api_key == VALID_API_KEY:
                self.authorized_groups.add(chat_id)
                self._save_authorized_groups()
                logger.info(f"Chat {chat_id} authorized successfully")
                return True
            
            logger.warning(f"Invalid API key attempt for chat {chat_id}")
            return False
        except Exception as e:
            logger.error(f"Error authorizing group {chat_id}: {e}")
            return False
    
    def is_chat_authorized(self, chat_id: int) -> bool:
        """Check if chat is authorized"""
        try:
            if not isinstance(chat_id, int):
                return False
            return chat_id in self.authorized_groups
        except Exception as e:
            logger.error(f"Error checking authorization for chat {chat_id}: {e}")
            return False