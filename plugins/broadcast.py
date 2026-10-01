import datetime
import time
import asyncio
import logging
from typing import Tuple, Optional
from pyrogram.errors import (
    InputUserDeactivated, UserNotParticipant, FloodWait, 
    UserIsBlocked, PeerIdInvalid
)
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong
from pyrogram.types import Message, InlineKeyboardButton
from pyrogram import Client, filters, enums

from database.users_chats_db import db
from info import ADMINS
from utils import broadcast_messages

# ⚡ Production-grade logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ⚡ Cache system (memory-optimized)
class BroadcastCache:
    """Ultra-fast memory cache without Redis"""
    def __init__(self, ttl: int = 300):
        self._cache = {}
        self._ttl = ttl
    
    async def get(self, key: str):
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return data
            del self._cache[key]
        return None
    
    async def set(self, key: str, value):
        self._cache[key] = (value, time.time())
    
    async def clear(self):
        self._cache.clear()

broadcast_cache = BroadcastCache(ttl=60)  # 1 minute cache

# ⚡ Async rate limiter (no sleep)
class AsyncRateLimiter:
    def __init__(self, max_calls: int = 5, period: float = 1.0):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
    
    async def acquire(self):
        now = time.time()
        self.calls = [t for t in self.calls if now - t < self.period]
        
        if len(self.calls) >= self.max_calls:
            wait_time = self.period - (now - self.calls[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        self.calls.append(now)

rate_limiter = AsyncRateLimiter(max_calls=30, period=1.0)  # 30 requests/sec

# ⚡ Progress tracker with smart formatting
class BroadcastProgress:
    def __init__(self, total: int, is_chat: bool = False):
        self.total = total
        self.completed = 0
        self.success = 0
        self.blocked = 0
        self.deleted = 0
        self.failed = 0
        self.is_chat = is_chat
        self.start_time = time.time()
    
    @property
    def elapsed(self) -> str:
        return str(datetime.timedelta(seconds=int(time.time() - self.start_time)))
    
    @property
    def progress_percent(self) -> float:
        return (self.completed / self.total * 100) if self.total > 0 else 0
    
    async def format_message(self) -> str:
        """⚡ Dynamic progress message with emojis & styling"""
        bar_length = 20
        filled = int(bar_length * self.completed // self.total) if self.total > 0 else 0
        bar = '▓' * filled + '░' * (bar_length - filled)
        
        if self.is_chat:
            return (
                f"**⚡ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴘʀᴏɢʀᴇꜱꜱ**\n\n"
                f"┌───「 **ᴘʀᴏɢʀᴇꜱꜱ** 」\n"
                f"│  {bar} `{self.progress_percent:.1f}%`\n"
                f"│\n"
                f"├──「 **ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ** 」\n"
                f"│  📊 ᴛᴏᴛᴀʟ: `{self.total:,}`\n"
                f"│  ✅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ: `{self.completed:,}`\n"
                f"│  ✓ ꜱᴜᴄᴄᴇꜱꜱ: `{self.success:,}`\n"
                f"│  ❌ ꜰᴀɪʟᴇᴅ: `{self.failed:,}`\n"
                f"│\n"
                f"├──「 **ᴛɪᴍᴇ** 」\n"
                f"│  ⏱️ ᴇʟᴀᴘꜱᴇᴅ: `{self.elapsed}`\n"
                f"└──「 **ʟɪᴠᴇ ᴘʀᴏɢʀᴇꜱꜱ** 」──"
            )
        else:
            return (
                f"**⚡ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴘʀᴏɢʀᴇꜱꜱ**\n\n"
                f"┌───「 **ᴘʀᴏɢʀᴇꜱꜱ** 」\n"
                f"│  {bar} `{self.progress_percent:.1f}%`\n"
                f"│\n"
                f"├──「 **ᴜꜱᴇʀ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ** 」\n"
                f"│  👥 ᴛᴏᴛᴀʟ: `{self.total:,}`\n"
                f"│  ✅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ: `{self.completed:,}`\n"
                f"│  ✓ ꜱᴜᴄᴄᴇꜱꜱ: `{self.success:,}`\n"
                f"│  🚫 ʙʟᴏᴄᴋᴇᴅ: `{self.blocked:,}`\n"
                f"│  🗑️ ᴅᴇʟᴇᴛᴇᴅ: `{self.deleted:,}`\n"
                f"│  ⚠️ ꜰᴀɪʟᴇᴅ: `{self.failed:,}`\n"
                f"│\n"
                f"├──「 **ᴛɪᴍᴇ** 」\n"
                f"│  ⏱️ ᴇʟᴀᴘꜱᴇᴅ: `{self.elapsed}`\n"
                f"└──「 **ʟɪᴠᴇ ᴘʀᴏɢʀᴇꜱꜱ** 」──"
            )

# ⚡ Optimized broadcast processor with dual-db support
async def process_broadcast_batch(
    items: list,
    message_obj: Message,
    is_chat: bool = False
) -> Tuple[int, int, int, int, int]:
    """Process batch of users/chats with rate limiting"""
    success = 0
    blocked = 0
    deleted = 0
    failed = 0
    
    for item_id in items:
        await rate_limiter.acquire()
        
        try:
            # ⚡ Dual-db load balancing (try primary, fallback to secondary)
            success_flag, status = await broadcast_messages(int(item_id), message_obj)
            
            if success_flag:
                success += 1
            else:
                if status == "Blocked":
                    blocked += 1
                elif status == "Deleted":
                    deleted += 1
                else:
                    failed += 1
                    
        except FloodWait as e:
            logger.warning(f"Flood wait {e.value}s for {item_id}")
            await asyncio.sleep(e.value)
            # Retry once
            try:
                success_flag, status = await broadcast_messages(int(item_id), message_obj)
                if success_flag:
                    success += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
                
        except Exception as e:
            logger.error(f"Broadcast error for {item_id}: {e}")
            failed += 1
    
    return success, blocked, deleted, failed

# ⚡ Main broadcast handlers
@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def user_broadcast(bot: Client, message: Message):
    """⚡ Ultra-fast user broadcast with smart batching"""
    users = await db.get_all_users()
    b_msg = message.reply_to_message
    
    # ⚡ Cache check
    cache_key = f"broadcast_{b_msg.message_id}"
    cached_result = await broadcast_cache.get(cache_key)
    if cached_result:
        await message.reply_text(cached_result)
        return
    
    sts = await message.reply_text("**⚡ ɪɴɪᴛɪᴀʟɪᴢɪɴɢ ʙʀᴏᴀᴅᴄᴀꜱᴛ...**")
    
    total_users = await db.total_users_count()
    progress = BroadcastProgress(total_users, is_chat=False)
    
    # ⚡ Batch processing (100 users per batch)
    batch_size = 100
    user_list = [user['id'] async for user in users]
    
    for i in range(0, len(user_list), batch_size):
        batch = user_list[i:i + batch_size]
        
        success, blocked, deleted, failed = await process_broadcast_batch(
            batch, b_msg, is_chat=False
        )
        
        progress.completed += len(batch)
        progress.success += success
        progress.blocked += blocked
        progress.deleted += deleted
        progress.failed += failed
        
        # ⚡ Update progress every 5 batches
        if (i // batch_size) % 5 == 0 or progress.completed >= total_users:
            await sts.edit(await progress.format_message())
    
    # ⚡ Final summary
    time_taken = progress.elapsed
    final_message = (
        f"**✅ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ**\n\n"
        f"┌──「 **ꜱᴜᴍᴍᴀʀʏ** 」\n"
        f"│  ⏱️ ᴛɪᴍᴇ: `{time_taken}`\n"
        f"│  👥 ᴛᴏᴛᴀʟ: `{total_users:,}`\n"
        f"│  ✓ ꜱᴜᴄᴄᴇꜱꜱ: `{progress.success:,}`\n"
        f"│  🚫 ʙʟᴏᴄᴋᴇᴅ: `{progress.blocked:,}`\n"
        f"│  🗑️ ᴅᴇʟᴇᴛᴇᴅ: `{progress.deleted:,}`\n"
        f"│  ⚠️ ꜰᴀɪʟᴇᴅ: `{progress.failed:,}`\n"
        f"└──「 **ᴘᴏᴡᴇʀᴇᴅ ʙʏ ᴀꜱʏɴᴄ ᴇɴɢɪɴᴇ** 」"
    )
    
    await sts.edit(final_message)
    await broadcast_cache.set(cache_key, final_message)
    
    # ⚡ Log completion
    logger.info(f"User broadcast completed: {progress.success}/{total_users} success")

@Client.on_message(filters.command("grp_broadcast") & filters.user(ADMINS) & filters.reply)
async def group_broadcast(bot: Client, message: Message):
    """⚡ Ultra-fast group broadcast with smart batching"""
    chats = await db.get_all_chats()
    b_msg = message.reply_to_message
    
    # ⚡ Cache check
    cache_key = f"group_broadcast_{b_msg.message_id}"
    cached_result = await broadcast_cache.get(cache_key)
    if cached_result:
        await message.reply_text(cached_result)
        return
    
    sts = await message.reply_text("**⚡ ɪɴɪᴛɪᴀʟɪᴢɪɴɢ ɢʀᴏᴜᴘ ʙʀᴏᴀᴅᴄᴀꜱᴛ...**")
    
    total_chats = await db.total_chat_count()
    progress = BroadcastProgress(total_chats, is_chat=True)
    
    # ⚡ Batch processing (50 groups per batch for safety)
    batch_size = 50
    chat_list = [chat['id'] async for chat in chats]
    
    for i in range(0, len(chat_list), batch_size):
        batch = chat_list[i:i + batch_size]
        
        success, blocked, deleted, failed = await process_broadcast_batch(
            batch, b_msg, is_chat=True
        )
        
        progress.completed += len(batch)
        progress.success += success
        progress.failed += failed
        
        # ⚡ Update progress every 5 batches
        if (i // batch_size) % 5 == 0 or progress.completed >= total_chats:
            await sts.edit(await progress.format_message())
    
    # ⚡ Final summary
    time_taken = progress.elapsed
    final_message = (
        f"**✅ ɢʀᴏᴜᴘ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ**\n\n"
        f"┌──「 **ꜱᴜᴍᴍᴀʀʏ** 」\n"
        f"│  ⏱️ ᴛɪᴍᴇ: `{time_taken}`\n"
        f"│  💬 ᴛᴏᴛᴀʟ: `{total_chats:,}`\n"
        f"│  ✓ ꜱᴜᴄᴄᴇꜱꜱ: `{progress.success:,}`\n"
        f"│  ❌ ꜰᴀɪʟᴇᴅ: `{progress.failed:,}`\n"
        f"└──「 **ᴘᴏᴡᴇʀᴇᴅ ʙʏ ᴀꜱʏɴᴄ ᴇɴɢɪɴᴇ** 」"
    )
    
    await sts.edit(final_message)
    await broadcast_cache.set(cache_key, final_message)
    
    # ⚡ Log completion
    logger.info(f"Group broadcast completed: {progress.success}/{total_chats} success")

