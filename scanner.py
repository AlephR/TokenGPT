import time
import cv2
import mss
import numpy as np


class FortniteScanner:
    """
    Anti-cheat safe passive screen analyzer.
    Reads pixels from the monitor without touching game memory or processes.
    """

    def __init__(self):
        self.last_chest_trigger = 0.0
        self.chest_cooldown_sec = 3.5  # Prevents double-counting the same chest popup

    def capture_frame(self) -> np.ndarray:
        """Grabs the primary monitor as a fast BGR OpenCV image."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            raw = np.array(sct.grab(monitor))
            return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

    def _crop_center_map(self, frame: np.ndarray) -> np.ndarray:
        """Crops the central square where Fortnite displays the full island map."""
        h, w, _ = frame.shape
        side = min(h, w)
        x1 = (w - side) // 2
        y1 = (h - side) // 2
        return frame[y1 : y1 + side, x1 : x1 + side]

    def detect_bus_path(self, frame: np.ndarray | None = None) -> dict:
        """
        Detects if the full map is open and finds the Battle Bus flight vector.
        Returns normalized (0.0 - 1.0) bus_start and bus_end coordinates.
        """
        if frame is None:
            frame = self.capture_frame()

        map_crop = self._crop_center_map(frame)
        small = cv2.resize(map_crop, (500, 500))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

        # 1. Check for Fortnite ocean blue to confirm the full map screen is open
        lower_ocean = np.array([95, 70, 50])
        upper_ocean = np.array([132, 255, 255])
        ocean_mask = cv2.inRange(hsv, lower_ocean, upper_ocean)
        ocean_ratio = float(np.count_nonzero(ocean_mask)) / ocean_mask.size

        if ocean_ratio < 0.22:
            return {
                "map_open": False,
                "ocean_pct": round(ocean_ratio * 100, 1),
                "bus_found": False,
                "bus_start": (0.15, 0.20),
                "bus_end": (0.85, 0.80),
            }

        # 2. Isolate bright white/cyan pixels of the Battle Bus flight line
        lower_bus = np.array([0, 0, 215])
        upper_bus = np.array([180, 65, 255])
        bus_mask = cv2.inRange(hsv, lower_bus, upper_bus)

        edges = cv2.Canny(bus_mask, 50, 150)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180, threshold=60, minLineLength=140, maxLineGap=25
        )

        if lines is not None:
            # Flatten to (N, 4) so it works across all OpenCV versions
            flat_lines = lines.reshape(-1, 4)
            x1, y1, x2, y2 = max(
                flat_lines, key=lambda l: np.hypot(l[2] - l[0], l[3] - l[1])
            )
            return {
                "map_open": True,
                "ocean_pct": round(ocean_ratio * 100, 1),
                "bus_found": True,
                "bus_start": (round(float(x1) / 500.0, 3), round(float(y1) / 500.0, 3)),
                "bus_end": (round(float(x2) / 500.0, 3), round(float(y2) / 500.0, 3)),
            }

        return {
            "map_open": True,
            "ocean_pct": round(ocean_ratio * 100, 1),
            "bus_found": False,
            "bus_start": (0.15, 0.20),
            "bus_end": (0.85, 0.80),
        }

    def detect_chest_popup(self, frame: np.ndarray | None = None) -> bool:
        """
        Watches the top-right XP accolade zone for the bright gold/cyan
        chest-opened badge flash. Uses a cooldown so one chest counts once.
        """
        now = time.time()
        if now - self.last_chest_trigger < self.chest_cooldown_sec:
            return False

        if frame is None:
            frame = self.capture_frame()

        h, w, _ = frame.shape
        # Crop top-right HUD accolade region (72%->98% width, 12%->28% height)
        roi = frame[int(h * 0.12) : int(h * 0.28), int(w * 0.72) : int(w * 0.98)]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Match bright gold/yellow XP accolade banner highlights
        lower_gold = np.array([18, 130, 180])
        upper_gold = np.array([35, 255, 255])
        gold_mask = cv2.inRange(hsv, lower_gold, upper_gold)
        gold_ratio = float(np.count_nonzero(gold_mask)) / gold_mask.size

        if gold_ratio > 0.08:
            self.last_chest_trigger = now
            return True
        return False


if __name__ == "__main__":
    print("--- Testing TokenGPT Vision Scanner ---")
    scanner = FortniteScanner()

    # 1. Test synthetic map image with a simulated Battle Bus line
    fake_map = np.zeros((500, 500, 3), dtype=np.uint8)
    fake_map[:] = (180, 90, 20)  # OpenCV BGR ocean blue
    cv2.line(fake_map, (60, 100), (440, 410), (255, 255, 255), 4)  # White bus path

    result = scanner.detect_bus_path(fake_map)
    print(f"Simulated Map Test -> Map Open: {result['map_open']} | Bus Found: {result['bus_found']}")
    print(f"Detected Bus Vector: {result['bus_start']} -> {result['bus_end']}")

    # 2. Test live Mac screen capture
    live_result = scanner.detect_bus_path()
    print(f"Live Screen Test   -> Map Open: {live_result['map_open']} ({live_result['ocean_pct']}% ocean blue)")