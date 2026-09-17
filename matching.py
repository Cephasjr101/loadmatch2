"""Core matching engine: hard filters + weighted score."""
import math
from datetime import datetime
from typing import List

from .models import Load, Truck, TruckStatus

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def find_matches(load: Load, trucks: List[Truck], max_distance_km: float = 500.0) -> List[dict]:
    """Return trucks compatible with the load, sorted by score (higher = better)."""
    results = []
    for truck in trucks:
        if truck.status != TruckStatus.available:
            continue
        if truck.equipment_type != load.equipment_type:
            continue
        if truck.capacity_kg < load.weight_kg:
            continue
        # Availability window must cover pickup time (compare naive datetimes
        # for SQLite, which stores them without tz by default).
        pickup = load.pickup_at.replace(tzinfo=None)
        if not (truck.available_from.replace(tzinfo=None) <= pickup
                <= truck.available_until.replace(tzinfo=None)):
            continue

        dist = haversine_km(
            truck.current_lat, truck.current_lon, load.origin_lat, load.origin_lon
        )
        if dist > max_distance_km:
            continue

        score, reasons = 100.0, []
        score -= min(dist, max_distance_km) / max_distance_km * 60.0  # proximity: up to 60 pts
        reasons.append(f"{dist:.0f} km from origin")

        if pickup.date() == truck.available_from.replace(tzinfo=None).date():
            score += 10.0
            reasons.append("available exactly on pickup day")

        headroom = truck.capacity_kg - load.weight_kg
        if headroom / truck.capacity_kg < 0.2:
            score += 10.0
            reasons.append("tight fit (efficient load)")

        results.append({
            "truck": truck,
            "score": round(score, 2),
            "distance_to_origin_km": round(dist, 1),
            "reasons": reasons,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
