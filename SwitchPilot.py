"""
SwitchPilot v1.0
Automatic OBS source switching for streamers
https://itch.io/

Detects active applications and automatically switches OBS video/audio sources.
"""

import customtkinter as ctk
import obsws_python as obs
import win32gui
import win32process
import win32api
import win32con
import psutil
import threading
import time
import json
import os
import sys
import keyboard
import shutil
import winsound
import ctypes

# --- App Info ---
APP_NAME = "SwitchPilot"
APP_VERSION = "1.0"

# --- UI Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")  # Base theme (required)

ctk.ThemeManager.theme["CTkButton"]["fg_color"] = ["#9146FF", "#9146FF"]
ctk.ThemeManager.theme["CTkButton"]["hover_color"] = ["#772CE8", "#772CE8"]

# Design System - Consistent spacing
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

# Design System - Colors
COLOR_PRIMARY = "#9146FF"       # Purple - primary actions, active states
COLOR_SUCCESS = "#22C55E"       # Green - connected, healthy
COLOR_WARNING = "#F59E0B"       # Amber - warnings, pending states
COLOR_DANGER = "#EF4444"        # Red - errors, destructive actions
COLOR_DANGER_DARK = "#991B1B"   # Dark red - backgrounds for alerts
COLOR_ACCENT = "#F59E0B"        # Amber - game detection highlight
COLOR_MUTED = "#6B7280"         # Gray - secondary text
COLOR_SURFACE = "#1F1F1F"       # Dark surface for cards

# Design System - Typography
FONT_TITLE = ("Segoe UI", 24, "bold")
FONT_HEADING = ("Segoe UI", 14, "bold")
FONT_BODY = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 11)
FONT_CAPTION = ("Segoe UI", 10)

# --- Paths ---
if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(app_dir, "switchpilot_config.json")

# --- Flash Window Helpers (Windows API) ---
FLASHW_STOP = 0
FLASHW_CAPTION = 0x00000001
FLASHW_TRAY = 0x00000002
FLASHW_ALL = (FLASHW_CAPTION | FLASHW_TRAY)
FLASHW_TIMERNOFG = 0x0000000C


class FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("hwnd", ctypes.c_void_p),
        ("dwFlags", ctypes.c_uint),
        ("uCount", ctypes.c_uint),
        ("dwTimeout", ctypes.c_uint)
    ]


def flash_window(hwnd):
    """Flash the window in the taskbar to get user attention."""
    try:
        finfo = FLASHWINFO()
        finfo.cbSize = ctypes.sizeof(FLASHWINFO)
        finfo.hwnd = hwnd
        finfo.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
        finfo.uCount = 0
        finfo.dwTimeout = 0
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(finfo))
    except Exception:
        pass


class SwitchPilot(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("550x750")
        self.minsize(500, 600)

        # Set window/taskbar icon
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "SwitchPilot.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SwitchPilot.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        # --- Application State ---
        self.obs_client = None
        self.is_tracking = False
        self.last_injected_exe = ""
        self.monitors = []
        self.suggested_app = None
        self.recording_folder = os.path.normpath(os.path.join(os.path.expanduser("~"), "Videos"))
        self.current_bitrate = 6000
        self.temp_ignore_list = []

        # Stats
        self.last_render_skipped = 0

        # Default Config
        self.detection_keys = ['w', 'a', 's', 'd']
        self.whitelist = []
        self.blacklist = [
            "explorer.exe", "python.exe", "SearchHost.exe",
            "Taskmgr.exe", "ApplicationFrameHost.exe",
            "chrome.exe", "discord.exe"
        ]
        self.detection_hotkey = "f9"
        self.detection_threshold = 2.0
        self.frame_drop_threshold = 30

        # Build UI
        self.setup_ui()
        self.detect_monitors()
        self.load_settings()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Start background threads
        threading.Thread(target=self.heuristic_loop, daemon=True).start()

        # Register global hotkey
        self._register_hotkey()

        # Auto-connect if password saved
        if self.entry_pass.get():
            threading.Thread(target=self.auto_connect_logic, daemon=True).start()

    def _register_hotkey(self):
        """Safely register the global hotkey."""
        try:
            keyboard.add_hotkey(self.detection_hotkey, self.quick_add_suggestion)
        except Exception as e:
            print(f"Could not register hotkey '{self.detection_hotkey}': {e}")

    def _unregister_hotkey(self):
        """Safely unregister the current hotkey."""
        try:
            keyboard.remove_hotkey(self.quick_add_suggestion)
        except Exception:
            pass

    # =========================================================================
    # UI SETUP
    # =========================================================================
    def setup_ui(self):
        # === STATUS HEADER ===
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.pack(pady=SPACE_SM, padx=SPACE_MD, fill="x")

        header_row = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        header_row.pack(fill="x")

        self.lbl_title = ctk.CTkLabel(
            header_row,
            text=APP_NAME,
            font=FONT_TITLE,
            text_color=COLOR_PRIMARY
        )
        self.lbl_title.pack(side="left")

        self.lbl_version = ctk.CTkLabel(
            header_row,
            text=f"v{APP_VERSION}",
            font=FONT_CAPTION,
            text_color=COLOR_MUTED
        )
        self.lbl_version.pack(side="left", padx=SPACE_SM)

        self.lbl_alert = ctk.CTkLabel(
            self.status_frame,
            text="SYSTEM NORMAL",
            font=FONT_HEADING,
            text_color=COLOR_MUTED
        )
        self.lbl_alert.pack(pady=SPACE_SM)

        # === TABS ===
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=SPACE_MD, pady=SPACE_SM)

        self.tab_dash = self.tabs.add("Dashboard")
        self.tab_rules = self.tabs.add("Rules")
        self.tab_settings = self.tabs.add("Settings")

        self._setup_dashboard_tab()
        self._setup_rules_tab()
        self._setup_settings_tab()

    def _setup_dashboard_tab(self):
        """Setup the main dashboard tab."""
        # Game Detection Banner (hidden by default)
        self.suggestion_frame = ctk.CTkFrame(self.tab_dash, fg_color=COLOR_ACCENT, corner_radius=8)

        ctk.CTkLabel(
            self.suggestion_frame,
            text="GAME DETECTED",
            text_color="white",
            font=FONT_HEADING
        ).pack(pady=(SPACE_MD, SPACE_XS))

        self.lbl_suggestion = ctk.CTkLabel(
            self.suggestion_frame,
            text="",
            text_color="white",
            font=FONT_BODY
        )
        self.lbl_suggestion.pack(pady=SPACE_XS)

        btn_box = ctk.CTkFrame(self.suggestion_frame, fg_color="transparent")
        btn_box.pack(pady=SPACE_MD)

        self.btn_add_quick = ctk.CTkButton(
            btn_box,
            text=f"Add ({self.detection_hotkey.upper()})",
            width=90,
            fg_color=COLOR_SUCCESS,
            hover_color="#16A34A",
            command=self.quick_add_suggestion
        )
        self.btn_add_quick.pack(side="left", padx=SPACE_XS)

        ctk.CTkButton(
            btn_box,
            text="Ignore Once",
            width=90,
            fg_color=COLOR_MUTED,
            hover_color="#4B5563",
            command=self.ignore_suggestion_once
        ).pack(side="left", padx=SPACE_XS)

        ctk.CTkButton(
            btn_box,
            text="Ignore Always",
            width=100,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_DARK,
            command=self.ignore_suggestion_always
        ).pack(side="left", padx=SPACE_XS)

        # Current App Display
        self.ctrl_frame = ctk.CTkFrame(self.tab_dash, fg_color=COLOR_SURFACE, corner_radius=8)
        self.ctrl_frame.pack(pady=SPACE_MD, padx=SPACE_MD, fill="x")

        ctk.CTkLabel(
            self.ctrl_frame,
            text="Currently Tracking",
            font=FONT_CAPTION,
            text_color=COLOR_MUTED
        ).pack(pady=(SPACE_MD, SPACE_XS))

        self.lbl_current_app = ctk.CTkLabel(
            self.ctrl_frame,
            text="Waiting...",
            font=FONT_HEADING,
            text_color=COLOR_PRIMARY
        )
        self.lbl_current_app.pack(pady=SPACE_XS)

        self.switch_track = ctk.CTkSwitch(
            self.ctrl_frame,
            text="Enable Auto-Tracking",
            font=FONT_BODY,
            command=self.toggle_tracking
        )
        self.switch_track.pack(pady=SPACE_MD)

        # Storage Info
        self.storage_frame = ctk.CTkFrame(self.tab_dash, fg_color=COLOR_SURFACE, corner_radius=8)
        self.storage_frame.pack(pady=SPACE_SM, padx=SPACE_MD, fill="x")

        self.lbl_path = ctk.CTkLabel(
            self.storage_frame,
            text="Recording path: Connect to OBS first",
            font=FONT_CAPTION,
            text_color=COLOR_MUTED
        )
        self.lbl_path.pack(pady=(SPACE_MD, SPACE_XS))

        self.storage_bar = ctk.CTkProgressBar(self.storage_frame, height=12, corner_radius=6)
        self.storage_bar.pack(pady=SPACE_SM, padx=SPACE_LG, fill="x")
        self.storage_bar.set(0)

        self.lbl_storage = ctk.CTkLabel(
            self.storage_frame,
            text="Not connected",
            font=FONT_SMALL
        )
        self.lbl_storage.pack(pady=(SPACE_XS, SPACE_MD))

    def _setup_rules_tab(self):
        """Setup the rules (whitelist/blacklist) tab."""
        self.rule_tabs = ctk.CTkTabview(self.tab_rules)
        self.rule_tabs.pack(fill="both", expand=True, padx=SPACE_XS, pady=SPACE_XS)

        self.sub_whitelist = self.rule_tabs.add("Whitelist (Games)")
        self.sub_blacklist = self.rule_tabs.add("Blacklist (Ignore)")

        self._setup_list_tab(self.sub_whitelist, "whitelist")
        self._setup_list_tab(self.sub_blacklist, "blacklist")

    def _setup_list_tab(self, parent, list_type):
        """Setup a whitelist or blacklist tab."""
        # Scan controls
        scan_frame = ctk.CTkFrame(parent, fg_color="transparent")
        scan_frame.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")

        combo_var = ctk.StringVar(value="Scan for running apps...")
        combo = ctk.CTkComboBox(scan_frame, variable=combo_var, width=250, font=FONT_BODY)
        combo.pack(side="left", padx=SPACE_SM, fill="x", expand=True)

        ctk.CTkButton(
            scan_frame,
            text="Scan",
            width=70,
            font=FONT_BODY,
            command=lambda: self.scan_running_apps(combo)
        ).pack(side="left", padx=SPACE_XS)

        # Add/Remove buttons
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=SPACE_SM)

        ctk.CTkButton(
            btn_row,
            text="Add Selected",
            width=120,
            font=FONT_BODY,
            command=lambda: self.add_from_combo(list_type, combo)
        ).pack(side="left", padx=SPACE_SM)

        ctk.CTkButton(
            btn_row,
            text="Remove",
            width=120,
            font=FONT_BODY,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_DARK,
            command=lambda: self.remove_from_list(list_type)
        ).pack(side="left", padx=SPACE_SM)

        # Display list
        textbox = ctk.CTkTextbox(parent, font=FONT_BODY, corner_radius=6, height=200)
        textbox.pack(pady=SPACE_SM, padx=SPACE_SM, fill="both", expand=True)
        textbox.configure(state="disabled")

        if list_type == "whitelist":
            self.white_display = textbox
            self.white_combo = combo
        else:
            self.black_display = textbox
            self.black_combo = combo

    def _setup_settings_tab(self):
        """Setup the settings tab."""
        # Scrollable container - use fill="x" only for children to prevent stretch
        self.scroll_settings = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        self.scroll_settings.pack(fill="both", expand=True)

        # --- Connection Section ---
        conn_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        conn_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")

        ctk.CTkLabel(
            conn_grp,
            text="OBS WebSocket Connection",
            font=FONT_HEADING
        ).pack(pady=SPACE_MD)

        self.entry_pass = ctk.CTkEntry(
            conn_grp,
            placeholder_text="WebSocket Password",
            show="*",
            font=FONT_BODY,
            height=36
        )
        self.entry_pass.pack(pady=SPACE_SM, padx=SPACE_LG, fill="x")

        self.btn_connect = ctk.CTkButton(
            conn_grp,
            text="Connect",
            font=FONT_BODY,
            height=36,
            command=lambda: threading.Thread(target=self.auto_connect_logic, daemon=True).start()
        )
        self.btn_connect.pack(pady=SPACE_SM)

        self.lbl_conn_status = ctk.CTkLabel(
            conn_grp,
            text="Disconnected",
            font=FONT_SMALL,
            text_color=COLOR_DANGER
        )
        self.lbl_conn_status.pack(pady=(SPACE_XS, SPACE_MD))

        # --- Source Selection ---
        src_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        src_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")

        ctk.CTkLabel(
            src_grp,
            text="OBS Source Targeting",
            font=FONT_HEADING
        ).pack(pady=SPACE_MD)

        # Monitor Row
        self._create_dropdown_row(
            src_grp,
            "Monitor:",
            "monitor_var",
            "monitor_menu",
            "Select Monitor",
            self.detect_monitors
        )

        # Video Source Row
        self._create_dropdown_row(
            src_grp,
            "Video Source:",
            "video_source_var",
            "video_source_menu",
            "Select Video Source...",
            self.refresh_sources
        )

        # Audio Source Row
        aud_row = ctk.CTkFrame(src_grp, fg_color="transparent")
        aud_row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)

        ctk.CTkLabel(aud_row, text="Audio Source:", font=FONT_BODY, width=100, anchor="w").pack(side="left")

        self.audio_source_var = ctk.StringVar(value="Select Audio Source...")
        self.audio_source_menu = ctk.CTkOptionMenu(
            aud_row,
            variable=self.audio_source_var,
            values=["Connect first..."],
            font=FONT_BODY
        )
        self.audio_source_menu.pack(side="left", fill="x", expand=True, padx=(SPACE_SM, 0))

        # Spacer
        ctk.CTkLabel(src_grp, text="").pack(pady=SPACE_XS)

        # --- Automation Preferences ---
        auto_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        auto_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")

        ctk.CTkLabel(
            auto_grp,
            text="Automation Preferences",
            font=FONT_HEADING
        ).pack(pady=SPACE_MD)

        self.auto_rec_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            auto_grp,
            text="Auto-start recording when game detected",
            font=FONT_BODY,
            variable=self.auto_rec_var
        ).pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")

        self.auto_fit_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            auto_grp,
            text="Auto-fit source to canvas",
            font=FONT_BODY,
            variable=self.auto_fit_var
        ).pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")

        # Hotkey Row
        hk_row = ctk.CTkFrame(auto_grp, fg_color="transparent")
        hk_row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)

        ctk.CTkLabel(hk_row, text="Quick-Add Hotkey:", font=FONT_BODY).pack(side="left")

        self.btn_record_hotkey = ctk.CTkButton(
            hk_row,
            text=f"{self.detection_hotkey.upper()}",
            width=80,
            font=FONT_BODY,
            fg_color=COLOR_MUTED,
            hover_color="#4B5563",
            command=self.start_hotkey_recording
        )
        self.btn_record_hotkey.pack(side="right")

        # Detection Timer Slider
        self._create_slider_row(
            auto_grp,
            "Detection delay:",
            "lbl_time_val",
            "slider_time",
            0.5, 5.0, 9,
            self.detection_threshold,
            self.update_timer_label,
            suffix="s"
        )

        # Frame Drop Slider
        self._create_slider_row(
            auto_grp,
            "Frame drop alert threshold:",
            "lbl_drop_val",
            "slider_drop",
            5, 100, 19,
            self.frame_drop_threshold,
            self.update_drop_label,
            suffix=""
        )

        # Spacer
        ctk.CTkLabel(auto_grp, text="").pack(pady=SPACE_XS)

        # --- Activity Keys ---
        key_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        key_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")

        ctk.CTkLabel(
            key_grp,
            text="Activity Detection Keys",
            font=FONT_HEADING
        ).pack(pady=SPACE_MD)

        ctk.CTkLabel(
            key_grp,
            text="Keys that trigger game detection when held",
            font=FONT_CAPTION,
            text_color=COLOR_MUTED
        ).pack()

        key_row = ctk.CTkFrame(key_grp, fg_color="transparent")
        key_row.pack(pady=SPACE_SM)

        self.entry_key = ctk.CTkEntry(
            key_row,
            placeholder_text="e.g. space, shift",
            width=150,
            font=FONT_BODY,
            height=32
        )
        self.entry_key.pack(side="left", padx=SPACE_SM)

        ctk.CTkButton(
            key_row,
            text="Add",
            width=60,
            font=FONT_BODY,
            height=32,
            command=self.add_detection_key
        ).pack(side="left", padx=SPACE_XS)

        ctk.CTkButton(
            key_row,
            text="Remove",
            width=70,
            font=FONT_BODY,
            height=32,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_DARK,
            command=self.remove_detection_key
        ).pack(side="left", padx=SPACE_XS)

        self.txt_keys = ctk.CTkTextbox(key_grp, height=50, font=FONT_BODY, corner_radius=6)
        self.txt_keys.pack(pady=(SPACE_SM, SPACE_MD), padx=SPACE_MD, fill="x")
        self.txt_keys.configure(state="disabled")
        self.update_key_display()

        # --- OBS Integration ---
        obs_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        obs_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")

        ctk.CTkLabel(
            obs_grp,
            text="OBS Integration",
            font=FONT_HEADING
        ).pack(pady=SPACE_MD)

        ctk.CTkLabel(
            obs_grp,
            text="Install a script to auto-launch SwitchPilot with OBS",
            font=FONT_CAPTION,
            text_color=COLOR_MUTED
        ).pack()

        self.btn_install_obs = ctk.CTkButton(
            obs_grp,
            text="Install OBS Script",
            font=FONT_BODY,
            height=36,
            command=self.install_obs_script
        )
        self.btn_install_obs.pack(pady=SPACE_MD)

        self.lbl_install_status = ctk.CTkLabel(
            obs_grp,
            text="",
            font=FONT_CAPTION,
            text_color=COLOR_MUTED
        )
        self.lbl_install_status.pack(pady=(0, SPACE_MD))

    def _create_dropdown_row(self, parent, label, var_name, menu_name, default, refresh_cmd):
        """Helper to create a labeled dropdown with refresh button."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)

        ctk.CTkLabel(row, text=label, font=FONT_BODY, width=100, anchor="w").pack(side="left")

        var = ctk.StringVar(value=default)
        setattr(self, var_name, var)

        menu = ctk.CTkOptionMenu(row, variable=var, values=["Scan first..."], font=FONT_BODY)
        menu.pack(side="left", fill="x", expand=True)
        setattr(self, menu_name, menu)

        ctk.CTkButton(
            row,
            text="Refresh",
            width=70,
            font=FONT_BODY,
            command=refresh_cmd
        ).pack(side="right", padx=(SPACE_SM, 0))

    def _create_slider_row(self, parent, label, lbl_name, slider_name, min_val, max_val, steps, default, cmd, suffix):
        """Helper to create a labeled slider row."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)

        ctk.CTkLabel(row, text=label, font=FONT_BODY).pack(side="left")

        display_val = f"{default:.1f}{suffix}" if suffix == "s" else f"{int(default)}"
        lbl = ctk.CTkLabel(row, text=display_val, font=FONT_BODY, width=40)
        lbl.pack(side="right")
        setattr(self, lbl_name, lbl)

        slider = ctk.CTkSlider(row, from_=min_val, to=max_val, number_of_steps=steps, command=cmd)
        slider.set(default)
        slider.pack(side="right", padx=SPACE_SM, fill="x", expand=True)
        setattr(self, slider_name, slider)

    # =========================================================================
    # HOTKEY RECORDING
    # =========================================================================
    def start_hotkey_recording(self):
        """Start listening for a new hotkey."""
        self.btn_record_hotkey.configure(text="Press key...", fg_color=COLOR_WARNING)
        threading.Thread(target=self._wait_for_hotkey, daemon=True).start()

    def _wait_for_hotkey(self):
        """Wait for user to press a key and set it as the hotkey."""
        try:
            event = keyboard.read_event(suppress=False)
            if event.event_type == keyboard.KEY_DOWN:
                new_key = event.name
                self._unregister_hotkey()
                self.detection_hotkey = new_key
                self._register_hotkey()

                self.btn_record_hotkey.configure(text=new_key.upper(), fg_color=COLOR_MUTED)
                self.btn_add_quick.configure(text=f"Add ({new_key.upper()})")
                self.save_settings()
        except Exception as e:
            self.btn_record_hotkey.configure(text="Error", fg_color=COLOR_DANGER)
            print(f"Hotkey recording error: {e}")

    # =========================================================================
    # SETTINGS UTILITIES
    # =========================================================================
    def add_detection_key(self):
        """Add a key to the detection keys list."""
        key = self.entry_key.get().lower().strip()
        if not key:
            return

        if key in self.detection_keys:
            self._show_entry_feedback(self.entry_key, "Already added")
            return

        self.detection_keys.append(key)
        self.entry_key.delete(0, "end")
        self.update_key_display()
        self.save_settings()

    def remove_detection_key(self):
        """Remove a key from the detection keys list."""
        key = self.entry_key.get().lower().strip()
        if key in self.detection_keys:
            self.detection_keys.remove(key)
            self.entry_key.delete(0, "end")
            self.update_key_display()
            self.save_settings()
        else:
            self._show_entry_feedback(self.entry_key, "Key not found")

    def _show_entry_feedback(self, entry, message):
        """Briefly show feedback in an entry field."""
        original = entry.get()
        entry.delete(0, "end")
        entry.configure(placeholder_text=message)
        self.after(1500, lambda: entry.configure(placeholder_text="e.g. space, shift"))

    def update_key_display(self):
        """Update the keys display textbox."""
        self.txt_keys.configure(state="normal")
        self.txt_keys.delete("0.0", "end")
        self.txt_keys.insert("end", ", ".join(self.detection_keys))
        self.txt_keys.configure(state="disabled")

    def update_timer_label(self, val):
        """Update the detection timer label."""
        self.lbl_time_val.configure(text=f"{val:.1f}s")
        self.detection_threshold = val

    def update_drop_label(self, val):
        """Update the frame drop threshold label."""
        val = int(val)
        self.lbl_drop_val.configure(text=f"{val}")
        self.frame_drop_threshold = val

    # =========================================================================
    # OBS SCRIPT INSTALLATION
    # =========================================================================
    def install_obs_script(self):
        """Install the OBS auto-launch script."""
        try:
            # Get the path to this executable/script
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.abspath(__file__)

            # Escape backslashes for Lua
            exe_path_escaped = exe_path.replace("\\", "\\\\")

            # Generate the Lua script content
            lua_script = f'''obs = obslua

-- SwitchPilot Auto-Launcher
-- This script launches SwitchPilot when OBS starts.

local app_path = "{exe_path_escaped}"

function script_description()
    return "Launches SwitchPilot automatically when OBS starts.\\n\\nPath: " .. app_path
end

function on_event(event)
    if event == obs.OBS_FRONTEND_EVENT_FINISHED_LOADING then
        obs.script_log(obs.LOG_INFO, "SwitchPilot: Launching...")
        os.execute('start "" "' .. app_path .. '"')
    end
end

function script_load(settings)
    obs.obs_frontend_add_event_callback(on_event)
end
'''

            # Find OBS scripts folder
            appdata = os.environ.get('APPDATA', '')
            obs_scripts_folder = os.path.join(appdata, 'obs-studio', 'basic', 'scripts')

            # Check if OBS folder exists
            if not os.path.exists(os.path.join(appdata, 'obs-studio')):
                self._show_install_error("OBS folder not found. Is OBS installed?")
                return

            # Create scripts folder if it doesn't exist
            os.makedirs(obs_scripts_folder, exist_ok=True)

            # Write the Lua script
            script_path = os.path.join(obs_scripts_folder, 'SwitchPilot_Launcher.lua')
            with open(script_path, 'w') as f:
                f.write(lua_script)

            self.lbl_install_status.configure(
                text=f"Installed! Now add it in OBS:\nTools > Scripts > + > SwitchPilot_Launcher.lua",
                text_color=COLOR_SUCCESS
            )

        except PermissionError:
            self._show_install_error("Permission denied. Try running as administrator.")
        except Exception as e:
            self._show_install_error(f"Install failed: {str(e)[:50]}")

    def _show_install_error(self, message):
        """Show install error with manual instructions."""
        self.lbl_install_status.configure(
            text=f"{message}\nSee README for manual install instructions.",
            text_color=COLOR_DANGER
        )

    # =========================================================================
    # SUGGESTION LOGIC
    # =========================================================================
    def show_suggestion(self, exe_name):
        """Show the game detection suggestion banner."""
        if not self.suggestion_frame.winfo_ismapped():
            self.lbl_suggestion.configure(text=exe_name)
            self.suggestion_frame.pack(before=self.ctrl_frame, pady=SPACE_MD, padx=SPACE_MD, fill="x")
            self._notify_user()

    def hide_suggestion(self):
        """Hide the suggestion banner."""
        self.suggestion_frame.pack_forget()
        self.suggested_app = None

    def ignore_suggestion_once(self):
        """Ignore the current suggestion for this session."""
        if self.suggested_app:
            self.temp_ignore_list.append(self.suggested_app)
            self.hide_suggestion()

    def ignore_suggestion_always(self):
        """Add the current suggestion to the permanent blacklist."""
        if self.suggested_app:
            self.blacklist.append(self.suggested_app)
            self.update_display("blacklist")
            self.save_settings()
            self.hide_suggestion()

    def quick_add_suggestion(self):
        """Add the suggested app to the whitelist and start tracking."""
        if self.suggested_app and self.suggested_app not in self.whitelist:
            self.whitelist.append(self.suggested_app)
            self.update_display("whitelist")
            self.save_settings()
            self.hide_suggestion()

            # Immediately switch if the app is still active
            exe, title, cls, _ = self.get_window_info()
            if exe == self.suggested_app:
                self.update_obs(exe, title, cls)

    def _notify_user(self):
        """Flash window and play sound to notify user."""
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            flash_window(hwnd)
        except Exception:
            pass

    # =========================================================================
    # HEURISTIC LOOP (Game Detection)
    # =========================================================================
    def heuristic_loop(self):
        """Background loop that detects game activity based on key presses."""
        activity_timer = 0

        while True:
            threshold = self.detection_threshold
            is_active = False

            for key in self.detection_keys:
                try:
                    if keyboard.is_pressed(key):
                        is_active = True
                        break
                except Exception:
                    pass

            if is_active:
                activity_timer += 0.1
            else:
                activity_timer = 0

            if activity_timer > threshold:
                exe, title, cls, _ = self.get_window_info()
                is_whitelisted = exe in self.whitelist
                is_blacklisted = exe in self.blacklist
                is_temp_ignored = exe in self.temp_ignore_list

                if exe and not is_whitelisted and not is_blacklisted and not is_temp_ignored:
                    self.suggested_app = exe
                    if self.lbl_suggestion.cget("text") != exe:
                        self.show_suggestion(exe)
                else:
                    self.hide_suggestion()

            time.sleep(0.1)

    # =========================================================================
    # CORE FUNCTIONS
    # =========================================================================
    def auto_connect_logic(self):
        """Attempt to connect to OBS WebSocket with retries."""
        max_retries = 5
        password = self.entry_pass.get()

        if not password:
            self.lbl_conn_status.configure(text="Enter password first", text_color=COLOR_WARNING)
            return

        for attempt in range(max_retries):
            try:
                self.lbl_conn_status.configure(
                    text=f"Connecting... ({attempt + 1}/{max_retries})",
                    text_color=COLOR_WARNING
                )
                self.obs_client = obs.ReqClient(host='localhost', port=4455, password=password)
                self._on_connect_success()
                return

            except Exception as e:
                error_msg = str(e).lower()

                if "authentication failed" in error_msg:
                    self.lbl_conn_status.configure(text="Incorrect password", text_color=COLOR_DANGER)
                    return
                elif "connection refused" in error_msg:
                    self.lbl_conn_status.configure(text="OBS not running or WebSocket disabled", text_color=COLOR_DANGER)
                    return

                time.sleep(1)

        self.lbl_conn_status.configure(text="Connection failed - is OBS running?", text_color=COLOR_DANGER)

    def _on_connect_success(self):
        """Handle successful OBS connection."""
        self.lbl_conn_status.configure(text="Connected", text_color=COLOR_SUCCESS)
        self.refresh_sources()

        # Try to get OBS config
        for _ in range(3):
            if self._get_obs_config():
                break
            time.sleep(1)

        self.check_disk_space()
        self.save_settings()

        try:
            stats = self.obs_client.get_stats()
            self.last_render_skipped = stats.render_skipped_frames
        except Exception:
            pass

        # Resume auto-tracking if it was enabled before
        if getattr(self, '_pending_auto_tracking', False):
            self._pending_auto_tracking = False
            self.switch_track.select()
            self.is_tracking = True
            threading.Thread(target=self.tracking_loop, daemon=True).start()

    def refresh_sources(self):
        """Refresh the list of available OBS sources."""
        if not self.obs_client:
            return

        try:
            resp = self.obs_client.get_input_list()

            inputs = []
            raw_list = resp.inputs if hasattr(resp, 'inputs') else resp

            for item in raw_list:
                name = (
                    getattr(item, 'inputName', None) or
                    getattr(item, 'input_name', None) or
                    item.get('inputName') or
                    item.get('input_name')
                )
                if name:
                    inputs.append(name)

            if inputs:
                self.video_source_menu.configure(values=inputs)
                self.audio_source_menu.configure(values=inputs)

                if self.video_source_var.get() not in inputs:
                    self.video_source_var.set("Select Video Source...")
                if self.audio_source_var.get() not in inputs:
                    self.audio_source_var.set("Select Audio Source...")
            else:
                self.video_source_var.set("No sources found")
                self.audio_source_var.set("No sources found")

        except Exception as e:
            print(f"Error refreshing sources: {e}")
            self.video_source_var.set("Error loading sources")

    def check_disk_space(self):
        """Check available disk space for recordings."""
        try:
            clean_path = os.path.normpath(self.recording_folder)
            self.lbl_path.configure(text=f"Recording to: {clean_path}")

            if not os.path.exists(clean_path):
                self.lbl_storage.configure(text=f"Path not found: {clean_path}", text_color=COLOR_DANGER)
                return

            total, used, free = shutil.disk_usage(clean_path)
            free_gb = free / (1024 ** 3)
            percent_free = free / total
            self.storage_bar.set(percent_free)

            # Calculate recording time remaining
            total_bitrate = self.current_bitrate + 320  # Video + Audio bitrate
            if total_bitrate <= 0:
                total_bitrate = 6000
            minutes_left = (free_gb * 1024 * 1024 * 8) / (total_bitrate * 60)
            time_str = f"~{int(minutes_left // 60)}h {int(minutes_left % 60)}m recording time"

            if free_gb < 10:
                self.storage_bar.configure(progress_color=COLOR_DANGER)
                self.lbl_storage.configure(text=f"Critical: {free_gb:.1f} GB ({time_str})", text_color=COLOR_DANGER)
            elif free_gb < 50:
                self.storage_bar.configure(progress_color=COLOR_WARNING)
                self.lbl_storage.configure(text=f"Low: {free_gb:.1f} GB ({time_str})", text_color=COLOR_WARNING)
            else:
                self.storage_bar.configure(progress_color=COLOR_SUCCESS)
                self.lbl_storage.configure(text=f"{free_gb:.1f} GB available ({time_str})", text_color=COLOR_MUTED)

        except Exception as e:
            self.lbl_storage.configure(text=f"Error checking disk: {e}", text_color=COLOR_DANGER)

    def _get_obs_config(self):
        """Get OBS recording directory configuration."""
        if not self.obs_client:
            return False

        try:
            resp_dir = self.obs_client.get_record_directory()
            directory = getattr(resp_dir, 'record_directory', None) or getattr(resp_dir, 'recordDirectory', None)
            if directory:
                self.recording_folder = os.path.normpath(directory)
                return True
        except Exception as e:
            print(f"Error getting OBS config: {e}")

        return False

    def update_obs(self, exe_name, window_title, class_name):
        """Update OBS sources to capture the specified window."""
        if not self.obs_client:
            return

        vid = self.video_source_var.get()
        aud = self.audio_source_var.get()
        target = f"{window_title}:{class_name}:{exe_name}"

        try:
            # Update Video Source
            if vid and "Select" not in vid:
                self.obs_client.set_input_settings(
                    name=vid,
                    settings={"capture_mode": "window", "window": target, "priority": 1},
                    overlay=True
                )

                # Auto-fit if enabled
                if self.auto_fit_var.get():
                    self._auto_fit_source(vid)

                # Validate hook in background
                threading.Thread(target=self._validate_hook, args=(vid,), daemon=True).start()

            # Update Audio Source
            if aud and "Select" not in aud:
                self.obs_client.set_input_settings(
                    name=aud,
                    settings={"window": target, "priority": 1},
                    overlay=True
                )
                # Toggle to refresh audio capture
                self.obs_client.set_input_settings(name=aud, settings={"enabled": False}, overlay=True)
                time.sleep(0.05)
                self.obs_client.set_input_settings(name=aud, settings={"enabled": True}, overlay=True)

            # Auto-Record
            if self.auto_rec_var.get():
                if not self.obs_client.get_record_status().output_active:
                    self.obs_client.start_record()

        except Exception as e:
            print(f"Error updating OBS: {e}")
            self.lbl_current_app.configure(text=f"OBS Error: {str(e)[:30]}", text_color=COLOR_DANGER)

    def _auto_fit_source(self, source_name):
        """Auto-fit a source to fill the canvas."""
        try:
            current_scene = self.obs_client.get_current_program_scene().current_program_scene_name
            items = self.obs_client.get_scene_item_list(current_scene).scene_items
            item_id = next((i['sceneItemId'] for i in items if i['sourceName'] == source_name), None)

            if item_id:
                res = self.obs_client.get_video_settings()
                transform = {
                    "boundsAlignment": 0,
                    "boundsWidth": res.base_width,
                    "boundsHeight": res.base_height,
                    "boundsType": "OBS_BOUNDS_SCALE_INNER"
                }
                self.obs_client.set_scene_item_transform(current_scene, item_id, transform)
        except Exception as e:
            print(f"Auto-fit error: {e}")

    def _validate_hook(self, source_name):
        """Validate that the source hook was successful."""
        time.sleep(2.0)
        try:
            active = self.obs_client.get_source_active(source_name).video_active
            if not active:
                self.lbl_current_app.configure(text="Capture failed - try running as Admin", text_color=COLOR_DANGER)
                self._notify_user()
        except Exception:
            pass

    def tracking_loop(self):
        """Main tracking loop that monitors active windows."""
        check_counter = 0

        while self.is_tracking:
            self.check_overload()

            # Check disk space every 15 seconds
            if check_counter % 10 == 0:
                self.check_disk_space()
            check_counter += 1

            exe, title, cls, monitor_handle = self.get_window_info()

            if exe:
                selected_monitor = self.monitor_var.get()
                expected_handle = next(
                    (m['handle'] for m in self.monitors if m['name'] == selected_monitor),
                    None
                )
                is_correct_monitor = (monitor_handle == expected_handle)

                is_whitelisted = exe in self.whitelist
                is_blacklisted = exe in self.blacklist
                is_temp_ignored = exe in self.temp_ignore_list

                # Determine if we should track this app
                allowed = False
                if self.whitelist:
                    allowed = is_whitelisted
                else:
                    allowed = not is_blacklisted and not is_temp_ignored

                # Update status label
                if "failed" not in self.lbl_current_app.cget("text").lower():
                    status = "Tracking" if is_correct_monitor and allowed else "Ignored"
                    self.lbl_current_app.configure(
                        text=f"{exe} ({status})",
                        text_color=COLOR_PRIMARY if allowed else COLOR_MUTED
                    )

                # Switch sources if needed
                if is_correct_monitor and allowed and exe != self.last_injected_exe:
                    self.update_obs(exe, title, cls)
                    self.last_injected_exe = exe

            time.sleep(1.5)

    def check_overload(self):
        """Check for dropped frames and alert user."""
        if not self.obs_client:
            return

        try:
            stats = self.obs_client.get_stats()
            diff = stats.render_skipped_frames - self.last_render_skipped
            self.last_render_skipped = stats.render_skipped_frames

            if diff > self.frame_drop_threshold:
                self.lbl_alert.configure(text=f"Dropped {diff} frames!", text_color=COLOR_DANGER)
                self.status_frame.configure(fg_color=COLOR_DANGER_DARK)
                self._notify_user()
            elif diff > 0:
                self.lbl_alert.configure(text=f"Minor stutter ({diff} frames)", text_color=COLOR_WARNING)
                self.status_frame.configure(fg_color="transparent")
            else:
                self.lbl_alert.configure(text="SYSTEM NORMAL", text_color=COLOR_MUTED)
                self.status_frame.configure(fg_color="transparent")

        except Exception:
            pass

    def get_window_info(self):
        """Get information about the current foreground window."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0:
                return None, None, None, None

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe_name = psutil.Process(pid).name()
            window_title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL)

            return exe_name, window_title, class_name, monitor

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None, None, None, None
        except Exception:
            return None, None, None, None

    def scan_running_apps(self, combo_widget):
        """Scan for visible windows and populate the combo box."""
        apps = []

        def enum_handler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        exe_name = psutil.Process(pid).name()
                        apps.append(f"{title} ({exe_name})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

        try:
            win32gui.EnumWindows(enum_handler, None)
            apps.sort()
            combo_widget.configure(values=apps)
            if apps:
                combo_widget.set(apps[0])
            else:
                combo_widget.set("No apps found")
        except Exception as e:
            combo_widget.set(f"Scan error: {e}")

    def add_from_combo(self, list_type, combo_widget):
        """Add the selected app from combo to whitelist or blacklist."""
        selection = combo_widget.get()
        exe = selection.split("(")[-1].strip(")") if "(" in selection else selection.strip()

        target = self.whitelist if list_type == "whitelist" else self.blacklist

        if exe and exe not in target:
            target.append(exe)
            self.update_display(list_type)
            self.save_settings()

    def remove_from_list(self, list_type):
        """Remove the selected app from whitelist or blacklist."""
        combo = self.white_combo if list_type == "whitelist" else self.black_combo
        selection = combo.get()
        value = selection.split("(")[-1].strip(")") if "(" in selection else selection.strip()

        target = self.whitelist if list_type == "whitelist" else self.blacklist

        if value in target:
            target.remove(value)
            self.update_display(list_type)
            self.save_settings()

    def update_display(self, list_type):
        """Update the whitelist or blacklist display."""
        target = self.whitelist if list_type == "whitelist" else self.blacklist
        display = self.white_display if list_type == "whitelist" else self.black_display

        display.configure(state="normal")
        display.delete("0.0", "end")
        for app in target:
            display.insert("end", f"  {app}\n")
        display.configure(state="disabled")

    def detect_monitors(self):
        """Detect connected monitors."""
        try:
            self.monitors = []
            display_names = []

            for i, (handle, _, rect) in enumerate(win32api.EnumDisplayMonitors()):
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                name = f"Monitor {i + 1} ({width}x{height})"
                self.monitors.append({"handle": handle, "name": name})
                display_names.append(name)

            if hasattr(self, 'monitor_menu'):
                self.monitor_menu.configure(values=display_names)
                if display_names and self.monitor_var.get() == "Select Monitor":
                    self.monitor_var.set(display_names[0])

        except Exception as e:
            print(f"Error detecting monitors: {e}")

    # =========================================================================
    # SETTINGS PERSISTENCE
    # =========================================================================
    def save_settings(self):
        """Save settings to config file."""
        data = {
            "version": APP_VERSION,
            "password": self.entry_pass.get(),
            "monitor": self.monitor_var.get(),
            "video_source": self.video_source_var.get(),
            "audio_source": self.audio_source_var.get(),
            "auto_record": self.auto_rec_var.get(),
            "auto_fit": self.auto_fit_var.get(),
            "auto_tracking": self.switch_track.get() == 1,
            "hotkey": self.detection_hotkey,
            "detection_keys": self.detection_keys,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "detection_threshold": self.detection_threshold,
            "frame_drop_threshold": self.frame_drop_threshold
        }

        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        """Load settings from config file."""
        if not os.path.exists(CONFIG_FILE):
            # Check for old config file and migrate
            old_config = os.path.join(app_dir, "obs_tracker_config.json")
            if os.path.exists(old_config):
                try:
                    os.rename(old_config, CONFIG_FILE)
                except Exception:
                    pass

        if not os.path.exists(CONFIG_FILE):
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)

            if "password" in data:
                self.entry_pass.insert(0, data["password"])

            if "monitor" in data:
                if any(data["monitor"] in m["name"] for m in self.monitors):
                    self.monitor_var.set(data["monitor"])

            if "video_source" in data:
                self.video_source_var.set(data["video_source"])

            if "audio_source" in data:
                self.audio_source_var.set(data["audio_source"])

            if "auto_record" in data:
                self.auto_rec_var.set(data["auto_record"])

            if "auto_fit" in data:
                self.auto_fit_var.set(data["auto_fit"])

            if "whitelist" in data:
                self.whitelist = data["whitelist"]

            if "blacklist" in data:
                self.blacklist = data["blacklist"]

            if "hotkey" in data:
                self.detection_hotkey = data["hotkey"]
                self.btn_record_hotkey.configure(text=self.detection_hotkey.upper())
                self.btn_add_quick.configure(text=f"Add ({self.detection_hotkey.upper()})")

            if "detection_keys" in data:
                self.detection_keys = data["detection_keys"]
                self.update_key_display()

            if "detection_threshold" in data:
                self.slider_time.set(data["detection_threshold"])
                self.detection_threshold = data["detection_threshold"]
                self.lbl_time_val.configure(text=f"{self.detection_threshold:.1f}s")

            if "frame_drop_threshold" in data:
                self.frame_drop_threshold = data["frame_drop_threshold"]
                self.slider_drop.set(self.frame_drop_threshold)
                self.lbl_drop_val.configure(text=f"{self.frame_drop_threshold}")

            if "auto_tracking" in data and data["auto_tracking"]:
                self._pending_auto_tracking = True

            self.update_display("whitelist")
            self.update_display("blacklist")

        except json.JSONDecodeError:
            print("Config file corrupted. Starting with defaults.")
            try:
                os.remove(CONFIG_FILE)
            except Exception:
                pass

        except Exception as e:
            print(f"Error loading settings: {e}")

    def on_close(self):
        """Handle window close event."""
        self.save_settings()
        self.destroy()

    def toggle_tracking(self):
        """Toggle auto-tracking on/off."""
        if self.switch_track.get() == 1:
            if not self.obs_client:
                self.lbl_current_app.configure(text="Connect to OBS first", text_color=COLOR_WARNING)
                self.switch_track.deselect()
                return

            self.is_tracking = True
            threading.Thread(target=self.tracking_loop, daemon=True).start()
        else:
            self.is_tracking = False
            self.lbl_current_app.configure(text="Paused", text_color=COLOR_MUTED)
            self.lbl_alert.configure(text="SYSTEM NORMAL", text_color=COLOR_MUTED)


if __name__ == "__main__":
    app = SwitchPilot()
    app.mainloop()
