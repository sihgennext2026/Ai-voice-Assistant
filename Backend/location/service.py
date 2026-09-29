"""Location intelligence: geocoding, local demand discovery and road distance, with cached fallback.

Live APIs are never required: DEMO_MODE reads the cached snapshot in knowledge/data/location_cache.json,
and every live call falls back to cache or a straight-line estimate on failure.
"""
import logging
import math
from typing import Dict, List, Optional

import requests

from config import Settings
from knowledge.base import KnowledgeBase
from livelihood.schemas import Location, NearbyOpportunity

logger = logging.getLogger(__name__)
USER_AGENT = {"User-Agent": "sih-livelihood-guidance-prototype/1.0"}
ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"
DEMAND_RADIUS_M = 3000
ROAD_FACTOR = 1.3


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class LocationService:
    def __init__(self, settings: Settings, kb: KnowledgeBase):
        self.settings = settings
        self.kb = kb
        self.cache = kb.location_cache

    # ── live calls ────────────────────────────────────────────────────────────
    def geocode(self, name: str) -> Optional[Location]:
        try:
            r = requests.get(
                f"{self.settings.nominatim_base_url}/search",
                params={"q": name, "format": "json", "limit": 1, "countrycodes": "in"},
                headers=USER_AGENT, timeout=4,
            )
            r.raise_for_status()
            hits = r.json()
            if hits:
                return Location(name=name, lat=float(hits[0]["lat"]), lon=float(hits[0]["lon"]), source="nominatim")
        except Exception as exc:
            logger.warning("Nominatim geocoding failed: %s", type(exc).__name__)
        return None

    def fetch_tailoring_demand(self, lat: float, lon: float) -> Optional[dict]:
        query = (
            f'[out:json][timeout:10];('
            f'nwr["shop"~"tailor|fabric|sewing"](around:{DEMAND_RADIUS_M},{lat},{lon});'
            f'nwr["craft"~"tailor|dressmaker"](around:{DEMAND_RADIUS_M},{lat},{lon}););out center tags;'
        )
        try:
            r = requests.post(self.settings.overpass_api_url, data={"data": query}, headers=USER_AGENT, timeout=6)
            r.raise_for_status()
            elements = []
            for e in r.json().get("elements", []):
                c = e.get("center", e)
                if c.get("lat") is None:
                    continue
                elements.append({
                    "osm_id": f"{e['type']}/{e['id']}",
                    "name": e.get("tags", {}).get("name"),
                    "lat": c["lat"], "lon": c["lon"],
                    "km": round(haversine_km(lat, lon, c["lat"], c["lon"]), 1),
                })
            return {"count": len(elements), "radius_km": DEMAND_RADIUS_M / 1000, "elements": elements}
        except Exception as exc:
            logger.warning("Overpass query failed: %s", type(exc).__name__)
            return None

    def road_distances(self, origin: Location, targets: List[dict]) -> Dict[str, dict]:
        if not self.settings.openrouteservice_api_key or not targets:
            return {}
        locations = [[origin.lon, origin.lat]] + [[t["lon"], t["lat"]] for t in targets]
        try:
            r = requests.post(
                ORS_MATRIX_URL,
                headers={"Authorization": self.settings.openrouteservice_api_key},
                json={"locations": locations, "sources": [0], "metrics": ["distance", "duration"]},
                timeout=6,
            )
            r.raise_for_status()
            body = r.json()
            out = {}
            for t, d, s in zip(targets, body["distances"][0][1:], body["durations"][0][1:]):
                if d is not None:
                    out[t["id"]] = {"km": round(d / 1000, 1), "min": round(s / 60), "source": "openrouteservice"}
            return out
        except Exception as exc:
            logger.warning("OpenRouteService matrix failed: %s", type(exc).__name__)
            return {}

    # ── public API used by the session ───────────────────────────────────────
    def _cache_matches(self, origin: Location) -> bool:
        cached = self.cache.get("origin") or {}
        return bool(cached) and cached.get("name") == origin.name

    def nearby_opportunities(self, origin: Optional[Location]) -> List[NearbyOpportunity]:
        if origin is None:
            return []
        if origin.lat is None:
            geo = None if self.settings.demo_mode else self.geocode(origin.name)
            if geo is None and self._cache_matches(origin):
                geo = Location(**self.cache["origin"])
            if geo is None:
                return []
            origin.lat, origin.lon = geo.lat, geo.lon

        use_cache = self.settings.demo_mode and self._cache_matches(origin)
        curated = self.kb.opportunities

        if use_cache:
            distances = self.cache.get("distances", {})
            demand = self.cache.get("osm_demand")
        else:
            distances = self.road_distances(origin, curated)
            demand = self.fetch_tailoring_demand(origin.lat, origin.lon)
            if demand is None and self._cache_matches(origin):
                demand = self.cache.get("osm_demand")

        results: List[NearbyOpportunity] = []
        for opp in curated:
            d = distances.get(opp["id"])
            if d:
                km, minutes, dsrc = d["km"], d.get("min"), d["source"] + (" (cached)" if use_cache else "")
            else:
                km = round(haversine_km(origin.lat, origin.lon, opp["lat"], opp["lon"]) * ROAD_FACTOR, 1)
                minutes, dsrc = None, "estimated"
            results.append(NearbyOpportunity(
                id=opp["id"], type=opp["type"], name=opp["name"], area=opp["area"],
                distance_km=km, duration_min=minutes, distance_source=dsrc, source=opp["source"],
            ))

        if demand and demand.get("count"):
            nearest = min(e["km"] for e in demand["elements"])
            results.append(NearbyOpportunity(
                id="osm-tailoring-demand", type="tailoring_demand",
                name=f"{demand['count']} tailoring shops nearby", area=f"Within {demand['radius_km']:g} km",
                distance_km=nearest, distance_source="straight-line",
                source="openstreetmap" + (" (cached)" if use_cache else ""),
            ))
        return results
