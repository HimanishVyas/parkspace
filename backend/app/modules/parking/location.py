"""Geo helpers for radius search.

V1 deliberately avoids PostGIS: a single-city pilot with a few hundred listings
is served well by a lat/lon bounding-box prefilter (which uses a plain B-tree
index) plus an exact haversine distance computed in SQL.

Everything location-related lives in this module so swapping in PostGIS — or a
dedicated search service — later means changing these functions and nothing else.
"""
import math

from sqlalchemy import Float, and_, func
from sqlalchemy.sql.elements import ColumnElement

EARTH_RADIUS_KM = 6371.0088
MAX_RADIUS_KM = 50.0


def bounding_box(latitude: float, longitude: float, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lon, max_lon) for a circle of `radius_km`.

    The box is a superset of the circle, so it only ever prefilters — the exact
    distance test still runs afterwards.
    """
    lat_delta = math.degrees(radius_km / EARTH_RADIUS_KM)
    # Longitude degrees shrink towards the poles; clamp so we never divide by ~0.
    cos_lat = max(math.cos(math.radians(latitude)), 0.01)
    lon_delta = math.degrees(radius_km / (EARTH_RADIUS_KM * cos_lat))
    return (
        max(latitude - lat_delta, -90.0),
        min(latitude + lat_delta, 90.0),
        longitude - lon_delta,
        longitude + lon_delta,
    )


def distance_km_expression(
    lat_column: ColumnElement, lon_column: ColumnElement, latitude: float, longitude: float
) -> ColumnElement:
    """Great-circle distance in km between the row's point and (latitude, longitude).

    `least/greatest` guard against the dot product drifting outside [-1, 1] through
    floating-point error, which would make acos() error out.
    """
    lat_rad = math.radians(latitude)
    lon_rad = math.radians(longitude)
    row_lat = func.radians(lat_column.cast(Float))
    row_lon = func.radians(lon_column.cast(Float))
    cosine = (
        func.sin(lat_rad) * func.sin(row_lat)
        + func.cos(lat_rad) * func.cos(row_lat) * func.cos(row_lon - lon_rad)
    )
    return EARTH_RADIUS_KM * func.acos(func.least(1.0, func.greatest(-1.0, cosine)))


def within_bounding_box(
    lat_column: ColumnElement, lon_column: ColumnElement, latitude: float, longitude: float, radius_km: float
) -> ColumnElement:
    min_lat, max_lat, min_lon, max_lon = bounding_box(latitude, longitude, radius_km)
    return and_(
        lat_column >= min_lat,
        lat_column <= max_lat,
        lon_column >= min_lon,
        lon_column <= max_lon,
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Python-side equivalent of `distance_km_expression`, for tests and for
    distances computed outside a query."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
