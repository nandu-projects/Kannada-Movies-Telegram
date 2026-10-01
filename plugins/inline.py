import logging
from pyrogram import Client, emoji, filters
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedDocument, InlineQuery
from database.ia_filterdb import get_search_results
from utils import is_subscribed, get_size, temp
from info import *

logger = logging.getLogger(__name__)
cache_time = 0 if AUTH_USERS or AUTH_CHANNEL else CACHE_TIME

async def inline_users(query: InlineQuery):
    """✅ ᴜꜱᴇʀ ᴀᴜᴛʜᴇɴᴛɪᴄᴀᴛɪᴏɴ ᴄʜᴇᴄᴋ"""
    logger.info(f"🔍 ɪɴʟɪɴᴇ Qᴜᴇʀʏ ᴄʜᴇᴄᴋ ꜰᴏʀ ᴜꜱᴇʀ {query.from_user.id if query.from_user else 'ᴜɴᴋɴᴏᴡɴ'}")
    
    if AUTH_USERS:
        if query.from_user and query.from_user.id in AUTH_USERS:
            logger.info("✅ ᴜꜱᴇʀ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ ᴠɪᴀ ᴀᴜᴛʜ_ᴜꜱᴇʀꜱ")
            return True
        else:
            logger.warning("❌ ᴜꜱᴇʀ ɴᴏᴛ ɪɴ ᴀᴜᴛʜ_ᴜꜱᴇʀꜱ")
            return False
            
    if query.from_user and query.from_user.id not in temp.BANNED_USERS:
        logger.info("✅ ᴜꜱᴇʀ ɴᴏᴛ ʙᴀɴɴᴇᴅ")
        return True
        
    logger.warning("🚫 ᴜꜱᴇʀ ʙᴀɴɴᴇᴅ ᴏʀ ɪɴᴠᴀʟɪᴅ")
    return False

@Client.on_inline_query()
async def answer(bot, query):
    """🎯 ᴍᴀɪɴ ɪɴʟɪɴᴇ Qᴜᴇʀʏ ʜᴀɴᴅʟᴇʀ"""
    logger.info(f"🌐 ʜᴀɴᴅʟɪɴɢ ɪɴʟɪɴᴇ Qᴜᴇʀʏ: '{query.query}' ꜰʀᴏᴍ ᴜꜱᴇʀ {query.from_user.id if query.from_user else 'ᴜɴᴋɴᴏᴡɴ'}")
    
    # 🔐 ᴀᴜᴛʜᴇɴᴛɪᴄᴀᴛɪᴏɴ ᴄʜᴇᴄᴋ
    if not await inline_users(query):
        logger.warning("🚫 ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ ɪɴʟɪɴᴇ Qᴜᴇʀʏ - ᴇᴍᴘᴛʏ ʀᴇꜱᴘᴏɴꜱᴇ")
        await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text='⚡ ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ',
            switch_pm_parameter="hehe"
        )
        return

    # 📢 ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ᴄʜᴇᴄᴋ
    logger.info("📋 ᴄʜᴇᴄᴋɪɴɢ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜱᴛᴀᴛᴜꜱ...")
    invite_links = await is_subscribed(bot, query=query)
    
    if AUTH_CHANNEL and len(invite_links) >= 1:
        logger.warning("⚠️ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ʀᴇQᴜɪʀᴇᴅ - ᴇᴍᴘᴛʏ ʀᴇꜱᴘᴏɴꜱᴇ")
        await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text='📢 ᴘʟᴇᴀꜱᴇ ꜱᴜʙꜱᴄʀɪʙᴇ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ʙᴏᴛ',
            switch_pm_parameter="subscribe"
        )
        return

    results = []
    logger.info(f"🔍 ᴘᴀʀꜱɪɴɢ Qᴜᴇʀʏ: '{query.query}'")
    
    # 🔄 ᴘᴀʀꜱᴇ Qᴜᴇʀʏ ᴡɪᴛʜ ꜰɪʟᴇ ᴛʏᴘᴇ
    if '|' in query.query:
        string, file_type = query.query.split('|', maxsplit=1)
        string = string.strip()
        file_type = file_type.strip().lower()
        logger.info(f"📂 ᴘᴀʀꜱᴇᴅ: ꜱᴛʀɪɴɢ='{string}', ꜰɪʟᴇ_ᴛʏᴘᴇ='{file_type}'")
    else:
        string = query.query.strip()
        file_type = None
        logger.info(f"📂 ᴘᴀʀꜱᴇᴅ: ꜱᴛʀɪɴɢ='{string}', ꜰɪʟᴇ_ᴛʏᴘᴇ=ɴᴏɴᴇ")

    offset = int(query.offset or 0)
    logger.info(f"📄 ᴏꜰꜰꜱᴇᴛ: {offset}")
    reply_markup = get_reply_markup(query=string)
    logger.info("🔗 ɢᴇɴᴇʀᴀᴛᴇᴅ ʀᴇᴘʟʏ ᴍᴀʀᴋᴜᴘ")

    # 🗄️ ꜰᴇᴛᴄʜ ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛꜱ
    logger.info(f"🗄️ ꜰᴇᴛᴄʜɪɴɢ ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ '{string}' (ᴛʏᴘᴇ: {file_type}, ᴏꜰꜰꜱᴇᴛ: {offset})")
    files, next_offset, total = await get_search_results(
        query.from_user.id,
        string,
        file_type=file_type,
        max_results=10,
        offset=offset
    )
    logger.info(f"📊 ꜱᴇᴀʀᴄʜ ʀᴇꜱᴜʟᴛꜱ: {len(files)} ꜰɪʟᴇꜱ, ɴᴇxᴛ_ᴏꜰꜰꜱᴇᴛ: {next_offset}, ᴛᴏᴛᴀʟ: {total}")

    # 📁 ᴘʀᴏᴄᴇꜱꜱ ᴇᴀᴄʜ ꜰɪʟᴇ
    for file in files:
        logger.info(f"📁 ᴘʀᴏᴄᴇꜱꜱɪɴɢ ꜰɪʟᴇ: {file.file_name}")
        title = file.file_name
        size = get_size(file.file_size)
        f_caption = file.caption
        
        # ✏️ ᴄᴜꜱᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴ ʜᴀɴᴅʟɪɴɢ
        if CUSTOM_FILE_CAPTION:
            try:
                f_caption = CUSTOM_FILE_CAPTION.format(
                    file_name='' if title is None else title,
                    file_size='' if size is None else size,
                    file_caption='' if f_caption is None else f_caption
                )
                logger.info("✏️ ᴄᴜꜱᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴ ᴀᴘᴘʟɪᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ")
            except Exception as e:
                logger.exception(f"❌ ᴄᴜꜱᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴ ᴇʀʀᴏʀ: {e}")
                f_caption = f_caption if f_caption else f"{file.file_name}"
        
        if f_caption is None:
            f_caption = f"{file.file_name}"
            
        # 🔧 ꜰɪxᴇᴅ: ᴜꜱᴇ ᴛʜᴇ ꜰɪʟᴇ_ɪᴅ ᴅɪʀᴇᴄᴛʟʏ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀꜱᴇ
        # ᴛʜɪꜱ ꜰɪxᴇꜱ ᴛʜᴇ ᴍᴅ5_ᴄʜᴇᴄᴋꜱᴜᴍ_ɪɴᴠᴀʟɪᴅ ᴇʀʀᴏʀ
        results.append(
            InlineQueryResultCachedDocument(
                title=file.file_name,
                document_file_id=file.file_id,  # ᴜꜱᴇ ꜱᴛᴏʀᴇᴅ ꜰɪʟᴇ_ɪᴅ
                caption=f_caption,
                description=f'📦 ꜱɪᴢᴇ: {get_size(file.file_size)}\n🎬 ᴛʏᴘᴇ: {file.file_type}',
                reply_markup=reply_markup
            )
        )
        logger.info(f"✅ ᴀᴅᴅᴇᴅ ʀᴇꜱᴜʟᴛ ꜰᴏʀ {file.file_name}")

    # 📤 ꜱᴇɴᴅ ʀᴇꜱᴘᴏɴꜱᴇ
    if results:
        switch_pm_text = f"📁 ʀᴇꜱᴜʟᴛꜱ - {total}"
        if string:
            switch_pm_text += f" ꜰᴏʀ {string}"
            
        logger.info(f"📤 ᴀɴꜱᴡᴇʀɪɴɢ ᴡɪᴛʜ {len(results)} ʀᴇꜱᴜʟᴛꜱ | ꜱᴡɪᴛᴄʜ ᴘᴍ: {switch_pm_text}")
        
        try:
            await query.answer(
                results=results,
                is_personal=True,
                cache_time=cache_time,
                switch_pm_text=switch_pm_text,
                switch_pm_parameter="start",
                next_offset=str(next_offset) if next_offset else ""
            )
            logger.info("✅ ɪɴʟɪɴᴇ Qᴜᴇʀʏ ᴀɴꜱᴡᴇʀᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ")
            
        except QueryIdInvalid:
            logger.warning("⚠️ Qᴜᴇʀʏ ɪᴅ ɪɴᴠᴀʟɪᴅ - ꜱᴋɪᴘᴘɪɴɢ")
            
        except Exception as e:
            logger.exception(f"❌ ᴇʀʀᴏʀ ɪɴ Qᴜᴇʀʏ.ᴀɴꜱᴡᴇʀ: {e}")
            # ꜰᴀʟʟʙᴀᴄᴋ ᴡɪᴛʜ ᴇʀʀᴏʀ ɪɴꜰᴏ
            try:
                await query.answer(
                    results=[],
                    cache_time=0,
                    switch_pm_text=f'❌ ᴇʀʀᴏʀ: {str(e)[:40]}...',
                    switch_pm_parameter="error"
                )
            except:
                pass
    else:
        switch_pm_text = f'❌ ɴᴏ ʀᴇꜱᴜʟᴛꜱ'
        if string:
            switch_pm_text += f' ꜰᴏʀ "{string}"'
            
        logger.info(f"📭 ɴᴏ ʀᴇꜱᴜʟᴛꜱ - ᴀɴꜱᴡᴇʀɪɴɢ ᴇᴍᴘᴛʏ ᴡɪᴛʜ: {switch_pm_text}")
        
        await query.answer(
            results=[],
            is_personal=True,
            cache_time=cache_time,
            switch_pm_text=switch_pm_text,
            switch_pm_parameter="okay"
        )


def get_reply_markup(query):
    """🔘 ɢᴇɴᴇʀᴀᴛᴇ ʀᴇᴘʟʏ ᴍᴀʀᴋᴜᴘ ꜰᴏʀ ɪɴʟɪɴᴇ ʀᴇꜱᴜʟᴛꜱ"""
    buttons = [
        [
            InlineKeyboardButton('🔄 ꜱᴇᴀʀᴄʜ ᴀɢᴀɪɴ', switch_inline_query_current_chat=query)
        ],
        [
            InlineKeyboardButton('🔍 ᴀᴅᴠᴀɴᴄᴇᴅ ꜱᴇᴀʀᴄʜ', switch_inline_query_current_chat='')
        ]
    ]
    return InlineKeyboardMarkup(buttons)
