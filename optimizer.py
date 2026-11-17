import json
import math
import os
import time
from typing import Dict, List, Tuple

# Normalized (x, y) coordinates (0.0 to 1.0) & estimated chest counts across Reload islands
RELOAD_MAPS: Dict[str, List[Dict]] = {
    "Crossbones Isle": [
        {"name": "The Chest", "x": 0.50, "y": 0.48, "chests": 34},
        {"name": "Arlong Park", "x": 0.30, "y": 0.34, "chests": 19},
        {"name": "Loguetown", "x": 0.66, "y": 0.28, "chests": 22},
        {"name": "Baratie", "x": 0.24, "y": 0.70, "chests": 18},
        {"name": "Syrup Village", "x": 0.72, "y": 0.68, "chests": 17},
        {"name": "Lantern Landing", "x": 0.38, "y": 0.78, "chests": 16},
        {"name": "Northeast Buried Island", "x": 0.84, "y": 0.22, "chests": 15},
    ],
    "Venture": [
        {"name": "Tilted Towers", "x": 0.38, "y": 0.45, "chests": 38},
        {"name": "Retail Row", "x": 0.74, "y": 0.52, "chests": 28},
        {"name": "Pleasant Park", "x": 0.28, "y": 0.24, "chests": 25},
        {"name": "Lazy Links", "x": 0.56, "y": 0.20, "chests": 22},
        {"name": "Dusty Docks", "x": 0.62, "y": 0.44, "chests": 19},
        {"name": "Sandy Sheets", "x": 0.48, "y": 0.78, "chests": 21},
        {"name": "Lone Lodge", "x": 0.84, "y": 0.30, "chests": 17},
    ],
    "Oasis": [
        {"name": "Paradise Palms", "x": 0.68, "y": 0.62, "chests": 32},
        {"name": "Sun Strider Plaza", "x": 0.35, "y": 0.36, "chests": 26},
        {"name": "Scorched Springs", "x": 0.26, "y": 0.66, "chests": 21},
        {"name": "Mirage Market", "x": 0.54, "y": 0.26, "chests": 23},
        {"name": "Canyon Outpost", "x": 0.76, "y": 0.30, "chests": 18},
        {"name": "Sunken Oasis", "x": 0.46, "y": 0.52, "chests": 20},
        {"name": "Dune Docks", "x": 0.24, "y": 0.24, "chests": 16},
    ],
    "Squid Grounds": [
        {"name": "Red Light Arena", "x": 0.50, "y": 0.50, "chests": 35},
        {"name": "Glass Bridge", "x": 0.68, "y": 0.34, "chests": 24},
        {"name": "Dormitory Sector", "x": 0.30, "y": 0.32, "chests": 26},
        {"name": "Honeycomb Plaza", "x": 0.32, "y": 0.68, "chests": 22},
        {"name": "Marbles Courtyard", "x": 0.70, "y": 0.68, "chests": 20},
        {"name": "VIP Observatory", "x": 0.52, "y": 0.20, "chests": 18},
        {"name": "Tug Pier", "x": 0.20, "y": 0.50, "chests": 16},
    ],
}


def point_to_segment_distance(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """Calculates perpendicular distance from POI (px, py) to Battle Bus segment."""
    dx, dy = x2 - x1, y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def rank_drop_routes(
    bus_start: Tuple[float, float],
    bus_end: Tuple[float, float],
    squad_size: int = 4,
    map_name: str = "Crossbones Isle",
) -> List[Dict]:
    """Ranks POIs for the selected Reload map by uncontested chest yield."""
    pois = RELOAD_MAPS.get(map_name, RELOAD_MAPS["Crossbones Isle"])
    scored = []
    for poi in pois:
        dist = point_to_segment_distance(
            poi["x"], poi["y"], bus_start[0], bus_start[1], bus_end[0], bus_end[1]
        )
        # POIs directly under the bus (<0.15) lose ~65% of chests to hot-droppers
        contested_factor = 0.35 if dist < 0.15 else min(1.0, 0.55 + dist * 1.1)
        expected_uncontested = round(poi["chests"] * contested_factor, 1)
        scored.append(
            {
                "name": poi["name"],
                "raw_chests": poi["chests"],
                "bus_distance": round(dist, 2),
                "expected_uncontested": expected_uncontested,
            }
        )

    scored.sort(key=lambda r: r["expected_uncontested"], reverse=True)
    return scored[: max(1, min(4, squad_size))]


def calculate_odds(
    chests_opened: int,
    base_rate: float = 0.00000727,
    multiplier: float = 1.0,
    squad_size: int = 4,
) -> float:
    """Calculates cumulative squad Pirate Token probability (%)."""
    total_rolls = max(0, chests_opened) * max(1, squad_size)
    p = min(1.0, base_rate * multiplier)
    if total_rolls == 0 or p <= 0:
        return 0.0
    prob = 1.0 - math.pow(1.0 - p, total_rolls)
    return round(prob * 100.0, 3)


class PaceMonitor:
    """Tracks match Chests-Per-Minute (CPM) and triggers early requeue alerts."""

    def __init__(self, lobby_overhead_sec: float = 110.0, target_cpm: float = 4.5):
        self.lobby_overhead_sec = lobby_overhead_sec
        self.target_cpm = target_cpm
        self.reset_match()

    def reset_match(self):
        now = time.time()
        self.match_start = now
        self.last_chest_time = now
        self.match_chests = 0

    def log_chest(self):
        self.match_chests += 1
        self.last_chest_time = time.time()

    def get_status(self) -> Dict:
        now = time.time()
        elapsed_sec = max(1.0, now - self.match_start)
        dry_spell_sec = now - self.last_chest_time
        effective_minutes = (elapsed_sec + self.lobby_overhead_sec) / 60.0
        effective_cpm = self.match_chests / effective_minutes

        # Trigger reset once early loot is dry (>35s no chest after opening >=4 chests, or >75s total)
        should_reset = (self.match_chests >= 4 and dry_spell_sec > 35.0) or (
            elapsed_sec > 75.0 and dry_spell_sec > 45.0
        )
        return {
            "match_chests": self.match_chests,
            "effective_cpm": round(effective_cpm, 2),
            "dry_spell_sec": round(dry_spell_sec, 1),
            "should_reset": should_reset,
        }


class StatsManager:
    """Persists lifetime chests, matches played, and best CPM to local JSON."""

    def __init__(self, filepath: str = "tokengpt_stats.json"):
        self.filepath = filepath
        self.data = {"total_chests": 0, "matches_played": 0, "best_cpm": 0.0}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def record_chest(self, count: int = 1):
        self.data["total_chests"] += count
        self.save()

    def record_match_end(self, cpm: float):
        self.data["matches_played"] += 1
        if cpm > self.data["best_cpm"]:
            self.data["best_cpm"] = round(cpm, 2)
        self.save()