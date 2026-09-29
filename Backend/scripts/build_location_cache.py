"""Snapshot live location data for the demo case into knowledge/data/location_cache.json.

Run: python -m scripts.build_location_cache
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from knowledge.base import DATA_DIR, get_knowledge  # noqa: E402
from livelihood.schemas import Location  # noqa: E402
from location.service import LocationService  # noqa: E402


def main():
    settings = get_settings()
    kb = get_knowledge()
    case = kb.demo_cases[settings.demo_case_id]
    origin = Location(**case["registered"]["location"])
    service = LocationService(settings, kb)

    distances = service.road_distances(origin, kb.opportunities)
    demand = service.fetch_tailoring_demand(origin.lat, origin.lon)
    if not distances or demand is None:
        print("Live lookup failed; existing cache left unchanged.")
        sys.exit(1)

    snapshot = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "Snapshot of live API results for the demo case. Distances: OpenRouteService driving. "
                    "Demand: OpenStreetMap via Overpass (data (c) OpenStreetMap contributors, ODbL).",
        },
        "origin": origin.model_dump(),
        "distances": distances,
        "osm_demand": demand,
    }
    (DATA_DIR / "location_cache.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Cached {len(distances)} distances and {demand['count']} OSM tailoring locations.")


if __name__ == "__main__":
    main()
