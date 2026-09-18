"""Address -> coordinates lookup.

Thin wrapper over a Nominatim-compatible endpoint, used only as a convenience
when a provider types an address. Listings always store the resulting latitude
and longitude, so search never depends on this service being reachable.
"""
import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    display_name: str


async def geocode(query: str, *, country_codes: str = "in", limit: int = 5) -> list[GeocodeResult]:
    if not settings.geocoder_url or not query.strip():
        return []
    params = {
        "q": query.strip(),
        "format": "jsonv2",
        "limit": limit,
        "countrycodes": country_codes,
    }
    headers = {"User-Agent": settings.geocoder_user_agent}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(settings.geocoder_url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Geocoding failed for %r", query, exc_info=True)
        return []
    results = []
    for item in payload if isinstance(payload, list) else []:
        try:
            results.append(
                GeocodeResult(
                    latitude=float(item["lat"]),
                    longitude=float(item["lon"]),
                    display_name=str(item.get("display_name", "")),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return results
