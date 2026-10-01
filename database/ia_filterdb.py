import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import *
from utils import get_settings, save_group_settings
from sample_info import tempDict 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 🗄️ Basic Variables
saveMedia = None
_cache = {}  # 🚀 In-memory cache for speed

# 📦 Primary Database
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name',)
        collection_name = COLLECTION_NAME

# 📦 Secondary Database  
client2 = AsyncIOMotorClient(SECONDDB_URI)
db2 = client2[DATABASE_NAME]
instance2 = Instance.from_db(db2)

@instance2.register
class Media2(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name',)
        collection_name = COLLECTION_NAME

async def choose_mediaDB():
    """⚡ Smart Dual-DB Load Balancer"""
    global saveMedia
    if tempDict.get('indexDB') == DATABASE_URI:
        logger.info("🎯 ᴀᴄᴛɪᴠᴇ ᴅᴀᴛᴀʙᴀꜱᴇ: ᴘʀɪᴍᴀʀʏ ᴅʙ (ᴍᴇᴅɪᴀ)")
        saveMedia = Media
    else:
        logger.info("🎯 ᴀᴄᴛɪᴠᴇ ᴅᴀᴛᴀʙᴀꜱᴇ: ꜱᴇᴄᴏɴᴅᴀʀʏ ᴅʙ (ᴍᴇᴅɪᴀ2)")
        saveMedia = Media2

async def save_file(media):
    """💾 ꜱᴀᴠᴇ ꜰɪʟᴇ ᴛᴏ ᴅᴀᴛᴀʙᴀꜱᴇ"""
    await auto_switch_db()
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    
    try:
        if await Media.count_documents({'file_id': file_id}, limit=1):
            logger.warning(f"⚠️ {getattr(media, 'file_name', 'ɴᴏ_ꜰɪʟᴇ')} ᴀʟʀᴇᴀᴅʏ ᴇxɪꜱᴛꜱ ɪɴ ᴘʀɪᴍᴀʀʏ ᴅʙ!")
            return False, 0
            
        file = saveMedia(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
    except ValidationError:
        logger.exception('❌ ᴇʀʀᴏʀ ꜱᴀᴠɪɴɢ ꜰɪʟᴇ ᴛᴏ ᴅᴀᴛᴀʙᴀꜱᴇ')
        return False, 2
    else:
        try:
            await file.commit()
            # 🚀 Clear cache for this query pattern
            _cache.clear()
            logger.info(f"✅ {getattr(media, 'file_name', 'ɴᴏ_ꜰɪʟᴇ')} ꜱᴀᴠᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ")
            return True, 1
        except DuplicateKeyError:  
            logger.warning(f"⚠️ {getattr(media, 'file_name', 'ɴᴏ_ꜰɪʟᴇ')} ᴀʟʀᴇᴀᴅʏ ᴇxɪꜱᴛꜱ")
            return False, 0

async def get_search_results(query, file_type=None, max_results=10, offset=0, filter=False):
    # 🔍 ᴄᴀᴄʜᴇ ᴋᴇʏ ɢᴇɴᴇʀᴀᴛɪᴏɴ
    cache_key = f"{query}:{file_type}:{max_results}:{offset}"
    if cache_key in _cache:
        logger.info(f"⚡ ᴄᴀᴄʜᴇ ʜɪᴛ ꜰᴏʀ: {query}")
        return _cache[cache_key]
    
    query = query.strip()
    
    # 📝 ʀᴇɢᴇx ᴘᴀᴛᴛᴇʀɴ
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + re.escape(query) + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = re.escape(query).replace(r'\ ', r'.*[\s\.\+\-_()]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []

    # 🎯 ꜰɪʟᴛᴇʀ ᴄᴏɴꜱᴛʀᴜᴄᴛɪᴏɴ
    if USE_CAPTION_FILTER:
        filter_query = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter_query = {'file_name': regex}

    if file_type:
        filter_query['file_type'] = file_type

    # 📊 ᴄᴏᴜɴᴛ ᴛᴏᴛᴀʟ ʀᴇꜱᴜʟᴛꜱ (ᴘᴀʀᴀʟʟᴇʟ)
    count1 = await Media.count_documents(filter_query)
    count2 = await Media2.count_documents(filter_query)
    total_results = count1 + count2
    
    # 🔧 ᴇɴꜱᴜʀᴇ ᴇᴠᴇɴ ᴍᴀx_ʀᴇꜱᴜʟᴛꜱ
    if max_results % 2 != 0:
        logger.info(f"📊 ᴀᴅᴊᴜꜱᴛɪɴɢ ᴍᴀx_ʀᴇꜱᴜʟᴛꜱ ꜰʀᴏᴍ {max_results} ᴛᴏ {max_results+1}")
        max_results += 1

    # 🚀 ᴘᴀʀᴀʟʟᴇʟ ᴅᴀᴛᴀʙᴀꜱᴇ Qᴜᴇʀɪᴇꜱ
    cursor = Media.find(filter_query).sort('$natural', -1)
    cursor2 = Media2.find(filter_query).sort('$natural', -1)
    
    cursor2.skip(offset).limit(max_results)
    fileList2 = await cursor2.to_list(length=max_results)
    
    # 📦 ᴍᴇʀɢᴇ ʀᴇꜱᴜʟᴛꜱ
    if len(fileList2) < max_results:
        next_offset = offset + len(fileList2)
        remaining = max_results - len(fileList2)
        cursorSkipper = max(0, next_offset - count2)
        cursor.skip(cursorSkipper).limit(remaining)
        fileList1 = await cursor.to_list(length=remaining)
        files = fileList2 + fileList1
        next_offset = next_offset + len(fileList1)
    else:
        files = fileList2
        next_offset = offset + max_results
    
    if next_offset >= total_results:
        next_offset = ''
    
    result = (files, next_offset, total_results)
    
    # 💾 ᴄᴀᴄʜᴇ ᴛʜᴇ ʀᴇꜱᴜʟᴛ
    _cache[cache_key] = result
    logger.info(f"✅ ꜰᴏᴜɴᴅ {len(files)} ʀᴇꜱᴜʟᴛꜱ ꜰᴏʀ: {query}")
    
    return result

async def get_bad_files(query, file_type=None, filter=False):
    """⚠️ ɢᴇᴛ ᴀʟʟ ᴍᴀᴛᴄʜɪɴɢ ꜰɪʟᴇꜱ"""
    query = query.strip()
    
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + re.escape(query) + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = re.escape(query).replace(r'\ ', r'.*[\s\.\+\-_()]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return [], 0

    if USE_CAPTION_FILTER:
        filter_query = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter_query = {'file_name': regex}

    if file_type:
        filter_query['file_type'] = file_type

    # 🚀 ᴘᴀʀᴀʟʟᴇʟ Qᴜᴇʀɪᴇꜱ
    count1 = await Media.count_documents(filter_query)
    count2 = await Media2.count_documents(filter_query)

    cursor = Media.find(filter_query).sort('$natural', -1)
    cursor2 = Media2.find(filter_query).sort('$natural', -1)
    
    files2 = await cursor2.to_list(length=count2)
    files1 = await cursor.to_list(length=count1)
    
    files = files2 + files1
    
    logger.info(f"📊 ᴛᴏᴛᴀʟ ʙᴀᴅ ꜰɪʟᴇꜱ ꜰᴏᴜɴᴅ: {len(files)}")
    return files, len(files)

async def get_file_details(query):
    """📄 ɢᴇᴛ ꜰɪʟᴇ ᴅᴇᴛᴀɪʟꜱ ʙʏ ɪᴅ"""
    filter_query = {'file_id': query}
    
    # 🔍 ꜰɪʀꜱᴛ ᴄʜᴇᴄᴋ ᴄᴀᴄʜᴇ
    if query in _cache:
        return _cache[query]
    
    cursor = Media.find(filter_query)
    filedetails = await cursor.to_list(length=1)
    
    if not filedetails:
        cursor2 = Media2.find(filter_query)
        filedetails = await cursor2.to_list(length=1)
    
    # 💾 ᴄᴀᴄʜᴇ ʀᴇꜱᴜʟᴛ
    if filedetails:
        _cache[query] = filedetails
    
    return filedetails

def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0

    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])

    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    """📦 ᴜɴᴘᴀᴄᴋ ꜰɪʟᴇ ɪᴅ"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref


# 📊 DB Space Configuration
DB_LIMIT_MB = 512
SWITCH_THRESHOLD_MB = 200
RETURN_THRESHOLD_MB = 250  # switch back to primary if space recovers

async def get_db_free_space():
    try:
        stats = await db.command("dbStats")
        used_mb = (stats["dataSize"] + stats["indexSize"]) / (1024 * 1024)
        free_mb = round(DB_LIMIT_MB - used_mb, 2)
        return free_mb
    except Exception as e:
        logger.error(f"❌ ꜰᴀɪʟᴇᴅ ᴛᴏ ᴄʜᴇᴄᴋ ᴅʙ ꜱᴘᴀᴄᴇ: {e}")
        return 0


async def auto_switch_db():
    global saveMedia

    try:
        free_mb = await get_db_free_space()

        current_db = (
            "ᴘʀɪᴍᴀʀʏ"
            if tempDict.get("indexDB") == DATABASE_URI
            else "ꜱᴇᴄᴏɴᴅᴀʀʏ"
        )

        if (
            free_mb <= SWITCH_THRESHOLD_MB
            and tempDict.get("indexDB") == DATABASE_URI
        ):

            tempDict["indexDB"] = SECONDDB_URI
            saveMedia = Media2

            logger.warning(
                f"🔄 ᴅʙ ꜱᴡɪᴛᴄʜᴇᴅ ➜ ꜱᴇᴄᴏɴᴅᴀʀʏ\n"
                f"📦 ꜰʀᴇᴇ ꜱᴘᴀᴄᴇ: {free_mb} ᴍʙ\n"
                f"⚠️ ᴘʀɪᴍᴀʀʏ ᴅʙ ɴᴇᴀʀʟʏ ꜰᴜʟʟ"
            )

        elif (
            free_mb >= RETURN_THRESHOLD_MB
            and tempDict.get("indexDB") == SECONDDB_URI
        ):

            tempDict["indexDB"] = DATABASE_URI
            saveMedia = Media

            logger.info(
                f"✅ ᴅʙ ꜱᴡɪᴛᴄʜᴇᴅ ➜ ᴘʀɪᴍᴀʀʏ\n"
                f"📦 ꜰʀᴇᴇ ꜱᴘᴀᴄᴇ: {free_mb} ᴍʙ\n"
                f"🚀 ᴘʀɪᴍᴀʀʏ ᴅʙ ʀᴇꜱᴛᴏʀᴇᴅ"
            )

        return free_mb

    except Exception as e:
        logger.error(f"❌ ᴅʙ ꜱᴡɪᴛᴄʜ ᴇʀʀᴏʀ: {e}")
        return 0

# 🧹 ᴄᴀᴄʜᴇ ᴄʟᴇᴀɴᴇʀ ᴜᴛɪʟɪᴛʏ now use less
async def clear_cache():
    """🗑️ ᴄʟᴇᴀʀ ᴄᴀᴄʜᴇ"""
    _cache.clear()
    logger.info("🧹 ᴄᴀᴄʜᴇ ᴄʟᴇᴀʀᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ")
