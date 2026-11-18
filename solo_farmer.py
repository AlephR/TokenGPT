import platform
import time
import tkinter as tk
import threading
import mss
import numpy as np
from pynput import keyboard

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import winsound

MAPS = {
    "BR: Crossbones Isle": [
        ("Rubber Resort (NW Island)", 55),
        ("Lantern Landing (Center-W)", 49),
        ("Loguetown (South Bay)", 45),
        ("The Chest (34 Buried + 10 Reg)", 44),
        ("Arlong Park (West Coast)", 37),
        ("Plunder Port (South Ships)", 36),
        ("Fortune's Fort (NE)", 38),
        ("Busy Bay / Baratie (SE)", 34),
        ("Cursed Cavern (Center-E)", 32),
    ],
    "RELOAD: Rotation Maps": [
        ("Nitemare Island - Central POI", 28),
        ("Squid Grounds - Main Complex", 26),
        ("Venture - Tilted / Towers", 30),
        ("Oasis - Paradise / Palms", 26),
        ("Slurp Rush - Factory Core", 25),
        ("Surf City - Boardwalk", 24),
        ("Elite Stronghold - Main Keep", 26),
    ],
}

MODE_NAMES = list(MAPS.keys())
SEARCH_RING_BOX_RATIO = (0.485, 0.485, 0.515, 0.515)


class SoloTokenHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SoloTokenHUD")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg="#10141d")
        self.root.geometry("370x195+40+40")
        self.root.resizable(False, False)

        self.mode_index = 0
        self.poi_index = 0
        self.state = "LOBBY"
        self.chests_run = 0
        self.chests_total = 0

        self.session_start = time.time()
        self.dead_start = time.time()
        self.looting_start = None
        self.last_chest_time = None
        self.avg_dead_time = 75.0
        self.dead_samples = []
        self.alert_played = False

        self._build_ui()
        self._start_hotkeys()

        threading.Thread(target=self._screen_watcher_loop, daemon=True).start()
        self._update_ui_loop()

    def _play_beep(self):
        if IS_WINDOWS:
            threading.Thread(
                target=lambda: winsound.Beep(1100, 220), daemon=True
            ).start()
        else:
            self.root.bell()

    def _build_ui(self):
        self.lbl_mode = tk.Label(
            self.root, text="", font=("Consolas", 9, "bold"),
            fg="#fbbf24", bg="#10141d", anchor="w"
        )
        self.lbl_mode.pack(fill="x", padx=12, pady=(8, 0))

        self.lbl_poi = tk.Label(
            self.root, text="", font=("Consolas", 11, "bold"),
            fg="#38bdf8", bg="#10141d", anchor="w"
        )
        self.lbl_poi.pack(fill="x", padx=12, pady=(2, 2))

        self.lbl_counts = tk.Label(
            self.root, text="", font=("Consolas", 13, "bold"),
            fg="#f8fafc", bg="#10141d", anchor="w"
        )
        self.lbl_counts.pack(fill="x", padx=12, pady=2)

        self.lbl_rate = tk.Label(
            self.root, text="", font=("Consolas", 10),
            fg="#94a3b8", bg="#10141d", anchor="w"
        )
        self.lbl_rate.pack(fill="x", padx=12, pady=2)

        self.lbl_status = tk.Label(
            self.root, text="IN LOBBY — Press F8 on Drop",
            font=("Consolas", 11, "bold"),
            fg="#10141d", bg="#22c55e", pady=6
        )
        self.lbl_status.pack(fill="x", padx=12, pady=(8, 4))

        self.lbl_keys = tk.Label(
            self.root,
            text="[F5] Mode | [F6] POI | [F7] +1 | [F8] Land | [F9] Reset",
            font=("Consolas", 8), fg="#64748b", bg="#10141d"
        )
        self.lbl_keys.pack(fill="x", padx=12, pady=(0, 6))

    def _start_hotkeys(self):
        def on_press(key):
            if key == keyboard.Key.f5:
                self.toggle_mode()
            elif key == keyboard.Key.f6:
                self.cycle_poi()
            elif key == keyboard.Key.f7:
                self.add_chest()
            elif key == keyboard.Key.f8:
                self.start_looting()
            elif key == keyboard.Key.f9:
                self.reset_run()

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

    def toggle_mode(self):
        self.mode_index = (self.mode_index + 1) % len(MODE_NAMES)
        self.poi_index = 0
        if not self.dead_samples:
            self.avg_dead_time = 75.0 if self.mode_index == 0 else 50.0

    def cycle_poi(self):
        current_list = MAPS[MODE_NAMES[self.mode_index]]
        self.poi_index = (self.poi_index + 1) % len(current_list)

    def start_looting(self):
        now = time.time()
        if self.state == "LOBBY":
            dead_duration = now - self.dead_start
            if 20 < dead_duration < 240:
                self.dead_samples.append(dead_duration)
                self.avg_dead_time = sum(self.dead_samples) / len(self.dead_samples)
        self.state = "LOOTING"
        self.looting_start = now
        self.last_chest_time = now
        self.alert_played = False

    def add_chest(self):
        now = time.time()
        if self.state != "LOOTING":
            self.start_looting()
        self.chests_run += 1
        self.chests_total += 1
        self.last_chest_time = now
        self.alert_played = False

    def reset_run(self):
        self.state = "LOBBY"
        self.chests_run = 0
        self.looting_start = None
        self.last_chest_time = None
        self.dead_start = time.time()
        self.alert_played = False

    def _should_reset_now(self):
        if self.state != "LOOTING" or self.chests_run == 0 or not self.looting_start:
            return False
        now = time.time()
        run_elapsed = now - self.looting_start
        idle_since_chest = now - self.last_chest_time
        avg_sec_per_chest = (run_elapsed + self.avg_dead_time) / self.chests_run
        return idle_since_chest > avg_sec_per_chest

    def _screen_watcher_loop(self):
        last_detect = 0.0
        with mss.mss() as sct:
            mon = sct.monitors[1]
            w, h = mon["width"], mon["height"]
            box = {
                "left": int(w * SEARCH_RING_BOX_RATIO[0]),
                "top": int(h * SEARCH_RING_BOX_RATIO[1]),
                "width": int(w * (SEARCH_RING_BOX_RATIO[2] - SEARCH_RING_BOX_RATIO[0])),
                "height": int(h * (SEARCH_RING_BOX_RATIO[3] - SEARCH_RING_BOX_RATIO[1])),
            }
            while True:
                time.sleep(0.12)
                if time.time() - last_detect < 2.2:
                    continue
                frame = np.array(sct.grab(box))[:, :, :3]
                bright_pixels = np.sum(
                    (frame[:, :, 2] > 235) & (frame[:, :, 1] > 220) & (frame[:, :, 0] > 180)
                )
                total_pixels = frame.shape[0] * frame.shape[1]
                if 0.08 < (bright_pixels / total_pixels) < 0.45:
                    last_detect = time.time()
                    self.add_chest()

    def _update_ui_loop(self):
        mode_name = MODE_NAMES[self.mode_index]
        poi_name, expected_chests = MAPS[mode_name][self.poi_index]
        elapsed_hours = max((time.time() - self.session_start) / 3600.0, 1e-5)
        chests_per_hour = self.chests_total / elapsed_hours

        self.lbl_mode.config(text=f"MODE: {mode_name}")
        self.lbl_poi.config(text=f"DROP: {poi_name}")
        self.lbl_counts.config(
            text=f"Run: {self.chests_run}/{expected_chests}  |  Total: {self.chests_total}"
        )
        self.lbl_rate.config(
            text=f"Pace: {chests_per_hour:.0f} chests/hr  |  Dead Time: {self.avg_dead_time:.0f}s"
        )

        if self.state == "LOBBY":
            self.lbl_status.config(
                text="QUEUING / BUS — Press F8 on Drop",
                bg="#38bdf8", fg="#0f172a"
            )
        elif self._should_reset_now() or self.chests_run >= expected_chests:
            self.lbl_status.config(
                text=">>> RESET NOW (PRESS F9) <<<",
                bg="#ef4444", fg="#ffffff"
            )
            if not self.alert_played:
                self.alert_played = True
                self._play_beep()
        else:
            self.lbl_status.config(
                text="LOOTING — Keep Going",
                bg="#22c55e", fg="#0f172a"
            )

        self.root.after(200, self._update_ui_loop)

    def run(self):
        self.root.lift()
        self.root.mainloop()


if __name__ == "__main__":
    SoloTokenHUD().run()