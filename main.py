import threading
import time
import customtkinter as ctk
from pynput import keyboard

from optimizer import (
    RELOAD_MAPS,
    PaceMonitor,
    StatsManager,
    calculate_odds,
    rank_drop_routes,
)
from scanner import FortniteScanner

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TokenGPTApp(ctk.CTk):
    """Desktop gamer HUD unifying multi-map Battle Bus routing, CPM pacing, RNG odds, and global hotkeys."""

    def __init__(self):
        super().__init__()
        self.title("TokenGPT — Pirate Token Grind Optimizer")
        self.geometry("940x615")
        self.resizable(False, False)

        self.scanner = FortniteScanner()
        self.stats = StatsManager()
        self.pace = PaceMonitor(lobby_overhead_sec=110.0, target_cpm=4.5)
        self.auto_watch_active = False

        self.current_bus_start = (0.12, 0.20)
        self.current_bus_end = (0.88, 0.82)
        self.current_bus_label = "Preset NW → SE Bus"

        self._build_header()
        self._build_tabs()
        self._build_footer()
        self._start_loops()
        self._start_global_hotkeys()

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=10)
        header.pack(fill="x", padx=16, pady=(14, 8))

        self.header_title = ctk.CTkLabel(
            header,
            text="🏴‍☠️ TOKENGPT // CROSSBONES ISLE HUD",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.header_title.pack(side="left", padx=16, pady=12)

        self.lifetime_label = ctk.CTkLabel(
            header,
            text=self._format_lifetime_text(),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8",
        )
        self.lifetime_label.pack(side="right", padx=16, pady=12)

    def _format_lifetime_text(self) -> str:
        d = self.stats.data
        return f"Lifetime Chests: {d['total_chests']}  |  Matches: {d['matches_played']}  |  Best CPM: {d['best_cpm']}"

    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(self, corner_radius=10)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.tab_radar = self.tabs.add("1. Battle Bus Radar")
        self.tab_pace = self.tabs.add("2. Live Grind & Reset")
        self.tab_odds = self.tabs.add("3. Squad RNG Odds")

        self._setup_radar_tab()
        self._setup_pace_tab()
        self._setup_odds_tab()

    def _build_footer(self):
        footer = ctk.CTkFrame(self, corner_radius=8)
        footer.pack(fill="x", padx=16, pady=(0, 12))

        self.hotkey_label = ctk.CTkLabel(
            footer,
            text="⌨️ GLOBAL HOTKEYS (Works In-Game):   [F7] +1 Chest   |   [F8] Scan Battle Bus   |   [F9] Reset / Requeue Match",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#cbd5e1",
        )
        self.hotkey_label.pack(pady=8)

    # ---------------- TAB 1: BATTLE BUS RADAR ----------------
    def _setup_radar_tab(self):
        controls = ctk.CTkFrame(self.tab_radar, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(controls, text="Map:", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 6))
        self.map_menu = ctk.CTkOptionMenu(
            controls,
            values=list(RELOAD_MAPS.keys()),
            width=165,
            command=self._on_map_changed,
        )
        self.map_menu.set("Crossbones Isle")
        self.map_menu.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(controls, text="Squad:", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 6))
        self.squad_seg = ctk.CTkSegmentedButton(
            controls,
            values=["1", "2", "3", "4"],
            command=lambda _: self._refresh_routes(
                self.current_bus_start, self.current_bus_end, self.current_bus_label
            ),
        )
        self.squad_seg.set("4")
        self.squad_seg.pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            controls,
            text="Scan Screen (F8)",
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._scan_live_bus,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            controls,
            text="Sim NE → SW Bus",
            fg_color="#334155",
            hover_color="#475569",
            command=lambda: self._refresh_routes((0.85, 0.15), (0.15, 0.85), "Simulated NE → SW Bus"),
        ).pack(side="left", padx=4)

        self.bus_status_label = ctk.CTkLabel(
            self.tab_radar,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
        )
        self.bus_status_label.pack(anchor="w", padx=16, pady=(2, 8))

        self.route_box = ctk.CTkTextbox(
            self.tab_radar,
            font=ctk.CTkFont(family="Menlo", size=14),
            corner_radius=8,
        )
        self.route_box.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self._refresh_routes(self.current_bus_start, self.current_bus_end, self.current_bus_label)

    def _on_map_changed(self, selected_map: str):
        self.header_title.configure(text=f"🏴‍☠️ TOKENGPT // {selected_map.upper()} HUD")
        self._refresh_routes(self.current_bus_start, self.current_bus_end, self.current_bus_label)

    def _scan_live_bus(self):
        self.tabs.set("1. Battle Bus Radar")
        res = self.scanner.detect_bus_path()
        if res["map_open"] and res["bus_found"]:
            source = f"LIVE DETECTED ({res['ocean_pct']}% ocean)"
        elif res["map_open"]:
            source = "Map Open (Bus line unclear — using fallback)"
        else:
            source = f"No Map Detected ({res['ocean_pct']}% ocean — showing fallback)"
        self._refresh_routes(res["bus_start"], res["bus_end"], source)

    def _refresh_routes(self, start: tuple[float, float], end: tuple[float, float], label: str):
        self.current_bus_start = start
        self.current_bus_end = end
        self.current_bus_label = label

        selected_map = self.map_menu.get()
        squad = int(self.squad_seg.get())
        routes = rank_drop_routes(start, end, squad_size=squad, map_name=selected_map)
        self.bus_status_label.configure(text=f"Map: {selected_map}  |  Source: {label}  |  Vector: {start} → {end}")

        lines = [f"OPTIMAL UNCONTESTED SPLIT ON {selected_map.upper()} ({squad}-PLAYER SQUAD):\n"]
        for i, r in enumerate(routes, 1):
            lines.append(
                f"  [Player {i}]  {r['name']:<24} | ~{r['expected_uncontested']} free chests "
                f"(Total: {r['raw_chests']}, Bus Dist: {r['bus_distance']})"
            )
        lines.append("\nTIP: Avoid POIs with Bus Dist < 0.15 to prevent early off-spawn fights.")

        self.route_box.configure(state="normal")
        self.route_box.delete("1.0", "end")
        self.route_box.insert("1.0", "\n".join(lines))
        self.route_box.configure(state="disabled")

    # ---------------- TAB 2: LIVE GRIND & RESET ----------------
    def _setup_pace_tab(self):
        top = ctk.CTkFrame(self.tab_pace, corner_radius=8)
        top.pack(fill="x", padx=12, pady=12)

        self.pace_metric_label = ctk.CTkLabel(
            top,
            text="Match Chests: 0   |   Effective CPM: 0.00   |   Dry Spell: 0.0s",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.pace_metric_label.pack(pady=(14, 6))

        self.reset_banner = ctk.CTkLabel(
            top,
            text="STATUS: LOOTING ON PACE — KEEP GRINDING",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#4ade80",
        )
        self.reset_banner.pack(pady=(0, 14))

        btn_row = ctk.CTkFrame(self.tab_pace, fg_color="transparent")
        btn_row.pack(pady=8)

        ctk.CTkButton(
            btn_row,
            text="+1 Chest Opened (F7)",
            width=185,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            command=self._manual_log_chest,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row,
            text="End / Requeue Match (F9)",
            width=205,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self._end_match,
        ).pack(side="left", padx=8)

        self.watch_switch = ctk.CTkSwitch(
            self.tab_pace,
            text="Auto-Watch Screen for 'SEARCHED CHEST' Accolade Flash",
            font=ctk.CTkFont(size=13),
            command=self._toggle_auto_watch,
        )
        self.watch_switch.pack(pady=16)

    def _manual_log_chest(self):
        self.pace.log_chest()
        self.stats.record_chest(1)
        self.lifetime_label.configure(text=self._format_lifetime_text())
        self._update_pace_ui()

    def _end_match(self):
        status = self.pace.get_status()
        if status["match_chests"] > 0:
            self.stats.record_match_end(status["effective_cpm"])
        self.pace.reset_match()
        self.lifetime_label.configure(text=self._format_lifetime_text())
        self._update_pace_ui()

    def _toggle_auto_watch(self):
        self.auto_watch_active = bool(self.watch_switch.get())

    def _update_pace_ui(self):
        s = self.pace.get_status()
        self.pace_metric_label.configure(
            text=f"Match Chests: {s['match_chests']}   |   Effective CPM: {s['effective_cpm']}   |   Dry Spell: {s['dry_spell_sec']}s"
        )
        if s["should_reset"]:
            self.reset_banner.configure(
                text="🚨 DRY SPELL HIT — LEAVE MATCH & REQUEUE NOW!",
                text_color="#f87171",
            )
        else:
            self.reset_banner.configure(
                text="STATUS: LOOTING ON PACE — KEEP GRINDING",
                text_color="#4ade80",
            )

    # ---------------- TAB 3: SQUAD RNG ODDS ----------------
    def _setup_odds_tab(self):
        frame = ctk.CTkFrame(self.tab_odds, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        self.chests_slider_label = ctk.CTkLabel(
            frame, text="Chests Opened Per Player: 250", font=ctk.CTkFont(size=14, weight="bold")
        )
        self.chests_slider_label.pack(pady=(18, 4))

        self.chests_slider = ctk.CTkSlider(
            frame, from_=10, to=1000, number_of_steps=99, width=420, command=lambda _: self._recalc_odds()
        )
        self.chests_slider.set(250)
        self.chests_slider.pack(pady=(0, 14))

        self.odds_squad_seg = ctk.CTkSegmentedButton(
            frame, values=["1 Player", "2 Players", "3 Players", "4-Stack"], command=lambda _: self._recalc_odds()
        )
        self.odds_squad_seg.set("4-Stack")
        self.odds_squad_seg.pack(pady=8)

        self.treasure_hour_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            frame,
            text="2x Treasure Hour Active (Doubles Base Token Drop Rate)",
            variable=self.treasure_hour_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._recalc_odds,
        ).pack(pady=12)

        self.odds_result_label = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#facc15",
        )
        self.odds_result_label.pack(pady=(14, 6))
        self._recalc_odds()

    def _recalc_odds(self):
        chests = int(self.chests_slider.get())
        self.chests_slider_label.configure(text=f"Chests Opened Per Player: {chests}")
        squad_map = {"1 Player": 1, "2 Players": 2, "3 Players": 3, "4-Stack": 4}
        squad = squad_map[self.odds_squad_seg.get()]
        mult = 2.0 if self.treasure_hour_var.get() else 1.0

        pct = calculate_odds(chests_opened=chests, multiplier=mult, squad_size=squad)
        total_rolls = chests * squad
        self.odds_result_label.configure(
            text=f"{pct}% Squad Token Chance\n({total_rolls:,} Total Squad Chest Rolls)"
        )

    # ---------------- BACKGROUND LOOPS & GLOBAL HOTKEYS ----------------
    def _start_loops(self):
        self._tick_ui()
        t = threading.Thread(target=self._vision_worker, daemon=True)
        t.start()

    def _tick_ui(self):
        self._update_pace_ui()
        self.after(1000, self._tick_ui)

    def _vision_worker(self):
        while True:
            if self.auto_watch_active:
                try:
                    if self.scanner.detect_chest_popup():
                        self.after(0, self._manual_log_chest)
                except Exception:
                    pass
            time.sleep(0.35)

    def _start_global_hotkeys(self):
        """Listens for F7, F8, and F9 globally even while Fortnite is fullscreen."""
        def on_press(key):
            try:
                if key == keyboard.Key.f7:
                    self.after(0, self._manual_log_chest)
                elif key == keyboard.Key.f8:
                    self.after(0, self._scan_live_bus)
                elif key == keyboard.Key.f9:
                    self.after(0, self._end_match)
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()


if __name__ == "__main__":
    app = TokenGPTApp()
    app.mainloop()