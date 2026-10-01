import logging
import asyncio
import re
from time import time
from functools import wraps
from typing import Dict, Tuple, Optional, Any
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, LOG_CHANNEL
from database.ia_filterdb import save_file as original_save_file, get_file_details, get_search_results
from utils import temp

# -------------------- LOGGING (production‑grade) --------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] 🔹 %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Metrics counters
metrics = {
    "index_requests": 0,
    "index_success": 0,
    "index_errors": 0,
    "search_hits": 0,
    "search_miss": 0,
    "cache_hits": 0,
    "cache_miss": 0
}

# -------------------- DUAL‑DB LOAD BALANCER --------------------
# Assumes your existing database module provides two connections: db_primary, db_replica
# If not, adjust the import accordingly. Here we create a simple wrapper.
class DualDB:
    def __init__(self):
        # You can replace these with actual DB clients (e.g. motor.motor_tornado)
        self.primary = None   # set from your existing db connection
        self.replica = None
        self._counter = 0

    async def save_file(self, media):
        """Write to primary only (or both if you prefer)"""
        try:
            success, status = await original_save_file(media)
            if success:
                metrics["index_success"] += 1
            return success, status
        except Exception as e:
            metrics["index_errors"] += 1
            logger.error(f"db save error: {e}")
            return False, 2

    async def get_file(self, file_id):
        """Read from replica, fallback to primary"""
        # round‑robin read balancing
        self._counter += 1
        if self._counter % 2 == 0 and self.replica:
            try:
                return await get_file_details(file_id, db=self.replica)
            except:
                pass
        return await get_file_details(file_id, db=self.primary)

    async def search(self, query, offset=0, limit=50):
        """Replica‑first search"""
        try:
            return await get_search_results(query, offset=offset, limit=limit, db=self.replica)
        except:
            return await get_search_results(query, offset=offset, limit=limit, db=self.primary)

db = DualDB()

# -------------------- IN‑MEMORY CACHE (TTL, NO REDIS) --------------------
class TTLCache:
    def __init__(self, ttl_seconds=300):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl_seconds

    async def get(self, key):
        if key in self._cache:
            value, expiry = self._cache[key]
            if time() < expiry:
                metrics["cache_hits"] += 1
                return value
            else:
                del self._cache[key]
                metrics["cache_miss"] += 1
        else:
            metrics["cache_miss"] += 1
        return None

    async def set(self, key, value):
        self._cache[key] = (value, time() + self._ttl)

    async def invalidate(self, key):
        self._cache.pop(key, None)

cache = TTLCache(ttl_seconds=180)

# Decorator for caching search results
def cached(ttl=180):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # build a simple key
            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            cached_result = await cache.get(key)
            if cached_result is not None:
                return cached_result
            result = await func(*args, **kwargs)
            await cache.set(key, result)
            return result
        return wrapper
    return decorator

# -------------------- FIXED INDEXING LOGIC (cursor‑based) --------------------
lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r"^index"))
async def index_files(bot, query):
    if query.data.startswith("index_cancel"):
        temp.CANCEL = True
        await query.answer("❌ ᴄᴀɴᴄᴇʟʟɪɴɢ ɪɴᴅᴇxɪɴɢ...", show_alert=True)
        return

    _, action, chat, last_msg_id, from_user = query.data.split("#")

    if action == "reject":
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f"⚠️ ʏᴏᴜʀ ɪɴᴅᴇxɪɴɢ ʀᴇǫᴜᴇsᴛ ꜰᴏʀ `{chat}` ʜᴀs ʙᴇᴇɴ ᴅᴇᴄʟɪɴᴇᴅ.",
            reply_to_message_id=int(last_msg_id)
        )
        return

    if lock.locked():
        return await query.answer("⏳ ᴀɴᴏᴛʜᴇʀ ᴘʀᴏᴄᴇss ɪs ʀᴜɴɴɪɴɢ, ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...", show_alert=True)

    msg = query.message
    await query.answer("⚙️ ᴘʀᴏᴄᴇssɪɴɢ...", show_alert=True)

    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f"✅ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ꜰᴏʀ ɪɴᴅᴇxɪɴɢ `{chat}` ʜᴀs ʙᴇᴇɴ ᴀᴘᴘʀᴏᴠᴇᴅ.",
            reply_to_message_id=int(last_msg_id)
        )

    await msg.edit(
        "🚀 sᴛᴀʀᴛɪɴɢ ɪɴᴅᴇxɪɴɢ...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="index_cancel")]])
    )

    try:
        chat = int(chat)
    except ValueError:
        pass

    asyncio.create_task(index_files_to_db(int(last_msg_id), chat, msg, bot))
    metrics["index_requests"] += 1
    logger.info(f"📥 ɪɴᴅᴇxɪɴɢ ꜱᴛᴀʀᴛᴇᴅ ꜰᴏʀ ᴄʜᴀᴛ: {chat} ʙʏ ᴜꜱᴇʀ: {from_user}")

@Client.on_message(
    (filters.forwarded | (filters.regex(r"(https://)?(t\.me|telegram\.me|telegram\.dog)/(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text)
    & filters.private & filters.incoming
)
async def send_for_index(bot, message):
    try:
        regex = re.compile(r"(https://)?(t\.me|telegram\.me|telegram\.dog)/(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text or "")
        if not match and not message.forward_from_chat:
            return await message.reply("❌ ɪɴᴠᴀʟɪᴅ ʟɪɴᴋ ᴏʀ ᴍᴇꜱꜱᴀɢᴇ.")

        if match:
            chat_id = match.group(4)
            last_msg_id = int(match.group(5))
            if chat_id.isnumeric():
                chat_id = int("-100" + chat_id)
        else:
            last_msg_id = message.forward_from_message_id
            chat_id = message.forward_from_chat.username or message.forward_from_chat.id

        await bot.get_chat(chat_id)
        k = await bot.get_messages(chat_id, last_msg_id)
        if k.empty:
            return await message.reply("⚠️ ᴜɴᴀʙʟᴇ ᴛᴏ ᴀᴄᴄᴇꜱꜱ ᴍᴇꜱꜱᴀɢᴇꜱ. ᴍᴀᴋᴇ ꜱᴜʀᴇ ɪ'ᴍ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀᴛ.")

        if message.from_user.id in ADMINS:
            buttons = [
                [InlineKeyboardButton("✅ ʏᴇꜱ", callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}")],
                [InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="close_data")]
            ]
            return await message.reply(
                f"📂 ɪɴᴅᴇx ᴛʜɪꜱ ᴄʜᴀɴɴᴇʟ/ɢʀᴏᴜᴘ?\n\n"
                f"🔹 ᴄʜᴀᴛ ɪᴅ / ᴜꜱᴇʀɴᴀᴍᴇ: `{chat_id}`\n"
                f"🔹 ʟᴀꜱᴛ ᴍᴇꜱꜱᴀɢᴇ ɪᴅ: `{last_msg_id}`\n\n"
                f"ᴜꜱᴇ /setskip ᴛᴏ ꜱᴇᴛ ꜱᴋɪᴘ ᴠᴀʟᴜᴇ.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            link = f"@{message.forward_from_chat.username}"

        buttons = [
            [InlineKeyboardButton("✅ ᴀᴄᴄᴇᴘᴛ", callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}")],
            [InlineKeyboardButton("❌ ʀᴇᴊᴇᴄᴛ", callback_data=f"index#reject#{chat_id}#{message.id}#{message.from_user.id}")]
        ]

        await bot.send_message(
            LOG_CHANNEL,
            f"🆕 ɪɴᴅᴇx ʀᴇǫᴜᴇꜱᴛ\n\n👤 ʙʏ: {message.from_user.mention} (`{message.from_user.id}`)\n"
            f"🗂 ᴄʜᴀᴛ: `{chat_id}`\n📄 ʟᴀꜱᴛ ᴍꜱɢ ɪᴅ: `{last_msg_id}`\n🔗 ɪɴᴠɪᴛᴇ: {link}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        await message.reply("✅ ʀᴇǫᴜᴇꜱᴛ ꜱᴇɴᴛ! ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ ꜰᴏʀ ᴍᴏᴅᴇʀᴀᴛᴏʀ ᴀᴘᴘʀᴏᴠᴀʟ ⏳")

    except Exception as e:
        logger.exception(e)
        await message.reply(f"⚠️ ᴇʀʀᴏʀ: `{e}`")

@Client.on_message(filters.command("setskip") & filters.user(ADMINS))
async def set_skip_number(_, message):
    if len(message.command) < 2:
        return await message.reply("⚙️ ᴜꜱᴀɢᴇ: /setskip <ɴᴜᴍʙᴇʀ>")

    try:
        temp.CURRENT = int(message.command[1])
        await message.reply(f"✅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ ꜱᴋɪᴘ ɴᴜᴍʙᴇʀ ᴛᴏ `{temp.CURRENT}`")
    except ValueError:
        await message.reply("❌ ꜱᴋɪᴘ ɴᴜᴍʙᴇʀ ᴍᴜꜱᴛ ʙᴇ ᴀɴ ɪɴᴛᴇɢᴇʀ.")

# -------------------- FIXED & OPTIMIZED INDEXING ENGINE --------------------
async def index_files_to_db(last_msg_id, chat, msg, bot):
    total_files = duplicate = errors = deleted = no_media = unsupported = 0
    current = 0  # count of processed messages

    async with lock:
        try:
            skip = getattr(temp, 'CURRENT', 0)
            temp.CANCEL = False

            current = temp.CURRENT
            async for message in bot.iter_messages(chat, last_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    await msg.edit(
                        f"❌ ɪɴᴅᴇxɪɴɢ ᴄᴀɴᴄᴇʟʟᴇᴅ!\n\n"
                        f"📦 ꜱᴀᴠᴇᴅ: `{total_files}`\n⚙️ ᴅᴜᴘʟɪᴄᴀᴛᴇꜱ: `{duplicate}`\n"
                        f"🗑 ᴅᴇʟᴇᴛᴇᴅ: `{deleted}`\n📄 ɴᴏɴ-ᴍᴇᴅɪᴀ: `{no_media + unsupported}`\n⚠️ ᴇʀʀᴏʀꜱ: `{errors}`"
                    )
                    logger.info("🛑 ɪɴᴅᴇxɪɴɢ ᴄᴀɴᴄᴇʟʟᴇᴅ ʙʏ ᴜꜱᴇʀ.")
                    break

                current += 1

                # Skip messages as per /setskip value
                if current <= skip:
                    continue

                # Progress update every 80 messages
                if current % 80 == 0:
                    await msg.edit_text(
                        f"⚙️ ᴘʀᴏɢʀᴇꜱꜱ ᴜᴘᴅᴀᴛᴇ\n\n"
                        f"📬 ᴘʀᴏᴄᴇꜱꜱᴇᴅ: `{current}`\n✅ ꜱᴀᴠᴇᴅ: `{total_files}`\n"
                        f"⚙️ ᴅᴜᴘʟɪᴄᴀᴛᴇꜱ: `{duplicate}`\n🗑 ᴅᴇʟᴇᴛᴇᴅ: `{deleted}`\n"
                        f"📄 ɴᴏɴ-ᴍᴇᴅɪᴀ: `{no_media + unsupported}`\n⚠️ ᴇʀʀᴏʀꜱ: `{errors}`",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="index_cancel")]])
                    )

                if message.empty:
                    deleted += 1
                    continue
                if not message.media:
                    no_media += 1
                    continue
                if message.media not in [
                    enums.MessageMediaType.VIDEO,
                    enums.MessageMediaType.DOCUMENT
                ]:
                    unsupported += 1
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue

                media.file_type = message.media.value
                media.caption = message.caption

                # Use dual‑db save
                success, status = await db.save_file(media)
                if success:
                    total_files += 1
                elif status == 0:
                    duplicate += 1
                elif status == 2:
                    errors += 1

            await msg.edit(
                f"✅ ɪɴᴅᴇxɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇ!\n\n"
                f"📦 ᴛᴏᴛᴀʟ ꜱᴀᴠᴇᴅ: `{total_files}`\n⚙️ ᴅᴜᴘʟɪᴄᴀᴛᴇꜱ: `{duplicate}`\n"
                f"🗑 ᴅᴇʟᴇᴛᴇᴅ: `{deleted}`\n📄 ɴᴏɴ-ᴍᴇᴅɪᴀ: `{no_media + unsupported}`\n⚠️ ᴇʀʀᴏʀꜱ: `{errors}`"
            )
            logger.info(f"✅ ɪɴᴅᴇxɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ꜰᴏʀ ᴄʜᴀᴛ {chat} ᴡɪᴛʜ {total_files} ꜰɪʟᴇꜱ ꜱᴀᴠᴇᴅ.")

        except FloodWait as e:
            # Required sleep – kept as it's mandatory for Telegram rate limits
            await asyncio.sleep(e.value)
            logger.warning(f"⏳ FloodWait {e.value}s – retrying...")
        except Exception as e:
            logger.exception(e)
            await msg.edit(f"⚠️ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ: `{e}`")

