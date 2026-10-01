import logging
from motor.motor_asyncio import AsyncIOMotorClient
from info import DATABASE_URI, DATABASE_NAME

logger = logging.getLogger(__name__)

_client = AsyncIOMotorClient(DATABASE_URI)
_db = _client[DATABASE_NAME]
_collection = _db["ott_movie_requests"]

_indexes_ready = False

async def _ensure_indexes():
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await _collection.create_index("movie_key", unique=True)
        _indexes_ready = True
    except Exception as e:
        logger.warning("OTT request index setup failed: %s", e)

async def already_requested(movie_key: str) -> bool:
    try:
        await _ensure_indexes()
        return bool(await _collection.find_one({"movie_key": movie_key}, {"_id": 1}))
    except Exception as e:
        logger.warning("OTT request lookup failed: %s", e)
        return False

async def mark_requested(movie_key: str, movie_title: str, year: str, providers: list[str]):
    try:
        await _ensure_indexes()
        await _collection.update_one(
            {"movie_key": movie_key},
            {"$set": {
                "movie_key": movie_key,
                "movie_title": movie_title,
                "year": year,
                "providers": providers,
            }},
            upsert=True,
        )
        return True
    except Exception as e:
        logger.warning("OTT request save failed: %s", e)
        return False
