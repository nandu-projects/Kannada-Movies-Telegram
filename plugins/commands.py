import os
import logging
import random
import asyncio
import time
import re
import json
import base64
from functools import lru_cache
from Script import script
from pyrogram import Client, filters, enums
from pyrogram.errors import ChatAdminRequired, FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.ia_filterdb import Media, Media2, get_file_details, unpack_new_file_id
from database.users_chats_db import db
from info import *
from utils import get_settings, get_size, is_subscribed, save_group_settings, temp, verify_user, check_token, check_verification, get_token
from database.connections_mdb import active_connection

logger = logging.getLogger(__name__)

BATCH_FILES = {}

# ---------- In‑Memory Cache for get_file_details (TTL = 5 minutes) ----------
_file_cache = {}
_CACHE_TTL = 300  # seconds

async def cached_get_file_details(file_id: str):
    now = time.time()
    if file_id in _file_cache:
        cached_data, timestamp = _file_cache[file_id]
        if now - timestamp < _CACHE_TTL:
            return cached_data
        else:
            del _file_cache[file_id]
    data = await get_file_details(file_id)
    _file_cache[file_id] = (data, now)
    return data
# ---------------------------------------------------------------------------

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        buttons = [[
            InlineKeyboardButton("➕️ Aᴅᴅ Mᴇ Tᴏ Yᴏᴜʀ Cʜᴀᴛ ➕", url=f"http://t.me/{temp.U_NAME}?startgroup=true"),
            ],[
            InlineKeyboardButton("🔎 Sᴇᴀʀᴄʜ", switch_inline_query_current_chat=''),
            ],[
            InlineKeyboardButton("Hᴇʟᴩ 🕸️", callback_data="help"),
            InlineKeyboardButton("Aʙᴏᴜᴛ ✨", callback_data="about")
            ],[
            InlineKeyboardButton("𝗗𝗼𝗻𝗮𝘁𝗲 𝗧𝗼 𝗠𝗲 ❤️", callback_data="donate")
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        if not await db.get_chat(message.chat.id):
            total = await client.get_chat_members_count(message.chat.id)
            await client.send_message(LOG_CHANNEL, script.LOG_TEXT_G.format(message.chat.title, message.chat.id, total, "Unknown"))
            await db.add_chat(message.chat.id, message.chat.title)
        return

    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(message.from_user.id, message.from_user.mention))

    if len(message.command) != 2:
        buttons = [[
            InlineKeyboardButton("➕️ Aᴅᴅ Mᴇ Tᴏ Yᴏᴜʀ Cʜᴀᴛ ➕", url=f"http://t.me/{temp.U_NAME}?startgroup=true"),
            ],[
            InlineKeyboardButton("🔎 Sᴇᴀʀᴄʜ", switch_inline_query_current_chat=''),
            ],[
            InlineKeyboardButton("Hᴇʟᴩ 🕸️", callback_data="help"),
            InlineKeyboardButton("Aʙᴏᴜᴛ ✨", callback_data="about")
            ],[
            InlineKeyboardButton("𝗗𝗼𝗻𝗮𝘁𝗲 𝗧ᴏ 𝗠ᴇ ❤️", callback_data="donate")
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return

    invite_links = await is_subscribed(client, message)
    if AUTH_CHANNEL and len(invite_links) >= 1:
        btn = []
        for chnl_num, link in enumerate(invite_links, start=1):
            if chnl_num == 1:
                channel_num = "1sᴛ"
            elif chnl_num == 2:
                channel_num = "2ɴᴅ"
            elif chnl_num == 3:
                channel_num = "3ʀᴅ"
            else:
                channel_num = str(chnl_num) + "ᴛʜ"
            btn.append([
                InlineKeyboardButton(f"❆ Jᴏɪɴ Cʜᴀɴɴᴇʟ {channel_num} ❆", url=link)
            ])

        if message.command[1] != "subscribe":
            try:
                kk, file_id = message.command[1].split("_", 1)
                pre = 'checksubp' if kk == 'filep' else 'checksub'
                btn.append([InlineKeyboardButton("↻ Tʀʏ Aɢᴀɪɴ", callback_data=f"{pre}#{file_id}")])
            except (IndexError, ValueError):
                btn.append([InlineKeyboardButton("↻ Tʀʏ Aɢᴀɪɴ", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")])
        await client.send_message(
            chat_id=message.from_user.id,
            text="**Yᴏᴜ ᴀʀᴇ ɴᴏᴛ ɪɴ ᴏᴜʀ Bᴀᴄᴋ-ᴜᴘ ᴄʜᴀɴɴᴇʟs ɢɪᴠᴇɴ ʙᴇʟᴏᴡ sᴏ ʏᴏᴜ ᴅᴏɴ'ᴛ ɢᴇᴛ ᴛʜᴇ ᴍᴏᴠɪᴇ ғɪʟᴇ...\n\nIғ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜᴇ ᴍᴏᴠɪᴇ ғɪʟᴇ, ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ɢɪᴠᴇɴ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴀɴᴅ ᴊᴏɪɴ ᴏᴜʀ ʙᴀᴄᴋ-ᴜᴘ ᴄʜᴀɴɴᴇʟs, ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ '↻ Tʀʏ Aɢᴀɪɴ' ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ...\n\nTʜᴇɴ ʏᴏᴜ ᴡɪʟʟ ɢᴇᴛ ᴛʜᴇ ᴍᴏᴠɪᴇ ғɪʟᴇs...**",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    if len(message.command) == 2 and message.command[1] in ["subscribe", "error", "okay", "help"]:
        buttons = [[
            InlineKeyboardButton("➕️ Aᴅᴅ Mᴇ Tᴏ Yᴏᴜʀ Cʜᴀᴛ ➕", url=f"http://t.me/{temp.U_NAME}?startgroup=true"),
            ],[
            InlineKeyboardButton("🔎 Sᴇᴀʀᴄʜ", switch_inline_query_current_chat=''),
            ],[
            InlineKeyboardButton("Hᴇʟᴩ 🕸️", callback_data="help"),
            InlineKeyboardButton("Aʙᴏᴜᴛ ✨", callback_data="about")
            ],[
            InlineKeyboardButton("𝗗𝗼𝗻𝗮𝘁𝗲 𝗧ᴏ 𝗠ᴇ ❤️", callback_data="donate")
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return

    data = message.command[1]
    try:
        pre, file_id = data.split('_', 1)
    except:
        file_id = data
        pre = ""

    # --------------------- BATCH (JSON) ---------------------
    if data.split("-", 1)[0] == "BATCH":
        sts = await message.reply("🔄 **ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...**")
        file_id = data.split("-", 1)[1]
        msgs = BATCH_FILES.get(file_id)
        if not msgs:
            file = await client.download_media(file_id)
            try:
                with open(file) as file_data:
                    msgs = json.loads(file_data.read())
            except:
                await sts.edit("❌ **ғᴀɪʟᴇᴅ ᴛᴏ ᴏᴘᴇɴ ғɪʟᴇ.**")
                return await client.send_message(LOG_CHANNEL, "UNABLE TO OPEN FILE.")
            os.remove(file)
            BATCH_FILES[file_id] = msgs
        for msg in msgs:
            title = msg.get("title")
            size = get_size(int(msg.get("size", 0)))
            f_caption = msg.get("caption", "")
            if BATCH_FILE_CAPTION:
                try:
                    f_caption = BATCH_FILE_CAPTION.format(file_name='' if title is None else title,
                                                          file_size='' if size is None else size,
                                                          file_caption='' if f_caption is None else f_caption)
                except Exception as e:
                    logger.exception(e)
                    f_caption = f_caption
            if f_caption is None:
                f_caption = f"{title}"
            try:
                await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                )
            except FloodWait as e:
                await asyncio.sleep(e.x)
                logger.warning(f"Floodwait of {e.x} sec.")
                await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                )
            except Exception as e:
                logger.warning(e, exc_info=True)
                continue
        await sts.delete()
        return

    # --------------------- BATCH (DSTORE) ---------------------
    elif data.split("-", 1)[0] == "DSTORE":
        sts = await message.reply("🔄 **ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...**")
        b_string = data.split("-", 1)[1]
        decoded = (base64.urlsafe_b64decode(b_string + "=" * (-len(b_string) % 4))).decode("ascii")
        try:
            f_msg_id, l_msg_id, f_chat_id, protect = decoded.split("_", 3)
        except:
            f_msg_id, l_msg_id, f_chat_id = decoded.split("_", 2)
            protect = "/pbatch" if PROTECT_CONTENT else "batch"
        diff = int(l_msg_id) - int(f_msg_id)
        async for msg in client.iter_messages(int(f_chat_id), int(l_msg_id), int(f_msg_id)):
            if msg.media:
                media = getattr(msg, msg.media)
                if BATCH_FILE_CAPTION:
                    try:
                        f_caption = BATCH_FILE_CAPTION.format(file_name=getattr(media, 'file_name', ''),
                                                              file_size=getattr(media, 'file_size', ''),
                                                              file_caption=getattr(msg, 'caption', ''))
                    except Exception as e:
                        logger.exception(e)
                        f_caption = getattr(msg, 'caption', '')
                else:
                    media = getattr(msg, msg.media)
                    file_name = getattr(media, 'file_name', '')
                    f_caption = getattr(msg, 'caption', file_name)
                try:
                    await msg.copy(message.chat.id, caption=f_caption, protect_content=True if protect == "/pbatch" else False)
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await msg.copy(message.chat.id, caption=f_caption, protect_content=True if protect == "/pbatch" else False)
                except Exception as e:
                    logger.exception(e)
                    continue
            elif msg.empty:
                continue
            else:
                try:
                    await msg.copy(message.chat.id, protect_content=True if protect == "/pbatch" else False)
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await msg.copy(message.chat.id, protect_content=True if protect == "/pbatch" else False)
                except Exception as e:
                    logger.exception(e)
                    continue
        await sts.delete()
        return

    # --------------------- SINGLE FILE ---------------------
    files_ = await cached_get_file_details(file_id)
    if not files_:
        pre, file_id = ((base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")).split("_", 1)
        try:
            await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_id,
                protect_content=True if pre == 'filep' else False,
            )
            await message.reply_text("✅ **ғɪʟᴇ sᴇɴᴛ sᴜᴄᴄᴇssғᴜʟʟʏ !**")
            return
        except:
            pass
        return await message.reply('❌ **ɴᴏ sᴜᴄʜ ғɪʟᴇ ᴇxɪsᴛ.**')

    files = files_[0]
    title = files.file_name
    size = get_size(files.file_size)
    f_caption = files.caption
    if CUSTOM_FILE_CAPTION:
        try:
            f_caption = CUSTOM_FILE_CAPTION.format(file_name='' if title is None else title,
                                                   file_size='' if size is None else size,
                                                   file_caption='' if f_caption is None else f_caption)
        except Exception as e:
            logger.exception(e)
            f_caption = f_caption
    if f_caption is None:
        f_caption = f"{files.file_name}"

    await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        protect_content=True if pre == 'filep' else False,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ', url=CHNL_LNK)]]
        )
    )
    await message.reply_text("✅ **ғɪʟᴇ sᴇɴᴛ sᴜᴄᴄᴇssғᴜʟʟʏ !**")
    return

# --------------------- CHANNEL INFO ---------------------
@Client.on_message(filters.command('channel') & filters.user(ADMINS))
async def channel_info(bot, message):
    if isinstance(CHANNELS, (int, str)):
        channels = [CHANNELS]
    elif isinstance(CHANNELS, list):
        channels = CHANNELS
    else:
        raise ValueError("Uɴᴇxᴘᴇᴄᴛᴇᴅ ᴛʏᴘᴇ ᴏғ CHANNELS")

    text = '📑 **Iɴᴅᴇxᴇᴅ ᴄʜᴀɴɴᴇʟs/ɢʀᴏᴜᴘs**\n'
    for channel in channels:
        chat = await bot.get_chat(channel)
        if chat.username:
            text += '\n@' + chat.username
        else:
            text += '\n' + chat.title or chat.first_name
    text += f'\n\n**Total:** {len(CHANNELS)}'

    if len(text) < 4096:
        await message.reply(text)
    else:
        file = 'Indexed channels.txt'
        with open(file, 'w') as f:
            f.write(text)
        await message.reply_document(file)
        os.remove(file)

# --------------------- LOGS ---------------------
@Client.on_message(filters.command('logs') & filters.user(ADMINS))
async def log_file(bot, message):
    try:
        await message.reply_document('Logs.txt')
    except Exception as e:
        await message.reply(str(e))

# --------------------- DELETE SINGLE FILE ---------------------
@Client.on_message(filters.command('delete') & filters.user(ADMINS))
async def delete(bot, message):
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("🔄 **ᴘʀᴏᴄᴇssɪɴɢ...**", quote=True)
    else:
        await message.reply('❌ **ʀᴇᴘʟʏ ᴛᴏ ᴀ ғɪʟᴇ ᴡɪᴛʜ /delete**', quote=True)
        return

    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit('❌ **ᴜɴsᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇ ғᴏʀᴍᴀᴛ**')
        return

    file_id, file_ref = unpack_new_file_id(media.file_id)
    if await Media.count_documents({'file_id': file_id}):
        result = await Media.collection.delete_one({'_id': file_id})
    else:
        result = await Media2.collection.delete_one({'_id': file_id})

    if result.deleted_count:
        await msg.edit('✅ **ғɪʟᴇ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ**')
        return

    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    for collection in (Media, Media2):
        result = await collection.collection.delete_many({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
        })
        if result.deleted_count:
            await msg.edit('✅ **ғɪʟᴇ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ**')
            return

    # fallback for old indexed files
    result = await Media.collection.delete_many({
        'file_name': media.file_name,
        'file_size': media.file_size,
        'mime_type': media.mime_type
    })
    if result.deleted_count:
        await msg.edit('✅ **ғɪʟᴇ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ**')
        return

    result = await Media2.collection.delete_many({
        'file_name': media.file_name,
        'file_size': media.file_size,
        'mime_type': media.mime_type
    })
    if result.deleted_count:
        await msg.edit('✅ **ғɪʟᴇ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ**')
        return

    await msg.edit('❌ **ғɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ**')

# --------------------- DELETE ALL INDEXED FILES ---------------------
@Client.on_message(filters.command('deleteall') & filters.user(ADMINS))
async def delete_all_index(bot, message):
    await message.reply_text(
        '⚠️ **ᴛʜɪs ᴡɪʟʟ ᴅᴇʟᴇᴛᴇ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ғɪʟᴇs. ᴄᴏɴᴛɪɴᴜᴇ ?**',
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Yᴇs", callback_data="autofilter_delete"),
                InlineKeyboardButton("Cᴀɴᴄᴇʟ", callback_data="close_data")
            ]]
        ),
        quote=True,
    )

@Client.on_callback_query(filters.regex(r'^autofilter_delete'))
async def delete_all_index_confirm(bot, message):
    await Media.collection.drop()
    await Media2.collection.drop()
    await message.answer("✅ ᴀʟʟ ғɪʟᴇs ᴅᴇʟᴇᴛᴇᴅ")
    await message.message.edit('✅ **sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ғɪʟᴇs.**')

# --------------------- GROUP SETTINGS ---------------------
@Client.on_message(filters.command('settings'))
async def settings(client, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(f"⚠️ ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ. ᴜsᴇ /connect {message.chat.id} ɪɴ ᴘᴍ")
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        grpid = await active_connection(str(userid))
        if grpid is not None:
            grp_id = grpid
            try:
                chat = await client.get_chat(grpid)
                title = chat.title
            except:
                await message.reply_text("❌ ᴍᴀᴋᴇ sᴜʀᴇ ɪ'ᴍ ᴘʀᴇsᴇɴᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ !", quote=True)
                return
        else:
            await message.reply_text("❌ ɪ'ᴍ ɴᴏᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴛᴏ ᴀɴʏ ɢʀᴏᴜᴘs !", quote=True)
            return
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grp_id = message.chat.id
        title = message.chat.title
    else:
        return

    st = await client.get_chat_member(grp_id, userid)
    if st.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] and str(userid) not in ADMINS:
        return

    settings = await get_settings(grp_id)
    try:
        if settings['max_btn']:
            settings = await get_settings(grp_id)
    except KeyError:
        await save_group_settings(grp_id, 'max_btn', False)
        settings = await get_settings(grp_id)

    buttons = [
        [
            InlineKeyboardButton('Fɪʟᴛᴇʀ Bᴜᴛᴛᴏɴ', callback_data=f'setgs#button#{settings["button"]}#{grp_id}'),
            InlineKeyboardButton('Sɪɴɢʟᴇ' if settings["button"] else 'Dᴏᴜʙʟᴇ', callback_data=f'setgs#button#{settings["button"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Fɪʟᴇ Sᴇɴᴅ Mᴏᴅᴇ', callback_data=f'setgs#botpm#{settings["botpm"]}#{grp_id}'),
            InlineKeyboardButton('Mᴀɴᴜᴀʟ Sᴛᴀʀᴛ' if settings["botpm"] else 'Aᴜᴛᴏ Sᴇɴᴅ', callback_data=f'setgs#botpm#{settings["botpm"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Pʀᴏᴛᴇᴄᴛ Cᴏɴᴛᴇɴᴛ', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}'),
            InlineKeyboardButton('✔ Oɴ' if settings["file_secure"] else '✘ Oғғ', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Iᴍᴅʙ', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'),
            InlineKeyboardButton('✔ Oɴ' if settings["imdb"] else '✘ Oғғ', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Sᴘᴇʟʟ Cʜᴇᴄᴋ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'),
            InlineKeyboardButton('✔ Oɴ' if settings["spell_check"] else '✘ Oғғ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Wᴇʟᴄᴏᴍᴇ Msɢ', callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}'),
            InlineKeyboardButton('✔ Oɴ' if settings["welcome"] else '✘ Oғғ', callback_data=f'setgs#welcome#{settings["welcome"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Aᴜᴛᴏ-Dᴇʟᴇᴛᴇ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'),
            InlineKeyboardButton('10 Mɪɴs' if settings["auto_delete"] else '✘ Oғғ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Aᴜᴛᴏ-Fɪʟᴛᴇʀ', callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}'),
            InlineKeyboardButton('✔ Oɴ' if settings["auto_ffilter"] else '✘ Oғғ', callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}'),
        ],
        [
            InlineKeyboardButton('Mᴀx Bᴜᴛᴛᴏɴs', callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}'),
            InlineKeyboardButton('10' if settings["max_btn"] else f'{MAX_B_TN}', callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}'),
        ],
    ]

    btn = [[
        InlineKeyboardButton("Oᴘᴇɴ Hᴇʀᴇ ↓", callback_data=f"opnsetgrp#{grp_id}"),
        InlineKeyboardButton("Oᴘᴇɴ Iɴ PM ⇲", callback_data=f"opnsetpm#{grp_id}")
    ]]

    reply_markup = InlineKeyboardMarkup(buttons)
    if chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await message.reply_text(
            text="<b>Dᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏᴘᴇɴ sᴇᴛᴛɪɴɢs ʜᴇʀᴇ ?</b>",
            reply_markup=InlineKeyboardMarkup(btn),
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
            reply_to_message_id=message.id
        )
    else:
        await message.reply_text(
            text=f"<b>Cʜᴀɴɢᴇ Yᴏᴜʀ Sᴇᴛᴛɪɴɢs Fᴏʀ {title} As Yᴏᴜʀ Wɪsʜ ⚙</b>",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
            reply_to_message_id=message.id
        )

@Client.on_message(filters.command('set_template'))
async def save_template(client, message):
    sts = await message.reply("🔄 ᴄʜᴇᴄᴋɪɴɢ ᴛᴇᴍᴘʟᴀᴛᴇ...")
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(f"⚠️ ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ. ᴜsᴇ /connect {message.chat.id} ɪɴ ᴘᴍ")
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        grpid = await active_connection(str(userid))
        if grpid is not None:
            grp_id = grpid
            try:
                chat = await client.get_chat(grpid)
                title = chat.title
            except:
                await message.reply_text("❌ ᴍᴀᴋᴇ sᴜʀᴇ ɪ'ᴍ ᴘʀᴇsᴇɴᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ !", quote=True)
                return
        else:
            await message.reply_text("❌ ɪ'ᴍ ɴᴏᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴛᴏ ᴀɴʏ ɢʀᴏᴜᴘs !", quote=True)
            return
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grp_id = message.chat.id
        title = message.chat.title
    else:
        return

    st = await client.get_chat_member(grp_id, userid)
    if st.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] and str(userid) not in ADMINS:
        return

    if len(message.command) < 2:
        return await sts.edit("❌ **ɴᴏ ɪɴᴘᴜᴛ !!**")
    template = message.text.split(" ", 1)[1]
    await save_group_settings(grp_id, 'template', template)
    await sts.edit(f"✅ **sᴜᴄᴄᴇssғᴜʟʟʏ ᴄʜᴀɴɢᴇᴅ ᴛᴇᴍᴘʟᴀᴛᴇ ғᴏʀ {title} ᴛᴏ:**\n\n{template}")

# --------------------- REQUEST HANDLER ---------------------
@Client.on_message((filters.command(["request", "Request"]) | filters.regex("#request") | filters.regex("#Request")) & filters.group)
async def requests(bot, message):
    if REQST_CHANNEL is None or SUPPORT_CHAT_ID is None:
        return
    if message.reply_to_message and SUPPORT_CHAT_ID == message.chat.id:
        chat_id = message.chat.id
        reporter = str(message.from_user.id)
        mention = message.from_user.mention
        success = True
        content = message.reply_to_message.text
        try:
            if REQST_CHANNEL is not None:
                btn = [[
                    InlineKeyboardButton('Vɪᴇᴡ Rᴇᴏ̨ᴜᴇsᴛ', url=f"{message.reply_to_message.link}"),
                    InlineKeyboardButton('Sʜᴏᴡ Oᴘᴛɪᴏɴs', callback_data=f'show_option#{reporter}')
                ]]
                await bot.send_message(chat_id=REQST_CHANNEL, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                success = True
            elif len(content) >= 3:
                for admin in ADMINS:
                    btn = [[
                        InlineKeyboardButton('Vɪᴇᴡ Rᴇᴏ̨ᴜᴇsᴛ', url=f"{message.reply_to_message.link}"),
                        InlineKeyboardButton('Sʜᴏᴡ Oᴘᴛɪᴏɴs', callback_data=f'show_option#{reporter}')
                    ]]
                    await bot.send_message(chat_id=admin, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                    success = True
            else:
                if len(content) < 3:
                    await message.reply_text("<b>⚠️ ʏᴏᴜ ᴍᴜsᴛ ᴛʏᴘᴇ ᴀᴛ ʟᴇᴀsᴛ 3 ᴄʜᴀʀᴀᴄᴛᴇʀs.</b>")
            if len(content) < 3:
                success = False
        except Exception as e:
            await message.reply_text(f"Error: {e}")
            pass

    elif SUPPORT_CHAT_ID == message.chat.id:
        reporter = str(message.from_user.id)
        mention = message.from_user.mention
        content = message.text
        keywords = ["#request", "/request", "#Request", "/Request"]
        for keyword in keywords:
            if keyword in content:
                content = content.replace(keyword, "")
        try:
            if REQST_CHANNEL is not None and len(content) >= 3:
                btn = [[
                    InlineKeyboardButton('Vɪᴇᴡ Rᴇᴏ̨ᴜᴇsᴛ', url=f"{message.link}"),
                    InlineKeyboardButton('Sʜᴏᴡ Oᴘᴛɪᴏɴs', callback_data=f'show_option#{reporter}')
                ]]
                await bot.send_message(chat_id=REQST_CHANNEL, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                success = True
            elif len(content) >= 3:
                for admin in ADMINS:
                    btn = [[
                        InlineKeyboardButton('Vɪᴇᴡ Rᴇᴏ̨ᴜᴇsᴛ', url=f"{message.link}"),
                        InlineKeyboardButton('Sʜᴏᴡ Oᴘᴛɪᴏɴs', callback_data=f'show_option#{reporter}')
                    ]]
                    await bot.send_message(chat_id=admin, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                    success = True
            else:
                if len(content) < 3:
                    await message.reply_text("<b>⚠️ ʏᴏᴜ ᴍᴜsᴛ ᴛʏᴘᴇ ᴀᴛ ʟᴇᴀsᴛ 3 ᴄʜᴀʀᴀᴄᴛᴇʀs.</b>")
            if len(content) < 3:
                success = False
        except Exception as e:
            await message.reply_text(f"Error: {e}")
            pass
    else:
        success = False

    if success:
        btn = [[InlineKeyboardButton('Vɪᴇᴡ Rᴇᴏ̨ᴜᴇsᴛ', url=f"{reported_post.link}")]]
        await message.reply_text("<b>✅ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ʜᴀs ʙᴇᴇɴ ᴀᴅᴅᴇᴅ. ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ.</b>", reply_markup=InlineKeyboardMarkup(btn))

# --------------------- SEND MESSAGE TO USER ---------------------
@Client.on_message(filters.command("send") & filters.user(ADMINS))
async def send_msg(bot, message):
    if message.reply_to_message:
        target_id = message.text.split(" ", 1)[1]
        out = "Usᴇʀs Sᴀᴠᴇᴅ Iɴ DB Aʀᴇ:\n\n"
        success = False
        try:
            user = await bot.get_users(target_id)
            users = await db.get_all_users()
            async for usr in users:
                out += f"{usr['id']}\n"
            if str(user.id) in out:
                await message.reply_to_message.copy(int(user.id))
                success = True
            else:
                success = False
            if success:
                await message.reply_text(f"✅ ᴍᴇssᴀɢᴇ sᴇɴᴛ ᴛᴏ {user.mention}.")
            else:
                await message.reply_text("❌ ᴜsᴇʀ ʜᴀs ɴᴏᴛ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ ʏᴇᴛ.")
        except Exception as e:
            await message.reply_text(f"Error: {e}")
    else:
        await message.reply_text("⚠️ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ /send ᴜsᴇʀɪᴅ")

# --------------------- DELETE FILES BY KEYWORD ---------------------
@Client.on_message(filters.command("deletefiles") & filters.user(ADMINS))
async def deletemultiplefiles(bot, message):
    if message.chat.type != enums.ChatType.PRIVATE:
        return await message.reply_text("❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋs ᴏɴʟʏ ɪɴ ᴘᴍ.")
    try:
        keyword = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text("❌ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴋᴇʏᴡᴏʀᴅ ᴀʟᴏɴɢ ᴡɪᴛʜ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅ.")
    btn = [[
        InlineKeyboardButton("Yᴇs, Cᴏɴᴛɪɴᴜᴇ !", callback_data=f"killfilesdq#{keyword}")
    ], [
        InlineKeyboardButton("Nᴏ, Aʙᴏʀᴛ !", callback_data="close_data")
    ]]
    await message.reply_text(
        text="⚠️ **ᴀʀᴇ ʏᴏᴜ sᴜʀᴇ? ᴛʜɪs ᴀᴄᴛɪᴏɴ ɪs ɪʀʀᴇᴠᴇʀsɪʙʟᴇ.**",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )
