from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram import Client, filters, enums

@Client.on_message(filters.command(['help']))
async def ai_generate_private(client, message):
    await message.reply_text(
        text="""<b><blockquote>❗️How to Search Movies Here❓
▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
1. Just Send Movie Name and Movie Released Year Correctly.
<blockquote>(Check Google for Correct Movie Spelling and Movie Released Year)</blockquote>

Examples: -
Oppam 2016
Baahubali 2015 1080p
<blockquote>(For Getting only 1080p Quality Files)</blockquote>
▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
Baahubali 2015 Malayalam
Baahubali 2015 Tamil
<blockquote>(For Dubbed Movie Files)</blockquote>
▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬
❗️On Android, Better Use VLC Media Player For Watch Movie's.
▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬</b>"""
    )
