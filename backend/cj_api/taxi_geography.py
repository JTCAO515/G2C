"""Taxi inputs use GCJ-02 at the provider and WGS-84 for the local region test."""

from functools import lru_cache
import json
from math import cos, degrees, pi, radians, sin, sqrt
from pathlib import Path


DATA = Path(__file__).with_name('taxi_data') / 'mainland-wgs84.json'
AXIS = 6378245.0
ECCENTRICITY_SQUARED = 0.006693421622965943


@lru_cache(maxsize=1)
def _polygons():
    return json.loads(DATA.read_bytes())['coordinates']


def _inside_ring(lng, lat, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat) and lng < x1 + (x2 - x1) * (lat - y1) / (y2 - y1):
            inside = not inside
    return inside


def in_mainland(lng, lat):
    """Use the CHN map unit, which excludes the separate HK, Macau and Taiwan units."""
    if not 72 < lng < 136 or not 17 < lat < 55:
        return False
    return any(_inside_ring(lng, lat, outline)
               and not any(_inside_ring(lng, lat, hole) for hole in holes)
               for outline, *holes in _polygons())


def wgs_to_gcj(lng, lat):
    # Coordinate offsets adapted from wandergis/coordtransform (MIT).
    x, y = lng - 105, lat - 35
    shared = 2 / 3 * (20 * sin(6 * x * pi) + 20 * sin(2 * x * pi))
    dy = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(abs(x))
    dy += shared + 2 / 3 * (20 * sin(y * pi) + 40 * sin(y * pi / 3))
    dy += 2 / 3 * (160 * sin(y * pi / 12) + 320 * sin(y * pi / 30))
    dx = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(abs(x))
    dx += shared + 2 / 3 * (20 * sin(x * pi) + 40 * sin(x * pi / 3))
    dx += 2 / 3 * (150 * sin(x * pi / 12) + 300 * sin(x * pi / 30))
    latitude = radians(lat)
    ellipsoid = 1 - ECCENTRICITY_SQUARED * sin(latitude) ** 2
    radius = AXIS / sqrt(ellipsoid)
    return (lng + degrees(dx / (radius * cos(latitude))),
            lat + degrees(dy * ellipsoid / (radius * (1 - ECCENTRICITY_SQUARED))))


def gcj_to_wgs(lng, lat):
    # The forward transform is smooth and local. Re-evaluate the offset
    # at the estimate before testing a WGS-84 boundary.
    east, north = lng, lat
    for _ in range(3):
        shifted_east, shifted_north = wgs_to_gcj(east, north)
        east -= shifted_east - lng
        north -= shifted_north - lat
    return east, north
