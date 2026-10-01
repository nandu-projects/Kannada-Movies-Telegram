import logging
import logging.config
import aiohttp 
import asyncio

# Get logging configurations
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)

from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from database.ia_filterdb import *
from database.users_chats_db import db
from info import *
from utils import temp
from typing import Union, Optional, AsyncGenerator
from pyrogram import types
from Script import script 
from datetime import date, datetime 
import pytz
from plugins.webcode import bot_run
from os import environ
from aiohttp import web as webserver
from sample_info import tempDict

async def db_monitor():
    while True:
        try:
            free_mb = await auto_switch_db()

            logging.info(
                f"📊 ᴅʙ ᴍᴏɴɪᴛᴏʀ | "
                f"ᴀᴄᴛɪᴠᴇ: {'ᴘʀɪᴍᴀʀʏ' if tempDict.get('indexDB') == DATABASE_URI else 'ꜱᴇᴄᴏɴᴅᴀʀʏ'} | "
                f"ꜰʀᴇᴇ: {free_mb} ᴍʙ"
            )

        except Exception as e:
            logging.error(f"❌ ᴅʙ ᴍᴏɴɪᴛᴏʀ ᴇʀʀᴏʀ: {e}")

        await asyncio.sleep(300)


async def keep_alive():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await session.get("https://handicapped-audra-filterbotkn-27aa5fb6.koyeb.app/")  # Uses the imported URL from info.py
                logging.info("Working..!!")
            except Exception as e:
                logging.error(f"Error Occurred : {e}")
            await asyncio.sleep(10)

async def keepalive():
    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                async with session.get(
                    "https://handicapped-audra-filterbotkn-27aa5fb6.koyeb.app/"
                ) as response:
                    logging.info(
                        f"❤️ Keep Alive: {response.status}"
                    )

            except Exception as e:
                logging.error(f"❌ Keep Alive Error: {e}")

            await asyncio.sleep(60)  # 1 minute

class Bot(Client):

    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=500,
            plugins={"root": "plugins"},
            sleep_threshold=60,
        )

    async def start(self):
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats
        await super().start()
        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.username = '@' + me.username
        logging.info(f"{me.first_name} with for Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
        logging.info(LOG_STR)
        tz = pytz.timezone('Asia/Kolkata')
        today = date.today()
        now = datetime.now(tz)
        time = now.strftime("%H:%M:%S %p")
        await self.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_TXT.format(today, time))
        await self.send_message(1404622369, text="ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ 🤖✨")
        await asyncio.gather(*(self.send_message(admin, text="ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ ✨") for admin in ADMINS))
        
        asyncio.create_task(keep_alive())
        asyncio.create_task(db_monitor())
        
        for admin in ADMINS:
            await self.send_message(admin, text="ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ.✨")
        asyncio.create_task(keepalive())
        
        client = webserver.AppRunner(await bot_run())
        await client.setup()
        bind_address = "0.0.0.0"
        await webserver.TCPSite(client, bind_address, 8080).start()

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot stopped. Bye.")

    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
    ) -> Optional[AsyncGenerator["types.Message", None]]:
        current = offset
        while current < limit:
            batch_size = min(200, limit - current)
            ids = list(range(current, current + batch_size))
            messages = await self.get_messages(chat_id, ids)
            for msg in messages:
                yield msg
            current += len(messages)
            
Bot().run()
