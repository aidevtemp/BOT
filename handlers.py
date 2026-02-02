"""
Bot handlers for Instagram and TikTok downloads with progress bar
"""

import os
import time
import asyncio
import logging
import re
from urllib.parse import urlparse
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
from downloader import ContentDownloader
from auth import Authorization
from url_storage import URLStorage

logger = logging.getLogger(__name__)

# Configuration
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
RATE_LIMIT_SECONDS = 20  # 20 second rate limit

# Store last request times: {user_id: timestamp}
last_request_times = {}


class BotHandlers:
    """Handle bot commands and callbacks"""
    
    def __init__(self):
        self.downloader = ContentDownloader()
        self.auth = Authorization()
        self.url_storage = URLStorage()
        self.youtube_enabled = self.downloader.youtube_enabled
    
    def _get_platform(self, url: str) -> str:
        """Get platform name from URL using proper domain extraction"""
        try:
            parsed = urlparse(url.lower())
            domain = parsed.netloc.lower()
            
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            if domain == 'instagram.com':
                return 'Instagram'
            elif domain == 'tiktok.com':
                return 'TikTok'
            elif domain in ['youtube.com', 'youtu.be']:
                return 'YouTube'
            elif domain == 'soundcloud.com':
                return 'SoundCloud'
            return 'Unknown'
        except Exception as e:
            logger.error(f"Error parsing URL {url}: {e}")
            return 'Unknown'
    
    def _escape_markdown(self, text: str) -> str:
        """Escape markdown special characters efficiently"""
        if not text:
            return ""
        # Use translation table for better performance
        escape_chars = '_*[]()~`>#+-=|{}.!'
        translation_table = str.maketrans({char: f'\\{char}' for char in escape_chars})
        return text.translate(translation_table)
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """Check if user is rate limited. Returns True if allowed."""
        current_time = time.time()
        last_time = last_request_times.get(user_id, 0)
        
        if current_time - last_time < RATE_LIMIT_SECONDS:
            return False
        
        last_request_times[user_id] = current_time
        return True
    
    def _sanitize_user_id(self, user_id: int) -> str:
        """Sanitize user ID for safe file path usage"""
        # Convert to string and ensure it only contains digits
        sanitized = re.sub(r'[^0-9]', '', str(user_id))
        if not sanitized:
            raise ValueError(f"Invalid user ID: {user_id}")
        return sanitized
    
    def _create_safe_user_dir(self, user_id: int) -> str:
        """Create safe user directory path"""
        sanitized_id = self._sanitize_user_id(user_id)
        user_dir = Path(DOWNLOAD_DIR) / sanitized_id
        
        # Ensure the path is within DOWNLOAD_DIR
        try:
            user_dir = user_dir.resolve()
            download_dir_resolved = Path(DOWNLOAD_DIR).resolve()
            if not str(user_dir).startswith(str(download_dir_resolved)):
                raise ValueError("Path traversal attempt detected")
        except Exception as e:
            logger.error(f"Path validation error: {e}")
            raise ValueError("Invalid path")
        
        return str(user_dir)
    
    def _check_authorization(self, update: Update) -> bool:
        """Check if chat is authorized"""
        try:
            chat_id = update.effective_chat.id
            return self.auth.is_chat_authorized(chat_id)
        except Exception as e:
            logger.error(f"Authorization check error: {e}")
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        try:
            platforms = ("🚀 *Instagram, TikTok & YouTube Downloader Bot* 🚀\n\n" 
                        if self.youtube_enabled 
                        else "🚀 *Instagram & TikTok Downloader Bot* 🚀\n\n")
            
            supported_text = "📥 *Supported Platforms:*\n• *Instagram:* Posts, Reels, IGTV, Carousels\n• *TikTok:* Videos without watermark\n• *SoundCloud:* Music & Audio\n"
            if self.youtube_enabled:
                supported_text += "• *YouTube:* Videos, Shorts, Music\n"
            
            welcome_message = (
                platforms +
                "Welcome! I can download content from supported platforms.\n\n" +
                supported_text + "\n" +
                "📋 *How to use:*\n"
                "`/fetch <URL>`\n"
                "or reply to a message with URL: `/fetch`\n\n"
                "⏱ *Rate Limit:* 20 seconds between requests\n\n"
                "🔐 *Authorization Required:*\n"
                "Use: `/apikey <key>`\n\n"
                "Example:\n"
                "`/fetch https://www.instagram.com/p/ABC123/`"
            )
            
            await update.message.reply_text(
                welcome_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await update.message.reply_text(
                "❌ An error occurred. Please try again later.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def fetch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /fetch command with rate limiting"""
        try:
            # Check authorization first
            if not self._check_authorization(update):
                await update.message.reply_text(
                    "❌ This chat needs authorization to use the bot.\n\n"
                    "Use: `/apikey <key>` to authorize this chat.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Check rate limit
            user_id = update.effective_user.id
            if not self._check_rate_limit(user_id):
                remaining = RATE_LIMIT_SECONDS - int(time.time() - last_request_times.get(user_id, 0))
                await update.message.reply_text(
                    f"⏱ Please wait {remaining} seconds before making another request.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            url = self._extract_url(update, context)
            
            if not url:
                await update.message.reply_text(
                    "❌ Please provide a URL or reply to a message with URL!\n\n"
                    "Usage:\n"
                    "`/fetch <URL>`\n"
                    "or reply to a message: `/fetch`\n\n"
                    "Supported: Instagram, TikTok, SoundCloud" + (", YouTube" if self.youtube_enabled else ""),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            if not self.downloader.is_supported_url(url):
                supported_list = "• instagram.com\n• tiktok.com\n• soundcloud.com"
                if self.youtube_enabled:
                    supported_list += "\n• youtube.com\n• youtu.be"
                
                await update.message.reply_text(
                    "❌ Unsupported URL or platform!\n\n"
                    "Supported domains:\n" + supported_list
                )
                return
            
            # Process download with progress bar
            if any(domain in url for domain in ['youtube.com', 'youtu.be']) and self.youtube_enabled:
                await self.show_format_selection(update, context, url)
            elif 'soundcloud.com' in url.lower():
                await self.show_soundcloud_format_selection(update, context, url)
            else:
                await self.process_download(update, context, url, "video", "best")
                
        except Exception as e:
            logger.error(f"Error in fetch command: {e}")
            await update.message.reply_text(
                "❌ An error occurred while processing your request. Please try again later.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    def _extract_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Extract URL from message or reply"""
        url = None
        
        # Check if replying to a message with URL
        if update.message.reply_to_message:
            reply_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
            words = reply_text.split()
            for word in words:
                if self.downloader.is_supported_url(word):
                    url = word
                    break
        
        # Check command arguments
        elif context.args:
            url = context.args[0]
        
        return url

    
    async def process_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, format_type: str, quality: str = "best"):
        """Process download with live progress bar"""
        progress_msg = None
        progress_task = None
        
        try:
            chat_id = update.effective_chat.id
            
            # Send initial message
            progress_msg = await update.effective_chat.send_message(
                "⏳ Starting download...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Create a queue for progress updates
            progress_queue = asyncio.Queue()
            last_message_content = {"text": "", "time": 0}
            message_update_lock = asyncio.Lock()
            
            async def update_progress_message():
                """Update the progress message with rate limiting"""
                while True:
                    try:
                        message = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                        
                        if message == "DONE":
                            break
                        
                        async with message_update_lock:
                            current_time = time.time()
                            # Only update if message changed and 1 second passed
                            if (message != last_message_content["text"] and 
                                current_time - last_message_content["time"] >= 1.0):
                                try:
                                    await progress_msg.edit_text(message, parse_mode=ParseMode.MARKDOWN)
                                    last_message_content["text"] = message
                                    last_message_content["time"] = current_time
                                except Exception as e:
                                    # Ignore "message not modified" errors
                                    if "message is not modified" not in str(e).lower():
                                        logger.error(f"Progress update error: {e}")
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Progress queue error: {e}")
            
            def progress_callback(message: str):
                """Callback for download progress"""
                try:
                    asyncio.create_task(progress_queue.put(message))
                except Exception as e:
                    logger.error(f"Progress callback error: {e}")
            
            # Start progress updater
            progress_task = asyncio.create_task(update_progress_message())
            
            user_dir = self._create_safe_user_dir(update.effective_user.id)
            
            # Download with progress
            result = await self.downloader.download(url, user_dir, progress_callback, format_type, quality)
            
            # Stop progress updater
            await progress_queue.put("DONE")
            if progress_task:
                await progress_task
            
            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                await progress_msg.edit_text(
                    f"❌ Download failed: {self._escape_markdown(error_msg)}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            await self._send_downloaded_files(update, progress_msg, result, url)
            
        except Exception as e:
            logger.error(f"Download process error: {e}")
            if progress_msg:
                try:
                    await progress_msg.edit_text(
                        "❌ An error occurred during download. Please try again later.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
        finally:
            # Cleanup
            if progress_task and not progress_task.done():
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
    async def _send_downloaded_files(self, update: Update, progress_msg, result: dict, url: str):
        """Send downloaded files to user"""
        try:
            # Show upload message
            await progress_msg.edit_text(
                f"✅ Download complete!\n"
                f"📤 Uploading {len(result['files'])} file(s)..."
            )
            
            # Save to history
            user = update.effective_user
            platform = self._get_platform(url)
            title = result['info'].get('title', 'No title')
            self.url_storage.add_to_history(
                url=url,
                user_id=user.id,
                username=user.username or user.first_name,
                platform=platform,
                title=title
            )
            
            info = result['info']
            raw_caption = info.get('caption', '')
            clean_caption = (raw_caption[:300] + '...') if len(raw_caption) > 300 else raw_caption
            
            # Escape markdown characters in caption and owner with safe access
            safe_caption = self._escape_markdown(clean_caption)
            safe_owner = self._escape_markdown(info.get('owner', 'Unknown'))
            safe_date = self._escape_markdown(info.get('date', 'Unknown'))
            
            caption = (
                f"📝 {safe_caption}\n\n"
                f"👤 *Owner:* {safe_owner}\n"
                f"📅 *Date:* {safe_date}"
            )
            
            await update.effective_chat.send_chat_action(action=ChatAction.UPLOAD_DOCUMENT)
            
            for idx, filepath in enumerate(result['files']):
                if not os.path.exists(filepath):
                    continue
                    
                file_size = os.path.getsize(filepath)
                
                if file_size > MAX_FILE_SIZE:
                    await update.effective_chat.send_message(
                        f"⚠️ File {idx+1} is too large ({file_size/1024/1024:.1f}MB)\n"
                        f"Maximum size: 50MB"
                    )
                    continue
                
                await self._send_file_by_type(update, filepath, caption if idx == 0 else None)
            
            await progress_msg.delete()
            
            # Cleanup files
            self._cleanup_files(result['files'])
            
        except Exception as e:
            logger.error(f"Error sending files: {e}")
            raise
    
    async def _send_file_by_type(self, update: Update, filepath: str, caption: str = None):
        """Send file based on its type"""
        ext = filepath.lower().split('.')[-1]
        is_video = ext in ['mp4', 'mkv', 'webm', 'mov']
        is_audio = ext in ['m4a', 'mp3', 'wav', 'ogg']
        is_image = ext in ['jpg', 'jpeg', 'png', 'webp']
        
        try:
            with open(filepath, 'rb') as file:
                if is_audio:
                    await update.effective_chat.send_audio(
                        audio=file,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif is_video:
                    await update.effective_chat.send_video(
                        video=file,
                        caption=caption,
                        supports_streaming=True,
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif is_image:
                    await update.effective_chat.send_photo(
                        photo=file,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await update.effective_chat.send_document(
                        document=file,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
        except Exception as e:
            logger.error(f"Upload failed for {filepath}: {e}")
            await update.effective_chat.send_message(f"⚠️ Upload failed: {str(e)}")
    
    def _cleanup_files(self, filepaths: list):
        """Clean up downloaded files"""
        for filepath in filepaths:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError as e:
                logger.warning(f"Could not delete file {filepath}: {e}")
    
    async def apikey_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /apikey command"""
        try:
            # Try to delete the API key message for security
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete API key message: {e}")
            
            if not context.args:
                await update.effective_chat.send_message(
                    "❌ Please provide an API key!\n\n"
                    "Usage: `/apikey <your_key>`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            api_key = context.args[0]
            chat_id = update.effective_chat.id
            
            if self.auth.authorize_group(api_key, chat_id):
                supported_text = "📥 **Supported:**\n• Instagram, TikTok, SoundCloud"
                if self.youtube_enabled:
                    supported_text = "📥 **Supported:**\n• Instagram, TikTok, YouTube, SoundCloud"
                
                await update.effective_chat.send_message(
                    "✅ **Chat authorized successfully!** 🚀\n\n"
                    "📋 **Usage:**\n"
                    "• `/fetch <URL>` - Direct download\n"
                    "• Reply to message with `/fetch`\n"
                    "• `/history` - Show recent fetches\n\n" +
                    supported_text + "\n\n"
                    "⏱ **Rate Limit:** 20 seconds between requests",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.effective_chat.send_message(
                    "❌ Invalid API key! Contact the bot administrator."
                )
        except Exception as e:
            logger.error(f"Error in apikey command: {e}")
            await update.effective_chat.send_message(
                "❌ An error occurred while processing the API key."
            )
    
    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command - Show recent fetched URLs"""
        try:
            # Check authorization first
            if not self._check_authorization(update):
                await update.message.reply_text(
                    "❌ This chat needs authorization to use the bot.\n\n"
                    "Use: `/apikey <key>` to authorize this chat.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            try:
                history = self.url_storage.get_history(limit=10)
            except Exception as e:
                logger.error(f"Error retrieving history: {e}")
                await update.message.reply_text(
                    "❌ Error retrieving history. Please try again later.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            if not history:
                await update.message.reply_text(
                    "📭 *No fetch history yet!*\n\n"
                    "Use `/fetch <URL>` to download content.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Build the message with clickable /fetch commands
            message_lines = ["📜 *Recent Fetch History*\n"]
            keyboard = []
            
            for idx, entry in enumerate(history, 1):
                platform = entry.get('platform', 'Unknown')
                title = entry.get('title', 'No title')[:30]  # Consistent truncation
                url = entry.get('url', '')
                username = entry.get('username', 'Unknown')
                
                # Escape markdown characters
                safe_title = self._escape_markdown(title)
                safe_username = self._escape_markdown(username)
                
                # Platform emoji
                emoji = {'Instagram': '📷', 'TikTok': '🎵', 'YouTube': '📺', 'SoundCloud': '🎶'}.get(platform, '🔗')
                
                message_lines.append(
                    f"{idx}. {emoji} *{platform}* - _{safe_title}_\n"
                    f"   👤 By: {safe_username}\n"
                )
                
                # Add button to re-fetch this URL
                keyboard.append([InlineKeyboardButton(
                    f"{idx}. 📥 Fetch again: {title}...",
                    callback_data=f"refetch_{idx-1}"
                )])
            
            # Add clear history button
            keyboard.append([InlineKeyboardButton(
                "🗑️ Clear History",
                callback_data="clear_history"
            )])
            
            message_lines.append(f"\n_Total: {len(history)} items_")
            
            await update.message.reply_text(
                "\n".join(message_lines),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )
        except Exception as e:
            logger.error(f"Error in history command: {e}")
            await update.message.reply_text(
                "❌ An error occurred while retrieving history.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def show_format_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        """Show format selection for YouTube"""
        if not url:
            raise ValueError("URL cannot be empty")
        
        # Store URL in context for callback
        context.user_data['pending_url'] = url
        
        keyboard = [
            [InlineKeyboardButton("🎬 Best Quality", callback_data="fmt_best")],
            [InlineKeyboardButton("📺 720p MP4", callback_data="fmt_720p")],
            [InlineKeyboardButton("📱 480p MP4", callback_data="fmt_480p")],
            [InlineKeyboardButton("📞 360p MP4", callback_data="fmt_360p")],
            [InlineKeyboardButton("🎵 Audio Only", callback_data="fmt_audio")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📋 **Choose download format:**",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_soundcloud_format_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        """Show format selection for SoundCloud"""
        if not url:
            raise ValueError("URL cannot be empty")
        
        # Store URL in context for callback
        context.user_data['pending_url'] = url
        
        keyboard = [
            [InlineKeyboardButton("🎵 Original (Opus)", callback_data="sc_original")],
            [InlineKeyboardButton("🎧 MP3 (320kbps)", callback_data="sc_mp3")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🎵 **SoundCloud Format Selection**\n\n"
            "• *Original (Opus)* - Best quality, smaller size\n"
            "• *MP3* - Universal compatibility",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_format_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle format selection callback"""
        query = update.callback_query
        await query.answer()
        
        try:
            data = query.data
            
            if data.startswith("fmt_"):
                quality = data.replace("fmt_", "")
                url = context.user_data.get('pending_url')
                
                if not url:
                    await query.edit_message_text("❌ Error: URL not found. Please try again.")
                    return
                
                # Delete the callback message and start fresh
                await query.delete_message()
                await self.process_download(update, context, url, "video", quality)
            
            elif data.startswith("sc_"):
                # SoundCloud format selection
                soundcloud_format = data.replace("sc_", "")  # "original" or "mp3"
                url = context.user_data.get('pending_url')
                
                if not url:
                    await query.edit_message_text("❌ Error: URL not found. Please try again.")
                    return
                
                # Delete the callback message and start fresh
                await query.delete_message()
                
                # Pass the format as quality parameter (will be handled in downloader)
                await self.process_download(update, context, url, "audio", soundcloud_format)
            
            elif data == "clear_history":
                # Handle clear history
                try:
                    self.url_storage.clear_history()
                    await query.edit_message_text(
                        "✅ *History cleared successfully!*\n\n"
                        "📭 No fetch history available.\n\n"
                        "Use `/fetch <URL>` to download content.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Error clearing history: {e}")
                    await query.edit_message_text("❌ Error clearing history. Please try again.")
            
            elif data.startswith("refetch_"):
                # Handle refetch from history
                try:
                    idx_str = data.replace("refetch_", "")
                    if not idx_str.isdigit():
                        raise ValueError(f"Invalid index: {idx_str}")
                    
                    idx = int(idx_str)
                    history = self.url_storage.get_history(limit=10)
                    
                    if idx < len(history):
                        entry = history[idx]
                        url = entry.get('url', '')
                        platform = entry.get('platform', 'Unknown')
                        
                        if url:
                            # Check platform for appropriate handling
                            if platform == 'YouTube' and self.youtube_enabled:
                                # Store URL for format selection
                                context.user_data['pending_url'] = url
                                
                                keyboard = [
                                    [InlineKeyboardButton("🎬 Best Quality", callback_data="fmt_best")],
                                    [InlineKeyboardButton("📺 720p MP4", callback_data="fmt_720p")],
                                    [InlineKeyboardButton("📱 480p MP4", callback_data="fmt_480p")],
                                    [InlineKeyboardButton("📞 360p MP4", callback_data="fmt_360p")],
                                    [InlineKeyboardButton("🎵 Audio Only", callback_data="fmt_audio")]
                                ]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                
                                await query.edit_message_text(
                                    "📋 **Choose download format:**",
                                    reply_markup=reply_markup,
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            elif platform == 'SoundCloud':
                                # Store URL for format selection
                                context.user_data['pending_url'] = url
                                
                                keyboard = [
                                    [InlineKeyboardButton("🎵 Original (Opus)", callback_data="sc_original")],
                                    [InlineKeyboardButton("🎧 MP3 (320kbps)", callback_data="sc_mp3")]
                                ]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                
                                await query.edit_message_text(
                                    "🎵 **SoundCloud Format Selection**\n\n"
                                    "• *Original (Opus)* - Best quality, smaller size\n"
                                    "• *MP3* - Universal compatibility",
                                    reply_markup=reply_markup,
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            else:
                                # Delete the callback message and start download
                                await query.delete_message()
                                await self.process_download(update, context, url, "video", "best")
                        else:
                            await query.edit_message_text("❌ Error: URL not found in history.")
                    else:
                        await query.edit_message_text("❌ Error: History entry not found.")
                except ValueError as e:
                    logger.error(f"Invalid callback data: {e}")
                    await query.edit_message_text("❌ Error: Invalid request.")
                except Exception as e:
                    logger.error(f"Refetch error: {e}")
                    await query.edit_message_text(f"❌ Error re-fetching: {str(e)}")
        except Exception as e:
            logger.error(f"Callback handler error: {e}")
            try:
                await query.edit_message_text("❌ An error occurred. Please try again.")
            except Exception:
                pass
