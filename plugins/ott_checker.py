import asyncio
import logging
import re
from typing import Optional

import aiohttp

from info import TMDB_API_TOKEN, OWNER_ID
from database.ott_requests_db import already_requested, mark_requested

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
INDIA_REGION = "IN"

# Prevent duplicate checks while the same movie is being processed concurrently.
_PENDING = set()
_LOCAL_SENT = set()


def _clean_query(value: str) -> str:
    value = re.sub(r"[._+\-]+", " ", value or "")
    value = re.sub(r"\b(480p|576p|720p|1080p|2160p|4k|hevc|x264|x265|h264|h265|hdr|web[- ]?dl|webrip|bluray|brrip|dvdrip|hdcam|camrip)\b", " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:100]


def _extract_year(query: str) -> Optional[str]:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", query or "")
    return match.group(1) if match else None

async def _tmdb_get(session, path: str, params: dict):
    headers = {
        "Authorization": f"Bearer {TMDB_API_TOKEN}",
        "accept": "application/json",
    }
    try:
        async with session.get(
            f"{TMDB_BASE}{path}",
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
        ) as response:
            if response.status != 200:
                logger.warning("TMDB %s returned HTTP %s", path, response.status)
                return None
            return await response.json()
    except Exception as e:
        logger.warning("TMDB request failed: %s", e)
        return None


def _choose_kannada_movie(results: list, query: str, year: Optional[str]):
    if not results:
        return None

    query_words = set(re.findall(r"[a-z0-9]+", query.lower()))
    candidates = []
    for movie in results:
        if movie.get("original_language") != "kn":
            continue
        title = (movie.get("title") or "").lower()
        release_date = movie.get("release_date") or ""
        movie_year = release_date[:4] if len(release_date) >= 4 else ""
        title_words = set(re.findall(r"[a-z0-9]+", title))
        overlap = len(query_words & title_words)
        exact = title == query.lower()
        year_match = bool(year and movie_year == year)
        score = (100 if exact else 0) + (30 if year_match else 0) + overlap * 10 + float(movie.get("popularity") or 0) / 1000
        candidates.append((score, movie))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


async def check_kannada_ott(query: str):
    """Return {title, year, providers} only for a Kannada film streaming in India."""
    if not TMDB_API_TOKEN:
        return None

    clean = _clean_query(query)
    if not clean:
        return None

    year = _extract_year(clean)
    params = {
        "query": clean,
        "include_adult": "false",
        "language": "en-US",
        "region": INDIA_REGION,
        "page": 1,
    }
    if year:
        params["year"] = year

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        search_data = await _tmdb_get(session, "/search/movie", params)
        movie = _choose_kannada_movie((search_data or {}).get("results", []), clean, year)
        if not movie:
            return None

        movie_id = movie.get("id")
        if not movie_id:
            return None

        provider_data = await _tmdb_get(session, f"/movie/{movie_id}/watch/providers", {})
        india = ((provider_data or {}).get("results") or {}).get(INDIA_REGION) or {}

        providers = []
        for bucket in ("flatrate", "free", "ads"):
            for provider in india.get(bucket) or []:
                name = provider.get("provider_name")
                if name and name not in providers:
                    providers.append(name)

        if not providers:
            return None

        release_date = movie.get("release_date") or ""
        movie_year = release_date[:4] if len(release_date) >= 4 else (year or "Unknown")
        return {
            "id": str(movie_id),
            "title": movie.get("title") or clean,
            "year": movie_year,
            "providers": providers,
        }


async def notify_owner_about_missing_movie(client, query: str, user):
    """Background task: silently check OTT and PM the owner only when confirmed."""
    if not TMDB_API_TOKEN:
        return

    key_base = _clean_query(query).lower()
    if not key_base or key_base in _PENDING:
        return

    _PENDING.add(key_base)
    try:
        result = await check_kannada_ott(query)
        if not result:
            return

        movie_key = f"tmdb:{result['id']}"
        if movie_key in _LOCAL_SENT or await already_requested(movie_key):
            return

        username = f"@{user.username}" if user and user.username else "No username"
        user_id = user.id if user else "Unknown"
        text = (
            "🔔 <b>New OTT Movie Request</b>\n\n"
            f"🎬 <b>Movie:</b> {result['title']}\n"
            f"📅 <b>Year:</b> {result['year']}\n"
            f"📺 <b>OTT:</b> {', '.join(result['providers'])}\n\n"
            f"👤 <b>User:</b> {username}\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>"
        )

        await client.send_message(chat_id=OWNER_ID, text=text)
        _LOCAL_SENT.add(movie_key)
        await mark_requested(movie_key, result['title'], result['year'], result['providers'])
    except Exception as e:
        logger.warning("OTT owner notification failed: %s", e)
    finally:
        _PENDING.discard(key_base)


def schedule_ott_check(client, query: str, user):
    asyncio.create_task(notify_owner_about_missing_movie(client, query, user))
