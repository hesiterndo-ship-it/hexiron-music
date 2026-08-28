import logging
import os
import time

import httpx

from config import CENTRAL_API_URL, CENTRAL_API_KEY, PRODUCT_ID


logger = logging.getLogger(__name__)

_CACHE_TTL = 120
_STALE_FALLBACK_TTL = 600

_cache: dict[str, tuple[float, bool]] = {}


async def is_group_licensed(group_id) -> bool:
    group_id = str(group_id)
    now = time.time()

    cached = _cache.get(group_id)

    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    proxy = os.getenv("SOCKS5_PROXY_URL")

    try:
        async with httpx.AsyncClient(
            timeout=5.0,
            proxy=proxy,
        ) as client:
            resp = await client.get(
                f"{CENTRAL_API_URL}/api/v1/license",
                params={
                    "product": PRODUCT_ID,
                    "group_id": group_id,
                },
                headers={
                    "X-API-Key": CENTRAL_API_KEY,
                },
            )

        if resp.status_code == 200:
            active = bool(resp.json().get("active"))
            _cache[group_id] = (now, active)
            return active

        logger.warning(
            "license API returned %s for group %s",
            resp.status_code,
            group_id,
        )

    except Exception as e:
        logger.warning(
            "license API unreachable for group %s: %s",
            group_id,
            e,
        )

    if cached and (now - cached[0]) < _STALE_FALLBACK_TTL:
        logger.warning(
            "using stale cached license status for group %s",
            group_id,
        )
        return cached[1]

    logger.error(
        "no cached license info for group %s and API unreachable - failing open",
        group_id,
    )

    return True