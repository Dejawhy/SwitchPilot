import customtkinter as ctk
import obsws_python as obs
import win32gui
from tkinter import messagebox, filedialog
import win32process
import win32api
import win32con
import win32event  
import winerror    
import psutil
import threading
import time
import json
import os
import sys
import keyboard
import shutil
import winsound
import wave
import audioop
import io
import ctypes
from PIL import Image


#Resource Path Helper 
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller exe."""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

APP_NAME = "HotSwap"
APP_VERSION = "1.0" 


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")
ctk.ThemeManager.theme["CTkButton"]["fg_color"] = ["#9146FF", "#9146FF"]
ctk.ThemeManager.theme["CTkButton"]["hover_color"] = ["#772CE8", "#772CE8"]

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

COLOR_PRIMARY = "#9146FF"
COLOR_SUCCESS = "#22C55E"
COLOR_WARNING = "#F59E0B"
COLOR_DANGER = "#EF4444"
COLOR_DANGER_DARK = "#991B1B"
COLOR_ACCENT = "#F59E0B"
COLOR_MUTED = "#6B7280"
COLOR_SURFACE = "#1F1F1F"

FONT_TITLE = ("Segoe UI", 24, "bold")
FONT_HEADING = ("Segoe UI", 16, "bold")
FONT_BODY = ("Segoe UI", 16, "bold")
FONT_SMALL = ("Segoe UI", 16, "bold")
FONT_CAPTION = ("Segoe UI", 16, "bold")

app_data_dir = os.path.join(os.environ['APPDATA'], "HotSwap")
if not os.path.exists(app_data_dir):
    try:
        os.makedirs(app_data_dir)
    except Exception:
        pass
CONFIG_FILE = os.path.join(app_data_dir, "config.json")

# ... [Keep Flash Window Helpers] ...
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

# Win32 Constants
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WDA_EXCLUDEFROMCAPTURE = 0x00000011
GetWindowLong = ctypes.windll.user32.GetWindowLongW
SetWindowLong = ctypes.windll.user32.SetWindowLongW
SetWindowDisplayAffinity = ctypes.windll.user32.SetWindowDisplayAffinity

class OverlayPopup:
    TYPE_GAME_DETECTED = "game_detected"
    TYPE_FRAME_DROP = "frame_drop"
    TYPE_CAPTURE_FAILED = "capture_failed"
    TYPE_ASPECT_RATIO = "aspect_mismatch"

    def __init__(self, parent):
        self.parent = parent
        self.popup = None
        self.auto_dismiss_id = None
        self.overlay_type = None
        self.logo_image = None
        self.popup_queue = []
        self._load_logo()
        self.current_message = "" 

    def _load_logo(self):
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(sys._MEIPASS, "HotSwap.ico")
            else:
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HotSwap.ico")

            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                img = img.resize((48, 48), Image.Resampling.LANCZOS)
                self.logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=(48, 48))
        except Exception as e:
            print(f"Could not load logo: {e}")
            self.logo_image = None

    def clear_queue(self):
        """Clears all pending popups. Use when user has taken action."""
        self.popup_queue.clear()

    def show(self, title, message, hotkey="F9", duration=10000, overlay_type=None):
        """Show the overlay popup, with deduplication logic."""
        
        # dupelication prevention logic
        if self.popup is not None and self.current_message == message:
            return

        for item in self.popup_queue:
            if item['message'] == message:
                return
        # ----------------------------

        # If a different popup is currently showing, queue this new one
        if self.popup is not None:
            self.popup_queue.append({
                'title': title,
                'message': message,
                'hotkey': hotkey,
                'duration': duration,
                'overlay_type': overlay_type
            })
            return

        self.overlay_type = overlay_type
        self.current_message = message 

        self.popup = ctk.CTkToplevel(self.parent)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        self.popup.configure(fg_color="#000001")
        self.popup.attributes("-transparentcolor", "#000001")

        if overlay_type == self.TYPE_FRAME_DROP or overlay_type == self.TYPE_CAPTURE_FAILED:
            title_color = COLOR_DANGER
        elif overlay_type == self.TYPE_ASPECT_RATIO:
            title_color = COLOR_WARNING
        else:
            title_color = COLOR_ACCENT

        frame = ctk.CTkFrame(self.popup, fg_color="#1a1a1a", corner_radius=20)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        if self.logo_image:
            ctk.CTkLabel(frame, image=self.logo_image, text="").pack(pady=(20, 5), anchor="center")

        ctk.CTkLabel(frame, text="HotSwap", font=("Segoe UI", 16, "bold"), text_color=COLOR_MUTED).pack(anchor="center")
        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 28, "bold"), text_color=title_color).pack(pady=(0, 10), anchor="center")
        ctk.CTkLabel(frame, text=message, font=("Segoe UI", 36, "bold"), text_color="#FFFFFF", wraplength=600, justify="center").pack(pady=(0, 15), padx=40, anchor="center")

        ignore_key = getattr(self.parent, 'ignore_alerts_hotkey', 'i').upper()

        if overlay_type == self.TYPE_GAME_DETECTED:
            ctk.CTkLabel(frame, text=f"{hotkey.upper()} Add to whitelist", font=("Segoe UI", 16, "bold"), text_color=COLOR_SUCCESS).pack(pady=(0, 2), anchor="center")
            ctk.CTkLabel(frame, text=f"{ignore_key} Dismiss", font=("Segoe UI", 16, "bold"), text_color="#9E0000").pack(pady=(0, 5), anchor="center")
        elif overlay_type == self.TYPE_FRAME_DROP:
            ctk.CTkLabel(frame, text=f"{ignore_key} Disable alerts", font=("Segoe UI", 16, "bold"), text_color="#9E0000").pack(pady=(0, 5), anchor="center")
        elif overlay_type == self.TYPE_CAPTURE_FAILED:
            ctk.CTkLabel(frame, text="Run as Administrator to fix", font=("Segoe UI", 16, "bold"), text_color=COLOR_MUTED).pack(pady=(0, 5), anchor="center")
        elif overlay_type == self.TYPE_ASPECT_RATIO:
            ctk.CTkLabel(frame, text="Black bars detected on stream", font=("Segoe UI", 16, "bold"), text_color=COLOR_MUTED).pack(pady=(0, 5), anchor="center")

        ctk.CTkLabel(frame, text=f"Auto-dismiss in {duration // 1000}s", font=("Segoe UI", 16, "bold"), text_color="#CDCF44").pack(pady=(0, 20), anchor="center")

        self.popup.update_idletasks()
        screen_width = self.popup.winfo_screenwidth()
        screen_height = self.popup.winfo_screenheight()
        popup_width = self.popup.winfo_reqwidth()
        popup_height = self.popup.winfo_reqheight()
        x = screen_width - popup_width - 30
        y = screen_height - popup_height - 80
        self.popup.geometry(f"+{x}+{y}")
        self.popup.attributes("-topmost", True)
        self.popup.attributes("-alpha", 0.95)
        self.popup.deiconify()
        self.popup.update()

        self._apply_win32_flags()

        if overlay_type == self.TYPE_GAME_DETECTED:
            self.auto_dismiss_id = self.popup.after(duration, self.parent.hide_suggestion)
        else:
            self.auto_dismiss_id = self.popup.after(duration, self.hide)

    def is_frame_drop_alert(self):
        return self.overlay_type == self.TYPE_FRAME_DROP and self.popup is not None

    def is_game_detected_alert(self):
        return self.overlay_type == self.TYPE_GAME_DETECTED and self.popup is not None

    def _apply_win32_flags(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.popup.winfo_id())
            if not hwnd: hwnd = self.popup.winfo_id()
            style = GetWindowLong(hwnd, GWL_EXSTYLE)
            new_style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            SetWindowLong(hwnd, GWL_EXSTYLE, new_style)
        except Exception:
            pass

    def hide(self):
        if self.auto_dismiss_id and self.popup:
            try:
                self.popup.after_cancel(self.auto_dismiss_id)
            except Exception:
                pass
            self.auto_dismiss_id = None

        if self.popup:
            try:
                self.popup.destroy()
            except Exception:
                pass
            self.popup = None
            self.current_message = "" 

        if self.popup_queue:
            next_popup = self.popup_queue.pop(0)
            self.parent.after(100, lambda: self._show_queued(next_popup))

    def _show_queued(self, popup_data):
        self.show(
            title=popup_data['title'],
            message=popup_data['message'],
            hotkey=popup_data['hotkey'],
            duration=popup_data['duration'],
            overlay_type=popup_data['overlay_type']
        )


class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, message, danger_action=False):
        super().__init__(parent)
        self.result = False
        self.title(title)
        self.geometry("400x200")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        if hasattr(parent, 'icon_path') and os.path.exists(parent.icon_path):
            self.after(200, lambda: self.iconbitmap(parent.icon_path))
        
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + (parent_width // 2) - 200
        y = parent_y + (parent_height // 2) - 100
        self.geometry(f"+{x}+{y}")

        self.frame = ctk.CTkFrame(self, fg_color="#1a1a1a", corner_radius=0)
        self.frame.pack(fill="both", expand=True)

        ctk.CTkLabel(self.frame, text=title, font=("Segoe UI", 20, "bold"), text_color="#FFFFFF").pack(pady=(20, 10))
        ctk.CTkLabel(self.frame, text=message, font=("Segoe UI", 16), text_color="#CCCCCC", wraplength=350).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        btn_frame.pack(pady=10)

        ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="#4B5563", hover_color="#374151", command=self.on_cancel).pack(side="left", padx=10)
        confirm_color = "#EF4444" if danger_action else "#22C55E"
        confirm_hover = "#991B1B" if danger_action else "#16A34A"
        confirm_text = "Clear All" if danger_action else "Confirm"
        ctk.CTkButton(btn_frame, text=confirm_text, width=100, fg_color=confirm_color, hover_color=confirm_hover, command=self.on_confirm).pack(side="left", padx=10)

        self.transient(parent)
        self.grab_set()
        self.wait_window()

    def on_confirm(self):
        self.result = True
        self.destroy()

    def on_cancel(self):
        self.result = False
        self.destroy()

class Tooltip:
    def __init__(self, widget, text, delay=800):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.scheduled_id = None
        widget.bind("<Enter>", self._schedule_show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<Button-1>", self._hide)

    def _schedule_show(self, event=None):
        self._hide()
        self.scheduled_id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self.tooltip_window: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tooltip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        frame = ctk.CTkFrame(tw, fg_color="#333333", corner_radius=6)
        frame.pack()
        ctk.CTkLabel(frame, text=self.text, font=("Segoe UI", 16, "bold"), text_color="#FFFFFF", wraplength=250, justify="left").pack(padx=8, pady=6)

    def _hide(self, event=None):
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class HotSwap(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("550x750")
        self.minsize(500, 600)
        self.attributes("-topmost", True)
        
        if getattr(sys, 'frozen', False):
            self.icon_path = os.path.join(sys._MEIPASS, "HotSwap.ico")
        else:
            self.icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HotSwap.ico")
        if os.path.exists(self.icon_path):
            self.iconbitmap(self.icon_path)

        self.obs_client = None
        self.is_tracking = False
        self.last_injected_exe = ""
        self.last_obs_target = ""
        self.monitors = []
        self.monitor_var = ctk.StringVar(value="")
        self.suggested_app = None
        self.suggested_title = None
        self.suggested_class = None
        self.recording_folder = os.path.normpath(os.path.join(os.path.expanduser("~"), "Videos"))
        self.current_bitrate = 6000
        self.temp_ignore_list = []
        self.locked_app = None
        self.overlay = OverlayPopup(self)
        self.self_exe = "HotSwap.exe" if getattr(sys, 'frozen', False) else "python.exe"
        self.last_render_skipped = 0

        self.demo_mode = False # Demo mode flag for testing

        self.detection_keys = ['w', 'a', 's', 'd']
        self.whitelist = []
        self.blacklist = ["explorer.exe", "python.exe", "SearchHost.exe", "Taskmgr.exe", "ApplicationFrameHost.exe", "chrome.exe", "discord.exe"]
        self.anticheat_games = ["valorant.exe", "vgc.exe", "faceitclient.exe", "faceit.exe", "easyanticheat.exe", "battleye.exe", "beclient.exe", "r5apex.exe", "fortnite.exe", "fortniteclient-win64-shipping.exe"]
        self.anticheat_suggested = False
        self.detection_hotkey = "f9"
        self.toggle_tracking_hotkey = "f10"
        self.ignore_alerts_hotkey = "i"
        self.detection_threshold = 2.0
        self.frame_drop_threshold = 30
        self.game_detection_enabled = True
        self.total_swaps = 0
        self.frame_drop_alerts_enabled = True
        self.disclaimer_accepted = False
        self.current_scene_collection = None
        self.scene_collection_sources = {}
        self.audio_feedback_enabled = True
        self.popup_notifications_enabled = True
        self.audio_volume = 0.5
        self.sound_detected_path = ""
        self.sound_switched_path = ""
        self.default_sound_detected = resource_path("sounds/detected.wav")
        self.default_sound_switched = resource_path("sounds/switched.wav")

        self.setup_ui()
        self.load_settings()
        
        threading.Thread(target=self.install_obs_script, kwargs={'silent': True}, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(500, self._hide_from_capture)
        
        if self.game_detection_enabled:
            threading.Thread(target=self.heuristic_loop, daemon=True).start()

        self._register_hotkeys()
        
        if self.entry_pass.get():
            threading.Thread(target=self.auto_connect_logic, daemon=True).start()
        else:
            self.tabs.set("Settings")
            self.after(1000, self.show_onboarding)

    def show_onboarding(self):
        guide = ctk.CTkToplevel(self)
        guide.title("Welcome to HotSwap")
        guide.geometry("500x450")
        guide.resizable(False, False)
        if hasattr(self, 'icon_path') and os.path.exists(self.icon_path):
            guide.after(200, lambda: guide.iconbitmap(self.icon_path))
        guide.transient(self)
        guide.lift()
        guide.attributes("-topmost", True)
        self._center_toplevel(guide)

        frame = ctk.CTkFrame(guide, fg_color="#1a1a1a", corner_radius=16)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(frame, text="Let's Get Connected!", font=("Segoe UI", 24, "bold"), text_color=COLOR_PRIMARY).pack(pady=(20, 10))
        steps = ["1. Open OBS Studio", "2. Go to Tools > WebSocket Server Settings", "3. Check 'Enable WebSocket server'", "4. Set a password (e.g. 1234)", "5. Enter that password in HotSwap Settings"]
        for step in steps:
            ctk.CTkLabel(frame, text=step, font=("Segoe UI", 16), text_color="#DDDDDD", anchor="w").pack(pady=5, padx=40, fill="x")
        
        ctk.CTkLabel(frame, text="HotSwap needs this connection to\ncontrol your scenes automatically.", font=("Segoe UI", 14), text_color=COLOR_MUTED, justify="center").pack(pady=(20, 10))
        
        warning_frame = ctk.CTkFrame(frame, fg_color=COLOR_DANGER_DARK, corner_radius=6)
        warning_frame.pack(pady=(5, 0), padx=20, fill="x")
        ctk.CTkLabel(warning_frame, text="BETA WARNING: This is v1.0.\nBugs are expected. Happy swapping!", font=("Segoe UI", 12, "bold"), text_color="#FFDDDD").pack(pady=5)
        
        ctk.CTkButton(frame, text="I'm Ready!", font=("Segoe UI", 16, "bold"), height=40, fg_color=COLOR_SUCCESS, hover_color="#16A34A", command=guide.destroy).pack(pady=20)

    def _center_toplevel(self, window):
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        window.geometry(f"+{x}+{y}")

    def _register_hotkeys(self):
        try:
            keyboard.add_hotkey(self.detection_hotkey, self.quick_add_suggestion)
        except Exception: pass
        try:
            keyboard.add_hotkey(self.toggle_tracking_hotkey, self.toggle_tracking_hotkey_pressed)
        except Exception: pass
        try:
            keyboard.add_hotkey(self.ignore_alerts_hotkey, self._ignore_frame_drop_alerts)
        except Exception: pass
        try:
            keyboard.add_hotkey("shift+l+d", self.toggle_demo_mode) #demo mode toggle
        except Exception: pass
        
    def toggle_demo_mode(self):
        """Secret toggle for recording demo videos."""
        self.demo_mode = not self.demo_mode
        
        if self.demo_mode:
            self.title(f"{APP_NAME} v{APP_VERSION} [DEMO MODE]")
            self._show_for_capture()
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            print("!!! DEMO MODE ENABLED - OBS UPDATES DISABLED, VISIBLE TO CAPTURE !!!")
        else:
            self.title(f"{APP_NAME} v{APP_VERSION}")
            self._hide_from_capture()
            winsound.MessageBeep(winsound.MB_OK)
            print("!!! DEMO MODE DISABLED - LIVE !!!")

    def _unregister_hotkeys(self):
        try: keyboard.remove_hotkey(self.quick_add_suggestion)
        except Exception: pass
        try: keyboard.remove_hotkey(self.toggle_tracking_hotkey_pressed)
        except Exception: pass
        try: keyboard.remove_hotkey(self._ignore_frame_drop_alerts)
        except Exception: pass

    def _ignore_frame_drop_alerts(self):
        if self.overlay.is_frame_drop_alert():
            self.frame_drop_alerts_enabled = False
            self.frame_drop_var.set(False)
            self.overlay.hide()
            self.save_settings()
        elif self.overlay.is_game_detected_alert():
            self.ignore_suggestion_once()

    def toggle_tracking_hotkey_pressed(self):
        if self.switch_track.get() == 1:
            self.switch_track.deselect()
        else:
            self.switch_track.select()
        self.toggle_tracking()


    def setup_ui(self):
        # [Paste content of setup_ui]
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.pack(pady=SPACE_SM, padx=SPACE_MD, fill="x")
        header_row = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        header_row.pack(fill="x")
        try:
            logo_path = resource_path("hotswaplogoapp.png")
            logo_img = Image.open(logo_path)
            self.header_logo = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(143, 38))
            self.lbl_title = ctk.CTkLabel(header_row, image=self.header_logo, text="")
            self.lbl_title.pack(side="left")
        except Exception:
            self.lbl_title = ctk.CTkLabel(header_row, text=APP_NAME, font=FONT_TITLE, text_color=COLOR_PRIMARY)
            self.lbl_title.pack(side="left")
        self.lbl_version = ctk.CTkLabel(header_row, text=f"v{APP_VERSION}", font=FONT_CAPTION, text_color=COLOR_MUTED)
        self.lbl_version.pack(side="left", padx=SPACE_SM)
        ctk.CTkLabel(header_row, text="", width=10).pack(side="left", expand=True, fill="x")
        self.btn_pin = ctk.CTkButton(header_row, text="📌", font=("Segoe UI", 16), width=40, height=40, fg_color="#333333", text_color=COLOR_SUCCESS, hover_color="#333333", command=self.toggle_pin)
        self.btn_pin.pack(side="right", padx=0)
        self.pin_tooltip = Tooltip(self.btn_pin, "Unpin window")
        self.lbl_alert = ctk.CTkLabel(self.status_frame, text="SYSTEM NORMAL", font=FONT_HEADING, text_color=COLOR_MUTED)
        self.lbl_alert.pack(pady=SPACE_SM)
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=SPACE_MD, pady=SPACE_SM)
        self.tab_dash = self.tabs.add("Dashboard")
        self.tab_rules = self.tabs.add("Rules")
        self.tab_settings = self.tabs.add("Settings")
        self._setup_dashboard_tab()
        self._setup_rules_tab()
        self._setup_settings_tab()
        self._setup_tooltips()

    def _setup_tooltips(self):
        Tooltip(self.btn_add_quick, "Add this game to your whitelist and start tracking it immediately.")

    def _setup_dashboard_tab(self):
        self.suggestion_frame = ctk.CTkFrame(self.tab_dash, fg_color=COLOR_ACCENT, corner_radius=8)
        ctk.CTkLabel(self.suggestion_frame, text="GAME DETECTED", text_color="white", font=FONT_HEADING).pack(pady=(SPACE_MD, SPACE_XS))
        self.lbl_suggestion = ctk.CTkLabel(self.suggestion_frame, text="", text_color="white", font=FONT_BODY)
        self.lbl_suggestion.pack(pady=SPACE_XS)
        btn_box = ctk.CTkFrame(self.suggestion_frame, fg_color="transparent")
        btn_box.pack(pady=SPACE_MD)
        self.btn_add_quick = ctk.CTkButton(btn_box, text=f"Add ({self.detection_hotkey.upper()})", width=90, fg_color=COLOR_SUCCESS, hover_color="#16A34A", command=self.quick_add_suggestion)
        self.btn_add_quick.pack(side="left", padx=SPACE_XS)
        self.btn_ignore_once = ctk.CTkButton(btn_box, text="Ignore Once", width=90, fg_color=COLOR_MUTED, hover_color="#4B5563", command=self.ignore_suggestion_once)
        self.btn_ignore_once.pack(side="left", padx=SPACE_XS)
        self.btn_ignore_always = ctk.CTkButton(btn_box, text="Ignore Always", width=100, fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_DARK, command=self.ignore_suggestion_always)
        self.btn_ignore_always.pack(side="left", padx=SPACE_XS)
        self.ctrl_frame = ctk.CTkFrame(self.tab_dash, fg_color=COLOR_SURFACE, corner_radius=8)
        self.ctrl_frame.pack(pady=SPACE_MD, padx=SPACE_MD, fill="x")
        self.lbl_ctrl_header = ctk.CTkLabel(self.ctrl_frame, text="Currently Tracking", font=FONT_CAPTION, text_color="#FFFFFF")
        self.lbl_ctrl_header.pack(pady=(SPACE_MD, SPACE_XS))
        self.lbl_current_app = ctk.CTkLabel(self.ctrl_frame, text="Waiting...", font=FONT_HEADING, text_color=COLOR_PRIMARY)
        self.lbl_current_app.pack(pady=SPACE_XS)
        self.track_row = ctk.CTkFrame(self.ctrl_frame, fg_color="transparent")
        self.track_row.pack(pady=SPACE_MD)
        self.switch_track = ctk.CTkSwitch(self.track_row, text="", width=60, switch_width=52, switch_height=28, command=self.toggle_tracking, state="disabled")
        self.switch_track.pack(side="left")
        self.lbl_track_status = ctk.CTkLabel(self.track_row, text="Connect to OBS first", font=("Segoe UI", 18, "bold"), text_color=COLOR_MUTED)
        self.lbl_track_status.pack(side="left", padx=(SPACE_SM, 0))
        self.lbl_swap_counter = ctk.CTkLabel(self.ctrl_frame, text="Total HotSwaps: 0", font=("Segoe UI", 14), text_color="#06B6D4")
        self.lbl_swap_counter.pack(pady=(SPACE_XS, SPACE_MD))
        self.storage_frame = ctk.CTkFrame(self.tab_dash, fg_color=COLOR_SURFACE, corner_radius=8)
        self.storage_frame.pack(pady=SPACE_SM, padx=SPACE_MD, fill="x")
        self.lbl_path = ctk.CTkLabel(self.storage_frame, text="Recording path: Connect to OBS first", font=FONT_CAPTION, text_color=COLOR_MUTED)
        self.lbl_path.pack(pady=(SPACE_MD, SPACE_XS))
        self.storage_bar = ctk.CTkProgressBar(self.storage_frame, height=12, corner_radius=6)
        self.storage_bar.pack(pady=SPACE_SM, padx=SPACE_LG, fill="x")
        self.storage_bar.set(0)
        self.lbl_storage = ctk.CTkLabel(self.storage_frame, text="Not connected", font=FONT_SMALL)
        self.lbl_storage.pack(pady=(SPACE_XS, SPACE_MD))

    def _setup_rules_tab(self):
        self.rule_tabs = ctk.CTkTabview(self.tab_rules)
        self.rule_tabs.pack(fill="both", expand=True, padx=SPACE_XS, pady=SPACE_XS)
        self.sub_whitelist = self.rule_tabs.add("Whitelist (Games)")
        self.sub_blacklist = self.rule_tabs.add("Blacklist (Ignore)")
        self._setup_list_tab(self.sub_whitelist, "whitelist")
        self._setup_list_tab(self.sub_blacklist, "blacklist")

    def _setup_list_tab(self, parent, list_type):
        scan_frame = ctk.CTkFrame(parent, fg_color="transparent")
        scan_frame.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")
        combo_var = ctk.StringVar(value="Scan for running apps...")
        combo = ctk.CTkComboBox(scan_frame, variable=combo_var, width=250, font=FONT_BODY, values=["Scan for running apps..."])
        combo.pack(side="left", padx=SPACE_SM, fill="x", expand=True)
        ctk.CTkButton(scan_frame, text="Scan", width=70, font=FONT_BODY, command=lambda: self.scan_running_apps(combo)).pack(side="left", padx=SPACE_XS)
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=SPACE_SM)
        ctk.CTkButton(btn_row, text="Add Selected", width=120, font=FONT_BODY, command=lambda: self.add_from_combo(list_type, combo)).pack(side="left", padx=SPACE_SM)
        ctk.CTkButton(btn_row, text="Clear All", width=120, font=FONT_BODY, fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_DARK, command=lambda: self.clear_list(list_type)).pack(side="left", padx=SPACE_SM)
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(pady=SPACE_SM, padx=SPACE_SM, fill="both", expand=True)
        if list_type == "whitelist":
            self.white_scroll = scroll
            self.white_combo = combo
        else:
            self.black_scroll = scroll
            self.black_combo = combo

    def _setup_settings_tab(self):
        self.scroll_settings = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        self.scroll_settings.pack(fill="both", expand=True)
        
        self.conn_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        self.conn_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")
        head_frame = ctk.CTkFrame(self.conn_grp, fg_color="transparent")
        head_frame.pack(pady=SPACE_MD)
        self.lbl_conn_header = ctk.CTkLabel(head_frame, text="OBS WebSocket Connection", font=FONT_HEADING)
        self.lbl_conn_header.pack(side="left")
        ctk.CTkButton(head_frame, text="?", width=30, height=30, font=("Segoe UI", 16, "bold"), fg_color=COLOR_MUTED, command=self.show_onboarding).pack(side="left", padx=(10, 0))
        self.entry_pass = ctk.CTkEntry(self.conn_grp, placeholder_text="WebSocket Password", show="*", font=FONT_BODY, height=36)
        self.entry_pass.pack(pady=SPACE_SM, padx=SPACE_LG, fill="x")
        ctk.CTkLabel(self.conn_grp, text="Pass: OBS > Tools > WebSocket Settings", font=("Segoe UI", 12), text_color=COLOR_MUTED).pack(pady=(0, SPACE_SM))
        self.btn_connect = ctk.CTkButton(self.conn_grp, text="Connect", font=FONT_BODY, height=36, command=lambda: threading.Thread(target=self.auto_connect_logic, daemon=True).start())
        self.btn_connect.pack(pady=SPACE_SM)
        self.lbl_conn_status = ctk.CTkLabel(self.conn_grp, text="Disconnected, you MUST connect to OBS WebSocket for this to work.", font=FONT_SMALL, text_color=COLOR_DANGER, wraplength=400)
        self.lbl_conn_status.pack(pady=(SPACE_XS, SPACE_MD))

        self._setup_rest_of_settings()

    def _setup_rest_of_settings(self):
        # (Copied logic from original _setup_settings_tab for remaining sections)
        self.obs_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        self.obs_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")
        self.lbl_obs_header = ctk.CTkLabel(self.obs_grp, text="Auto-Launch Setup", font=FONT_HEADING)
        self.lbl_obs_header.pack(pady=SPACE_MD)
        self.lbl_obs_desc = ctk.CTkLabel(self.obs_grp, text="Step 1: Click Install (Path will be copied to clipboard).\nStep 2: In OBS Scripts, click '+' to add a script.\nStep 3: Press Ctrl+V to paste the path and Open.", font=FONT_CAPTION, text_color=COLOR_MUTED, justify="left", wraplength=400)
        self.lbl_obs_desc.pack()
        self.btn_install_obs = ctk.CTkButton(self.obs_grp, text="1. Create Script & Copy Path", font=FONT_BODY, height=36, command=self.install_obs_script)
        self.btn_install_obs.pack(pady=SPACE_MD)
        self.lbl_install_status = ctk.CTkLabel(self.obs_grp, text="", font=FONT_CAPTION, text_color=COLOR_MUTED, wraplength=400)
        self.lbl_install_status.pack(pady=(0, SPACE_MD))

        self.src_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        self.src_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")
        self.lbl_src_header = ctk.CTkLabel(self.src_grp, text="OBS Source Targeting", font=FONT_HEADING)
        self.lbl_src_header.pack(pady=SPACE_MD)
        vid_row = ctk.CTkFrame(self.src_grp, fg_color="transparent")
        vid_row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)
        self.lbl_video_source = ctk.CTkLabel(vid_row, text="Video Source:", font=FONT_BODY, width=100, anchor="w")
        self.lbl_video_source.pack(side="left")
        self.video_source_var = ctk.StringVar(value="Select Video Source...")
        self.video_source_menu = ctk.CTkOptionMenu(vid_row, variable=self.video_source_var, values=["Scan first..."], font=FONT_BODY, command=self._on_source_changed)
        self.video_source_menu.pack(side="left", fill="x", expand=True)
        self.btn_vid_refresh = ctk.CTkButton(vid_row, text="Refresh", width=70, font=FONT_BODY, command=self.refresh_sources)
        self.btn_vid_refresh.pack(side="right", padx=(SPACE_SM, 0))

        aud_row = ctk.CTkFrame(self.src_grp, fg_color="transparent")
        aud_row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)
        self.lbl_audio_source = ctk.CTkLabel(aud_row, text="Audio Source:", font=FONT_BODY, width=100, anchor="w")
        self.lbl_audio_source.pack(side="left")
        self.audio_source_var = ctk.StringVar(value="Select Audio Source...")
        self.audio_source_menu = ctk.CTkOptionMenu(aud_row, variable=self.audio_source_var, values=["Connect first..."], font=FONT_BODY, command=self._on_source_changed)
        self.audio_source_menu.pack(side="left", fill="x", expand=True, padx=(SPACE_SM, 0))
        ctk.CTkLabel(self.src_grp, text="HotSwap controls these sources automatically.\nAvoid changing the Window setting in OBS Properties.", font=("Segoe UI", 12), text_color=COLOR_WARNING, wraplength=400, justify="left").pack(pady=(SPACE_SM, SPACE_XS), padx=SPACE_LG, anchor="w")
        ctk.CTkLabel(self.src_grp, text="").pack(pady=SPACE_XS)

        self.auto_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        self.auto_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")
        self.lbl_auto_header = ctk.CTkLabel(self.auto_grp, text="Automation Preferences", font=FONT_HEADING)
        self.lbl_auto_header.pack(pady=SPACE_MD)
        self.auto_rec_var = ctk.BooleanVar(value=False)
        self.chk_auto_rec = ctk.CTkCheckBox(self.auto_grp, text="Auto-start recording\nwhen game detected", font=FONT_BODY, variable=self.auto_rec_var)
        self.chk_auto_rec.pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")
        self.auto_fit_var = ctk.BooleanVar(value=False)
        self.chk_auto_fit = ctk.CTkCheckBox(self.auto_grp, text="Auto-fit source to canvas", font=FONT_BODY, variable=self.auto_fit_var)
        self.chk_auto_fit.pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")
        self.game_detection_var = ctk.BooleanVar(value=True)
        self.chk_game_detect = ctk.CTkCheckBox(self.auto_grp, text="Auto-detect games\n(uncheck for Anti-Cheat Safe Mode)", font=FONT_BODY, variable=self.game_detection_var, command=self._toggle_game_detection)
        self.chk_game_detect.pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")
        self.frame_drop_var = ctk.BooleanVar(value=True)
        self.chk_frame_drop = ctk.CTkCheckBox(self.auto_grp, text="Show frame drop alerts\n(press I to disable during game)", font=FONT_BODY, variable=self.frame_drop_var, command=self._toggle_frame_drop_alerts)
        self.chk_frame_drop.pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")
        self.audio_feedback_var = ctk.BooleanVar(value=True)
        self.chk_audio_feedback = ctk.CTkCheckBox(self.auto_grp, text="Enable audio feedback", font=FONT_BODY, variable=self.audio_feedback_var, command=self._toggle_audio_feedback)
        self.chk_audio_feedback.pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")
        self.popup_var = ctk.BooleanVar(value=True)
        self.chk_popup = ctk.CTkCheckBox(self.auto_grp, text="Show popup notifications", font=FONT_BODY, variable=self.popup_var, command=self._toggle_popup_notifications)
        self.chk_popup.pack(pady=SPACE_SM, padx=SPACE_LG, anchor="w")

        volume_row = ctk.CTkFrame(self.auto_grp, fg_color="transparent")
        volume_row.pack(pady=SPACE_XS, fill="x", padx=SPACE_LG)
        ctk.CTkLabel(volume_row, text="Volume:", font=FONT_BODY, width=70, anchor="w").pack(side="left")
        self.audio_volume_var = ctk.DoubleVar(value=self.audio_volume)
        self.volume_slider = ctk.CTkSlider(volume_row, from_=0.0, to=1.0, variable=self.audio_volume_var, command=self._on_volume_change, width=180)
        self.volume_slider.pack(side="left", padx=SPACE_SM)
        self.lbl_volume_pct = ctk.CTkLabel(volume_row, text=f"{int(self.audio_volume * 100)}%", font=FONT_BODY, width=45)
        self.lbl_volume_pct.pack(side="left")
        self.btn_volume_test = ctk.CTkButton(volume_row, text="Test", width=50, font=FONT_BODY, fg_color=COLOR_MUTED, hover_color="#4B5563", command=lambda: self._play_sound("detected"))
        self.btn_volume_test.pack(side="right", padx=SPACE_XS)

        # Sounds
        sound_detected_row = ctk.CTkFrame(self.auto_grp, fg_color="transparent")
        sound_detected_row.pack(pady=SPACE_XS, fill="x", padx=SPACE_LG)
        self.lbl_sound_detected = ctk.CTkLabel(sound_detected_row, text="Detected Sound:", font=FONT_BODY, width=120, anchor="w")
        self.lbl_sound_detected.pack(side="left")
        self.lbl_sound_detected_file = ctk.CTkLabel(sound_detected_row, text="Default", font=FONT_CAPTION, text_color=COLOR_MUTED, width=120)
        self.lbl_sound_detected_file.pack(side="left", padx=SPACE_XS)
        self.btn_sound_detected_browse = ctk.CTkButton(sound_detected_row, text="Browse", width=70, font=FONT_BODY, fg_color=COLOR_MUTED, hover_color="#4B5563", command=lambda: self._browse_sound("detected"))
        self.btn_sound_detected_browse.pack(side="right", padx=SPACE_XS)
        self.btn_sound_detected_reset = ctk.CTkButton(sound_detected_row, text="Reset", width=50, font=FONT_BODY, fg_color="transparent", hover_color="#4B5563", command=lambda: self._reset_sound("detected"))
        self.btn_sound_detected_reset.pack(side="right")
        
        sound_switched_row = ctk.CTkFrame(self.auto_grp, fg_color="transparent")
        sound_switched_row.pack(pady=SPACE_XS, fill="x", padx=SPACE_LG)
        self.lbl_sound_switched = ctk.CTkLabel(sound_switched_row, text="Switched Sound:", font=FONT_BODY, width=120, anchor="w")
        self.lbl_sound_switched.pack(side="left")
        self.lbl_sound_switched_file = ctk.CTkLabel(sound_switched_row, text="Default", font=FONT_CAPTION, text_color=COLOR_MUTED, width=120)
        self.lbl_sound_switched_file.pack(side="left", padx=SPACE_XS)
        self.btn_sound_switched_browse = ctk.CTkButton(sound_switched_row, text="Browse", width=70, font=FONT_BODY, fg_color=COLOR_MUTED, hover_color="#4B5563", command=lambda: self._browse_sound("switched"))
        self.btn_sound_switched_browse.pack(side="right", padx=SPACE_XS)
        self.btn_sound_switched_reset = ctk.CTkButton(sound_switched_row, text="Reset", width=50, font=FONT_BODY, fg_color="transparent", hover_color="#4B5563", command=lambda: self._reset_sound("switched"))
        self.btn_sound_switched_reset.pack(side="right")

        hk_row = ctk.CTkFrame(self.auto_grp, fg_color="transparent")
        hk_row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)
        self.lbl_quickadd_hotkey = ctk.CTkLabel(hk_row, text="Quick-Add Hotkey:", font=FONT_BODY)
        self.lbl_quickadd_hotkey.pack(side="left")
        self.btn_record_hotkey = ctk.CTkButton(hk_row, text=f"{self.detection_hotkey.upper()}", width=80, font=FONT_BODY, fg_color=COLOR_MUTED, hover_color="#4B5563", command=self.start_hotkey_recording)
        self.btn_record_hotkey.pack(side="right")

        toggle_hk_row = ctk.CTkFrame(self.auto_grp, fg_color="transparent")
        toggle_hk_row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)
        self.lbl_toggle_hotkey = ctk.CTkLabel(toggle_hk_row, text="Toggle Tracking Hotkey:", font=FONT_BODY)
        self.lbl_toggle_hotkey.pack(side="left")
        self.btn_record_toggle_hotkey = ctk.CTkButton(toggle_hk_row, text=f"{self.toggle_tracking_hotkey.upper()}", width=80, font=FONT_BODY, fg_color=COLOR_MUTED, hover_color="#4B5563", command=self.start_toggle_hotkey_recording)
        self.btn_record_toggle_hotkey.pack(side="right")
        
        ignore_hk_row = ctk.CTkFrame(self.auto_grp, fg_color="transparent")
        ignore_hk_row.pack(pady=SPACE_SM, fill="x", padx=SPACE_LG)
        self.lbl_ignore_hotkey = ctk.CTkLabel(ignore_hk_row, text="Ignore Alerts Hotkey:", font=FONT_BODY)
        self.lbl_ignore_hotkey.pack(side="left")
        self.btn_record_ignore_hotkey = ctk.CTkButton(ignore_hk_row, text=f"{self.ignore_alerts_hotkey.upper()}", width=80, font=FONT_BODY, fg_color=COLOR_MUTED, hover_color="#4B5563", command=self.start_ignore_hotkey_recording)
        self.btn_record_ignore_hotkey.pack(side="right")

        self._create_slider_row(self.auto_grp, "Detection delay:", "lbl_time_val", "slider_time", 0.5, 5.0, 9, self.detection_threshold, self.update_timer_label, suffix="s")
        self._create_slider_row(self.auto_grp, "Frame drop alert threshold:", "lbl_drop_val", "slider_drop", 5, 100, 19, self.frame_drop_threshold, self.update_drop_label, suffix="")
        ctk.CTkLabel(self.auto_grp, text="").pack(pady=SPACE_XS)

        self.key_grp = ctk.CTkFrame(self.scroll_settings, fg_color=COLOR_SURFACE, corner_radius=8)
        self.key_grp.pack(pady=SPACE_SM, padx=SPACE_SM, fill="x")
        self.lbl_key_header = ctk.CTkLabel(self.key_grp, text="Activity Detection Keys", font=FONT_HEADING)
        self.lbl_key_header.pack(pady=SPACE_MD)
        self.lbl_key_desc = ctk.CTkLabel(self.key_grp, text="Keys that trigger game detection when held", font=FONT_CAPTION, text_color=COLOR_MUTED, wraplength=400)
        self.lbl_key_desc.pack()
        key_row = ctk.CTkFrame(self.key_grp, fg_color="transparent")
        key_row.pack(pady=SPACE_SM)
        self.entry_key = ctk.CTkEntry(key_row, placeholder_text="e.g. space, shift", width=150, font=FONT_BODY, height=32)
        self.entry_key.pack(side="left", padx=SPACE_SM)
        ctk.CTkButton(key_row, text="Add", width=60, font=FONT_BODY, height=32, command=self.add_detection_key).pack(side="left", padx=SPACE_XS)
        ctk.CTkButton(key_row, text="Remove", width=70, font=FONT_BODY, height=32, fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_DARK, command=self.remove_detection_key).pack(side="left", padx=SPACE_XS)
        self.txt_keys = ctk.CTkTextbox(self.key_grp, height=50, font=FONT_BODY, corner_radius=6)
        self.txt_keys.pack(pady=(SPACE_SM, SPACE_MD), padx=SPACE_MD, fill="x")
        self.txt_keys.configure(state="disabled")
        self.update_key_display()

        ctk.CTkLabel(self.scroll_settings, text="").pack(pady=SPACE_SM)
        btn_debug = ctk.CTkButton(self.scroll_settings, text="Open Config Folder", font=FONT_BODY, fg_color=COLOR_MUTED, hover_color="#4B5563", command=lambda: os.startfile(os.path.dirname(CONFIG_FILE)))
        btn_debug.pack(pady=(0, SPACE_XL))

    def _create_slider_row(self, parent, label, lbl_name, slider_name, min_val, max_val, steps, default, cmd, suffix):
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

    def start_hotkey_recording(self):
        self.btn_record_hotkey.configure(text="Press key...", fg_color=COLOR_WARNING)
        threading.Thread(target=self._wait_for_hotkey, daemon=True).start()
    def _wait_for_hotkey(self):
        try:
            event = keyboard.read_event(suppress=False)
            if event.event_type == keyboard.KEY_DOWN:
                new_key = event.name
                self._unregister_hotkeys()
                self.detection_hotkey = new_key
                self._register_hotkeys()
                self.btn_record_hotkey.configure(text=new_key.upper(), fg_color=COLOR_MUTED)
                self.btn_add_quick.configure(text=f"Add ({new_key.upper()})")
                self.save_settings()
        except Exception: pass
    def start_toggle_hotkey_recording(self):
        self.btn_record_toggle_hotkey.configure(text="Press key...", fg_color=COLOR_WARNING)
        threading.Thread(target=self._wait_for_toggle_hotkey, daemon=True).start()
    def _wait_for_toggle_hotkey(self):
        try:
            event = keyboard.read_event(suppress=False)
            if event.event_type == keyboard.KEY_DOWN:
                new_key = event.name
                self._unregister_hotkeys()
                self.toggle_tracking_hotkey = new_key
                self._register_hotkeys()
                self.btn_record_toggle_hotkey.configure(text=new_key.upper(), fg_color=COLOR_MUTED)
                self.save_settings()
        except Exception: pass
    def start_ignore_hotkey_recording(self):
        self.btn_record_ignore_hotkey.configure(text="Press key...", fg_color=COLOR_WARNING)
        threading.Thread(target=self._wait_for_ignore_hotkey, daemon=True).start()
    def _wait_for_ignore_hotkey(self):
        try:
            event = keyboard.read_event(suppress=False)
            if event.event_type == keyboard.KEY_DOWN:
                new_key = event.name
                self._unregister_hotkeys()
                self.ignore_alerts_hotkey = new_key
                self._register_hotkeys()
                self.btn_record_ignore_hotkey.configure(text=new_key.upper(), fg_color=COLOR_MUTED)
                self.save_settings()
        except Exception: pass
        
    def _toggle_game_detection(self):
        wants_enabled = self.game_detection_var.get()
        if wants_enabled and not self.disclaimer_accepted:
            self._show_anticheat_notice()
            self.disclaimer_accepted = True
        self.game_detection_enabled = wants_enabled
        self.save_settings()
        if self.game_detection_enabled:
            threading.Thread(target=self.heuristic_loop, daemon=True).start()
    def _show_anticheat_notice(self):
        notice = ctk.CTkToplevel(self)
        notice.title("Anti-Cheat Info")
        notice.geometry("420x320")
        notice.resizable(False, False)
        notice.transient(self)
        notice.grab_set()
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 420) // 2
        y = self.winfo_y() + (self.winfo_height() - 320) // 2
        notice.geometry(f"+{x}+{y}")
        ctk.CTkLabel(notice, text="Anti-Cheat Notice", font=("Segoe UI", 18, "bold")).pack(pady=(20, 10))
        info_text = "Some competitive games (Valorant, FaceIt, etc.) use\naggressive anti-cheat systems.\n\nHotSwap only listens for real key presses and\ndoes not inject input or modify games.\n\nIf you play games with strict anti-cheat, you can\nenable Anti-Cheat Safe Mode to add games manually."
        ctk.CTkLabel(notice, text=info_text, font=FONT_BODY, justify="center").pack(pady=10, padx=20)
        btn_frame = ctk.CTkFrame(notice, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Got it", width=120, fg_color=COLOR_SUCCESS, hover_color="#16A34A", command=notice.destroy).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Enable Safe Mode", width=140, fg_color=COLOR_MUTED, hover_color="#4B5563", command=lambda: self._enable_safe_mode(notice)).pack(side="left", padx=10)
    def _enable_safe_mode(self, notice_window):
        self.game_detection_var.set(False)
        self.game_detection_enabled = False
        self.save_settings()
        notice_window.destroy()
    def _toggle_frame_drop_alerts(self):
        self.frame_drop_alerts_enabled = self.frame_drop_var.get()
        self.save_settings()
    def _toggle_audio_feedback(self):
        self.audio_feedback_enabled = self.audio_feedback_var.get()
        self.save_settings()
        if self.audio_feedback_enabled: self._play_sound("switched")
    def _toggle_popup_notifications(self):
        self.popup_notifications_enabled = self.popup_var.get()
        self.save_settings()
    def _on_volume_change(self, value):
        self.audio_volume = float(value)
        self.lbl_volume_pct.configure(text=f"{int(self.audio_volume * 100)}%")
        self.save_settings()
    def _browse_sound(self, sound_type):
        filepath = filedialog.askopenfilename(title=f"Select {sound_type.capitalize()} Sound", filetypes=[("WAV files", "*.wav"), ("All files", "*.*")])
        if filepath:
            if sound_type == "detected":
                self.sound_detected_path = filepath
                self.lbl_sound_detected_file.configure(text=os.path.basename(filepath), text_color=COLOR_SUCCESS)
            else:
                self.sound_switched_path = filepath
                self.lbl_sound_switched_file.configure(text=os.path.basename(filepath), text_color=COLOR_SUCCESS)
            self.save_settings()
            self._play_sound(sound_type)
    def _reset_sound(self, sound_type):
        if sound_type == "detected":
            self.sound_detected_path = ""
            self.lbl_sound_detected_file.configure(text="Default", text_color=COLOR_MUTED)
        else:
            self.sound_switched_path = ""
            self.lbl_sound_switched_file.configure(text="Default", text_color=COLOR_MUTED)
        self.save_settings()
    def _play_sound(self, sound_type):
        if not self.audio_feedback_enabled: return
        def _play():
            try:
                path = self.sound_detected_path if sound_type == "detected" else self.sound_switched_path
                if not path:
                    path = self.default_sound_detected if sound_type == "detected" else self.default_sound_switched
                
                if os.path.exists(path):
                    with wave.open(path, 'rb') as wav:
                        params = wav.getparams()
                        frames = wav.readframes(params.nframes)
                    volume = max(0.0, min(1.0, self.audio_volume))
                    adjusted_frames = audioop.mul(frames, params.sampwidth, volume)
                    buffer = io.BytesIO()
                    with wave.open(buffer, 'wb') as out_wav:
                        out_wav.setparams(params)
                        out_wav.writeframes(adjusted_frames)
                    winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY)
                else:
                    winsound.MessageBeep(winsound.MB_OK if sound_type == "switched" else winsound.MB_ICONEXCLAMATION)
            except Exception: pass
        threading.Thread(target=_play, daemon=True).start()
    
    def add_detection_key(self):
        key = self.entry_key.get().lower().strip()
        if not key: return
        if key in self.detection_keys:
            self._show_entry_feedback(self.entry_key, "Already added")
            return
        self.detection_keys.append(key)
        self.entry_key.delete(0, "end")
        self.update_key_display()
        self.save_settings()
    def remove_detection_key(self):
        key = self.entry_key.get().lower().strip()
        if key in self.detection_keys:
            self.detection_keys.remove(key)
            self.entry_key.delete(0, "end")
            self.update_key_display()
            self.save_settings()
        else:
            self._show_entry_feedback(self.entry_key, "Key not found")
    def _show_entry_feedback(self, entry, message):
        original = entry.get()
        entry.delete(0, "end")
        entry.configure(placeholder_text=message)
        self.after(1500, lambda: entry.configure(placeholder_text="e.g. space, shift"))
    def update_key_display(self):
        self.txt_keys.configure(state="normal")
        self.txt_keys.delete("0.0", "end")
        self.txt_keys.insert("end", ", ".join(self.detection_keys))
        self.txt_keys.configure(state="disabled")
    def update_timer_label(self, val):
        self.lbl_time_val.configure(text=f"{val:.1f}s")
        self.detection_threshold = val
    def update_drop_label(self, val):
        val = int(val)
        self.lbl_drop_val.configure(text=f"{val}")
        self.frame_drop_threshold = val
        
    def install_obs_script(self, silent=False):
        # [Paste install_obs_script logic]
        try:
            if getattr(sys, 'frozen', False): exe_path = sys.executable
            else: exe_path = os.path.abspath(__file__)
            exe_path_escaped = exe_path.replace("\\", "\\\\")
            lua_script = f'''obs = obslua
local app_path = "{exe_path_escaped}"
function script_description() return "Launches HotSwap automatically when OBS starts.\\n\\nPath: " .. app_path end
function on_event(event) if event == obs.OBS_FRONTEND_EVENT_FINISHED_LOADING then obs.script_log(obs.LOG_INFO, "HotSwap: Launching...") os.execute('start "" "' .. app_path .. '"') end end
function script_load(settings) obs.obs_frontend_add_event_callback(on_event) end
'''
            appdata = os.environ.get('APPDATA', '')
            obs_base = os.path.join(appdata, 'obs-studio', 'basic', 'scripts')
            if not os.path.exists(obs_base): os.makedirs(obs_base, exist_ok=True)
            script_path = os.path.join(obs_base, 'HotSwap_Launcher.lua')
            with open(script_path, 'w') as f: f.write(lua_script)
            if not silent:
                self.clipboard_clear()
                self.clipboard_append(script_path)
                self.update()
                self.lbl_install_status.configure(text="Path copied! Just press Ctrl+V in OBS.", text_color=COLOR_SUCCESS)
                self.after(5000, lambda: self.lbl_install_status.configure(text="Tip: The file path is in your clipboard."))
        except Exception as e:
            if not silent: self._show_install_error(f"Install failed: {str(e)[:50]}")
    def _show_install_error(self, message):
        self.lbl_install_status.configure(text=f"{message}\nSee README for manual install instructions.", text_color=COLOR_DANGER)

    # =========================================================================
    # SUGGESTION LOGIC (UPDATED)
    # =========================================================================
    def show_suggestion(self, exe_name):
        if not self.suggestion_frame.winfo_ismapped():
            self.lbl_suggestion.configure(text=exe_name)
            self.suggestion_frame.pack(before=self.ctrl_frame, pady=SPACE_MD, padx=SPACE_MD, fill="x")
            self.tabs.set("Dashboard")
            self._play_sound("detected")
            if self.popup_notifications_enabled:
                self.overlay.show(
                    title="Game Detected",
                    message=exe_name,
                    hotkey=self.detection_hotkey,
                    duration=10000,
                    overlay_type=OverlayPopup.TYPE_GAME_DETECTED
                )

    def hide_suggestion(self):
        self.suggestion_frame.pack_forget()
        self.suggested_app = None
        self.suggested_title = None
        self.suggested_class = None
        self.overlay.hide()

    def ignore_suggestion_once(self):
        if self.suggested_app:
            self.temp_ignore_list.append(self.suggested_app)
            self.hide_suggestion()

    def ignore_suggestion_always(self):
        if self.suggested_app:
            self.blacklist.append(self.suggested_app)
            self.update_display("blacklist")
            self.save_settings()
            self.hide_suggestion()

    def quick_add_suggestion(self):
        """UI PART: Sets the lock IMMEDIATELY to stop the loop from fighting."""
        if not self.is_tracking:
            return
        if not self.obs_client:
            self.lbl_current_app.configure(text="Connect to OBS first", text_color=COLOR_WARNING)
            return
        vid = self.video_source_var.get()
        if not vid or "Select" in vid:
            self.lbl_current_app.configure(text="Set Video Source in Settings", text_color=COLOR_WARNING)
            return
        self.overlay.clear_queue()

        app_to_add = self.suggested_app

        if not app_to_add:
            exe, _, _, _ = self.get_window_info()
            if exe and exe not in self.blacklist and exe != self.self_exe and exe != "HotSwap.exe":
                app_to_add = exe

        if not app_to_add: return

        # Don't add blacklisted apps
        if app_to_add in self.blacklist:
            self.hide_suggestion()
            return

        # Debounce rapid F9 spam (within 2 seconds)
        if time.time() - getattr(self, 'last_f9_time', 0) < 2:
            return
        self.last_f9_time = time.time()

        # 1. Update Whitelist
        if app_to_add not in self.whitelist:
            self.whitelist.append(app_to_add)
            self.update_display("whitelist")
            self.save_settings()

        saved_title = self.suggested_title
        saved_class = self.suggested_class
        
        self.hide_suggestion()
        
        # --- EARLY LOCK ---
        self.last_injected_exe = app_to_add 
        self.locked_app = None
        
        # 2. Run OBS update in background thread
        threading.Thread(target=self._quick_add_worker, args=(app_to_add, saved_title, saved_class), daemon=True).start()

    def _quick_add_worker(self, app_to_add, saved_title, saved_class):
        """WORKER PART: Updates OBS."""
        current_exe, current_title, current_cls, _ = self.get_window_info()

        target_title = current_title if (current_exe == app_to_add) else saved_title
        target_class = current_cls if (current_exe == app_to_add) else saved_class

        if not target_title or not target_class:
            time.sleep(0.5)
            current_exe, current_title, current_cls, _ = self.get_window_info()
            if current_exe == app_to_add:
                target_title = current_title
                target_class = current_cls

        if target_title and target_class:
            print(f"Quick Add worker switching to: {app_to_add}")


            self.update_obs(app_to_add, target_title, target_class, is_new_switch=True)

            self.lbl_current_app.configure(text=f"{app_to_add} (Tracking)", text_color=COLOR_PRIMARY)

            self.last_switch_time = time.time()

            self._play_sound("switched")
        else:
            print(f"Quick Add worker: Could not get window info for {app_to_add}")
            
    def _notify_user(self):
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd: hwnd = self.winfo_id()
            flash_window(hwnd)
        except Exception: pass

    # =========================================================================
    # HEURISTIC LOOP (Game Detection)
    # =========================================================================
    def heuristic_loop(self):
        """Background loop that detects game activity based on key presses."""
        activity_timer = 0

        while self.game_detection_enabled:
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
                if activity_timer > threshold:
                    exe, title, cls, _ = self.get_window_info()

                    if not exe or exe == self.self_exe or exe == "HotSwap.exe":
                        time.sleep(0.1)
                        continue
                    
                    is_whitelisted = exe in self.whitelist
                    
                    # If app was locked/injected but NO LONGER whitelisted, clear state.
                    was_locked = (exe == self.locked_app)
                    was_injected = (exe == self.last_injected_exe)

                    if (was_locked or was_injected) and not is_whitelisted:
                        self.locked_app = None
                        self.last_injected_exe = ""
                        # Let it fall through to suggestion

                    is_blacklisted = exe in self.blacklist
                    is_temp_ignored = exe in self.temp_ignore_list

                    # --- STRICT CHECK ---
                    # If it's whitelisted, NEVER suggest it.
                    if not is_whitelisted and not is_blacklisted and not is_temp_ignored:
                        self.suggested_app = exe
                        self.suggested_title = title
                        self.suggested_class = cls
                        
                        current_text = self.lbl_suggestion.cget("text")
                        is_visible = self.suggestion_frame.winfo_ismapped()
                        
                        if current_text != exe or not is_visible:
                            self.show_suggestion(exe)
                    else:
                        if self.suggestion_frame.winfo_ismapped():
                            self.hide_suggestion()
            else:
                activity_timer = 0

            time.sleep(0.1)

    def debug_frame_drop_test(self):
        self.overlay.show(
            title="Performance Warning",
            message="Dropped 45 frames! (TEST)",
            hotkey="",
            duration=8000,
            overlay_type=OverlayPopup.TYPE_FRAME_DROP
        )

    def auto_connect_logic(self):
        max_retries = 3
        password = self.entry_pass.get()
        if not password:
            self.lbl_conn_status.configure(text="Enter password first", text_color=COLOR_WARNING)
            return
        hosts_to_try = ['127.0.0.1', 'localhost']
        for attempt in range(max_retries):
            for host in hosts_to_try:
                try:
                    self.lbl_conn_status.configure(text=f"Connecting to {host}... ({attempt + 1}/{max_retries})", text_color=COLOR_WARNING)
                    self.obs_client = obs.ReqClient(host=host, port=4455, password=password)
                    self.obs_events = obs.EventClient(host=host, port=4455, password=password, callback=self.on_obs_event)
                    self._on_connect_success()
                    return
                except Exception as e:
                    error_msg = str(e).lower()
                    if "authentication failed" in error_msg:
                        self.lbl_conn_status.configure(text="Incorrect password", text_color=COLOR_DANGER)
                        return
            time.sleep(1)
        self.lbl_conn_status.configure(text="Can't reach OBS. Is it open with WebSocket enabled?", text_color=COLOR_DANGER)

    def on_obs_event(self, event):
        try:
            if event.name == "CurrentSceneCollectionChanged":
                self.after(2000, self.refresh_sources)
            elif event.name in ("SceneItemEnableStateChanged", "InputSettingsChanged", "CurrentProgramSceneChanged"):
                self.last_injected_exe = ""
                self.last_obs_target = ""
        except Exception: pass
        
    def _on_connect_success(self):
        self.lbl_conn_status.configure(text="Connected", text_color=COLOR_SUCCESS)
        self.switch_track.configure(state="normal")
        self.lbl_track_status.configure(text="Tracking is OFF", text_color=COLOR_DANGER)
        self.refresh_sources()
        for _ in range(3):
            if self._get_obs_config(): break
            time.sleep(1)
        self.check_disk_space()
        self.save_settings()
        try:
            stats = self.obs_client.get_stats()
            self.last_render_skipped = stats.render_skipped_frames
        except Exception: pass
        if getattr(self, '_pending_auto_tracking', False):
            self._pending_auto_tracking = False
            self.switch_track.select()
            self.is_tracking = True
            self.lbl_track_status.configure(text="Tracking is ON", text_color=COLOR_SUCCESS)
            self.lbl_current_app.configure(text="Scanning...", text_color=COLOR_PRIMARY)
            threading.Thread(target=self.tracking_loop, daemon=True).start()

    def _on_obs_disconnect(self):
        """Handle OBS disconnecting (closed, crashed, etc.)."""
        if self.obs_client is None:
            return  # Already disconnected, don't re-trigger
        self.obs_client = None
        self.is_tracking = False
        self.switch_track.deselect()
        self.switch_track.configure(state="disabled")
        self.lbl_track_status.configure(text="Connect to OBS first", text_color=COLOR_MUTED)
        self.lbl_current_app.configure(text="OBS Disconnected", text_color=COLOR_DANGER)
        self.lbl_conn_status.configure(text="Reconnecting...", text_color=COLOR_WARNING)
        self.lbl_alert.configure(text="SYSTEM NORMAL", text_color=COLOR_MUTED)
        self._reset_detection_state()
        # Start auto-reconnect in background
        threading.Thread(target=self._auto_reconnect_loop, daemon=True).start()

    def _auto_reconnect_loop(self):
        """Periodically try to reconnect to OBS after disconnect."""
        password = self.entry_pass.get()
        if not password:
            self.lbl_conn_status.configure(text="Disconnected - no password set", text_color=COLOR_DANGER)
            return
        hosts_to_try = ['127.0.0.1', 'localhost']
        while self.obs_client is None:
            time.sleep(5)
            for host in hosts_to_try:
                try:
                    self.obs_client = obs.ReqClient(host=host, port=4455, password=password)
                    self.obs_events = obs.EventClient(host=host, port=4455, password=password, callback=self.on_obs_event)
                    self.after(0, self._on_connect_success)
                    return
                except Exception:
                    continue

    def refresh_sources(self):
        if not self.obs_client: return
        try:
            try:
                collection_resp = self.obs_client.get_scene_collection_list()
                new_collection = collection_resp.current_scene_collection_name
                if self.current_scene_collection is not None and new_collection != self.current_scene_collection:
                    self._save_collection_sources(self.current_scene_collection)
                old_collection = self.current_scene_collection
                self.current_scene_collection = new_collection
            except Exception: pass

            resp = self.obs_client.get_input_list()
            video_inputs = []
            audio_inputs = []
            raw_list = resp.inputs if hasattr(resp, 'inputs') else resp
            video_kinds = ("game_capture", "window_capture")
            audio_kinds = ("wasapi_process_output_capture", "wasapi_input_capture", "wasapi_output_capture")
            for item in raw_list:
                name = (getattr(item, 'inputName', None) or getattr(item, 'input_name', None) or item.get('inputName') or item.get('input_name'))
                kind = (getattr(item, 'inputKind', None) or getattr(item, 'input_kind', None) or item.get('inputKind') or item.get('input_kind') or "")
                if not name: continue
                if kind in video_kinds:
                    video_inputs.append(name)
                if kind in audio_kinds or kind in video_kinds:
                    audio_inputs.append(name)

            if video_inputs or audio_inputs:
                self.video_source_menu.configure(values=video_inputs if video_inputs else ["No capture sources found"])
                self.audio_source_menu.configure(values=audio_inputs if audio_inputs else ["No audio sources found"])
                inputs = video_inputs + audio_inputs
                if self.current_scene_collection and self.current_scene_collection in self.scene_collection_sources:
                    saved = self.scene_collection_sources[self.current_scene_collection]
                    saved_video = saved.get("video_source", "")
                    saved_audio = saved.get("audio_source", "")
                    if saved_video in video_inputs: self.video_source_var.set(saved_video)
                    elif self.video_source_var.get() not in video_inputs: self.video_source_var.set("Select Video Source...")
                    if saved_audio in audio_inputs: self.audio_source_var.set(saved_audio)
                    elif self.audio_source_var.get() not in audio_inputs: self.audio_source_var.set("Select Audio Source...")
                else:
                    if self.video_source_var.get() not in video_inputs: self.video_source_var.set("Select Video Source...")
                    if self.audio_source_var.get() not in audio_inputs: self.audio_source_var.set("Select Audio Source...")
            else:
                self.video_source_var.set("No capture sources found")
                self.audio_source_var.set("No audio sources found")
        except Exception: self.video_source_var.set("Error loading sources")

    def _save_collection_sources(self, collection_name):
        if not collection_name: return
        video = self.video_source_var.get()
        audio = self.audio_source_var.get()
        if "Select" not in video or "Select" not in audio:
            self.scene_collection_sources[collection_name] = {"video_source": video if "Select" not in video else "", "audio_source": audio if "Select" not in audio else ""}
            self.save_settings()

    def _on_source_changed(self, _=None):
        if self.current_scene_collection: self._save_collection_sources(self.current_scene_collection)
    
    def check_disk_space(self):
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
            total_bitrate = self.current_bitrate + 320
            if total_bitrate <= 0: total_bitrate = 6000
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
        except Exception as e: self.lbl_storage.configure(text=f"Error checking disk: {e}", text_color=COLOR_DANGER)

    def _get_obs_config(self):
        if not self.obs_client: return False
        try:
            resp_dir = self.obs_client.get_record_directory()
            directory = getattr(resp_dir, 'record_directory', None) or getattr(resp_dir, 'recordDirectory', None)
            if directory:
                self.recording_folder = os.path.normpath(directory)
                return True
        except Exception: pass
        return False

    
    def _is_blocked_by_display_capture(self, target_source):
        """Check if a Display Capture is currently VISIBLE and ABOVE our target."""
        if not self.obs_client: return False
        
        try:
            scene = self.obs_client.get_current_program_scene().current_program_scene_name
            items = self.obs_client.get_scene_item_list(scene).scene_items
            

            target_index = 999
            for item in items:
                if item['sourceName'] == target_source:
                    target_index = item['sceneItemIndex']
                    break
            
            for item in items:
                # Is it above us?
                if item['sceneItemIndex'] < target_index:
                    # Is it visible?
                    if item['sceneItemEnabled']:
                        # Is it a Display Capture?
                        kind = item.get('inputKind', '').lower()
                        name = item['sourceName'].lower()
                        
                        # Check for standard Display Capture types or names
                        if "monitor_capture" in kind or "display_capture" in kind or "display capture" in name:
                            # print(f"[OBS] Blocked by Display Capture: {item['sourceName']}")
                            return True
            
            return False
            
        except Exception:
            # If we can't check, assume we are safe to proceed to avoid breaking functionality
            return False
    
    def update_obs(self, exe_name, window_title, class_name, is_new_switch=False):
        """Update OBS. Includes strict checks to ensure we don't switch when disabled."""
        
        if self.demo_mode:
            print(f"[DEMO MODE] Pretending to switch to: {exe_name}")
            return #
        
        # 1. SAFETY CHECK: 
        # We allow 'is_new_switch' (F9 Manual Add) to bypass this, 
        # but automatic background switches must pass this check.
        if not self.switch_track.get() and not is_new_switch:
            # print("Blocked update: Tracking is disabled.")
            return

        if not self.obs_client: return

        vid = self.video_source_var.get()
        aud = self.audio_source_var.get()
        
        # --- DISPLAY CAPTURE LOGIC ---
        if vid and "Select" not in vid:
            # Check if Display Capture is blocking us
            is_blocked = self._is_blocked_by_display_capture(vid)
            
            if is_blocked:
                if is_new_switch:
                    print(f"[OBS] OVERRIDE: Display Capture is active, but New Game detected. Switching anyway.")
                else:
                    # If it's NOT a new switch (just maintenance), we back off.
                    return

        safe_title = (window_title or "Untitled").replace(":", "#3A")
        target = f"{safe_title}:{class_name}:{exe_name}"
        
        try:
            # --- 1. HANDLE VIDEO SOURCE ---
            if vid and "Select" not in vid:
                current_settings = self.obs_client.get_input_settings(vid).input_settings
                current_window = current_settings.get("window", "")

                if current_window != target:
                    self.total_swaps += 1
                    self.lbl_swap_counter.configure(text=f"Total HotSwaps: {self.total_swaps}")
                    self.save_settings()
                    print(f"[OBS] Switching '{vid}' to: {exe_name}")
                    
                    try:
                        input_kind = self.obs_client.get_input_kind(vid).input_kind
                    except Exception:
                        input_kind = "window_capture"

                    new_settings = {"window": target}
                    if "window" in input_kind.lower():
                        new_settings["priority"] = 2 

                    self.obs_client.set_input_settings(name=vid, settings=new_settings, overlay=True)

                    if self.auto_fit_var.get(): 
                        self._auto_fit_source(vid)
                        
                    threading.Thread(target=self._validate_hook, args=(vid,), daemon=True).start()

            # --- 2. HANDLE AUDIO SOURCE ---
            if aud and "Select" not in aud:
                self.obs_client.set_input_settings(name=aud, settings={"window": target, "priority": 2}, overlay=True)
                # Toggle Audio
                self.obs_client.set_input_settings(name=aud, settings={"enabled": False}, overlay=True)
                time.sleep(0.05)
                self.obs_client.set_input_settings(name=aud, settings={"enabled": True}, overlay=True)

            # --- 3. AUTO-RECORD ---
            if self.auto_rec_var.get():
                if not self.obs_client.get_record_status().output_active:
                    self.obs_client.start_record()

        except Exception as e:
            error_msg = str(e).lower()
            print(f"OBS Update Error: {e}")
            if "10054" in error_msg or "10053" in error_msg or "connection" in error_msg or "closed" in error_msg or "eof" in error_msg:
                self.after(0, self._on_obs_disconnect)
            elif "scene" not in error_msg:
                self.lbl_current_app.configure(text=f"OBS Error: {str(e)[:30]}", text_color=COLOR_DANGER)

    def _auto_fit_source(self, source_name):
        window_width, window_height = 0, 0
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                rect = win32gui.GetClientRect(hwnd)
                window_width = rect[2] - rect[0]
                window_height = rect[3] - rect[1]
        except Exception: pass
        threading.Thread(target=self._auto_fit_source_delayed, args=(source_name, window_width, window_height), daemon=True).start()

    def _auto_fit_source_delayed(self, source_name, window_width, window_height):
        try:
            time.sleep(1.5)
            current_scene = self.obs_client.get_current_program_scene().current_program_scene_name
            items = self.obs_client.get_scene_item_list(current_scene).scene_items
            target_item = next((i for i in items if i['sourceName'] == source_name), None)
            if target_item:
                item_id = target_item['sceneItemId']
                res = self.obs_client.get_video_settings()
                new_transform = {"boundsAlignment": 0, "boundsWidth": res.base_width, "boundsHeight": res.base_height, "boundsType": "OBS_BOUNDS_SCALE_INNER"}
                self.obs_client.set_scene_item_transform(current_scene, item_id, new_transform)
                if window_width > 0 and window_height > 0:
                    canvas_ar = res.base_width / res.base_height
                    source_ar = window_width / window_height
                    diff = abs(canvas_ar - source_ar)
                    size_match = (window_width == res.base_width and window_height == res.base_height)
                    if diff > 0.01 and not size_match:
                        if diff > 0.1:
                            issue_type = "Ultrawide" if source_ar > canvas_ar else "Boxy (4:3)"
                        else:
                            issue_type = f"{window_width}x{window_height} (black bars possible)"
                        self.lbl_alert.configure(text=f"Resolution: {issue_type}", text_color=COLOR_WARNING)
                        if self.popup_notifications_enabled:
                            self.overlay.show(title="Aspect Ratio Warning", message=f"Game is {issue_type}", hotkey="", duration=6000, overlay_type=OverlayPopup.TYPE_ASPECT_RATIO)
        except Exception: pass

    def _validate_hook(self, source_name):
        # Give Game Capture more time to hook — some games take longer
        for attempt in range(3):
            time.sleep(2.0)
            try:
                if not self.obs_client: return
                active = self.obs_client.get_source_active(source_name).video_active
                if active: return  # Capture is working
            except Exception: return
        # Only warn after 3 failed checks (6 seconds total)
        self.lbl_current_app.configure(text="Capture may have failed - try Admin?", text_color=COLOR_WARNING)
        if self.popup_notifications_enabled:
            self.overlay.show(title="Capture Warning", message="Game may need Administrator mode", hotkey="", duration=6000, overlay_type=OverlayPopup.TYPE_CAPTURE_FAILED)

    def tracking_loop(self):
        """Main tracking loop with Strict Monitor Checking."""
        check_counter = 0
        while self.is_tracking:
            self.check_overload()
            if check_counter % 10 == 0: self.check_disk_space()
            check_counter += 1

            exe, title, cls, _ = self.get_window_info()

            if exe:
                if exe == self.self_exe or exe == "HotSwap.exe":
                    time.sleep(1.5)
                    continue

                # --- PERMISSION CHECKS ---
                is_whitelisted = exe in self.whitelist
                is_blacklisted = exe in self.blacklist
                is_temp_ignored = exe in self.temp_ignore_list

                if (exe.lower() in [g.lower() for g in self.anticheat_games] and not self.anticheat_suggested and self.game_detection_enabled):
                    self.anticheat_suggested = True
                    if self.popup_notifications_enabled:
                        self.overlay.show(title="Anti-Cheat Detected", message=f"{exe}\nConsider enabling Safe Mode", hotkey="", duration=8000, overlay_type=OverlayPopup.TYPE_ASPECT_RATIO)

                allowed = is_whitelisted
                if not allowed and self.last_injected_exe: self.last_injected_exe = ""
                
                if "failed" not in self.lbl_current_app.cget("text").lower():
                    status = "Tracking" if allowed else "Ignored"
                    self.lbl_current_app.configure(text=f"{exe} ({status})", text_color=COLOR_PRIMARY if allowed else COLOR_MUTED)
                
                # Debounce check
                if time.time() - getattr(self, 'last_switch_time', 0) < 3:
                    time.sleep(1.5)
                    continue
                
                # --- 3. SWITCHING LOGIC ---
                if allowed:
                    is_new_game = (exe != self.last_injected_exe)
                    
                    if is_new_game:
                        self.update_obs(exe, title, cls, is_new_switch=True)
                        self.last_injected_exe = exe
                        self.last_switch_time = time.time()
                    else:
                        # MAINTENANCE: We pass False. This prevents switching sounds/notifications on re-detect.
                        self.update_obs(exe, title, cls, is_new_switch=False)

            time.sleep(1.5)

    def _is_process_running(self, exe_name):
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == exe_name: return True
        except Exception: pass
        return False
        
    def check_overload(self):
        if not self.obs_client: return
        if not getattr(self, 'frame_drop_alerts_enabled', True): return
        try:
            stats = self.obs_client.get_stats()
            diff = stats.render_skipped_frames - self.last_render_skipped
            self.last_render_skipped = stats.render_skipped_frames
            now = time.time()
            recently_switched = (now - getattr(self, 'last_switch_time', 0)) < 5
            alert_cooldown = (now - getattr(self, 'last_alert_time', 0)) < 30
            if diff > self.frame_drop_threshold:
                self.lbl_alert.configure(text=f"Dropped {diff} frames!", text_color=COLOR_DANGER)
                self.status_frame.configure(fg_color=COLOR_DANGER_DARK)
                if not recently_switched and not alert_cooldown and self.popup_notifications_enabled:
                    self.overlay.show(title="Performance Warning", message=f"Dropped {diff} frames!", hotkey="", duration=8000, overlay_type=OverlayPopup.TYPE_FRAME_DROP)
                    self.last_alert_time = now
            elif diff > 0:
                self.lbl_alert.configure(text=f"Minor stutter ({diff} frames)", text_color=COLOR_WARNING)
                self.status_frame.configure(fg_color="transparent")
            else:
                self.lbl_alert.configure(text="SYSTEM NORMAL", text_color=COLOR_MUTED)
                self.status_frame.configure(fg_color="transparent")
        except Exception as e:
            error_msg = str(e).lower()
            if "10054" in error_msg or "10053" in error_msg or "connection" in error_msg or "closed" in error_msg or "eof" in error_msg:
                self.after(0, self._on_obs_disconnect)

    def get_window_info(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0: return None, None, None, None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe_name = psutil.Process(pid).name()
            window_title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL)
            return exe_name, window_title, class_name, monitor
        except (psutil.NoSuchProcess, psutil.AccessDenied): return None, None, None, None
        except Exception: return None, None, None, None

    def scan_running_apps(self, combo_widget):
        apps = []
        def enum_handler(hwnd, ctx):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        exe_name = psutil.Process(pid).name()
                        if exe_name and exe_name != "HotSwap.exe" and title.strip():
                            apps.append(f"{title} ({exe_name})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        try:
            win32gui.EnumWindows(enum_handler, None)
            apps.sort()
            clean_apps = [a for a in apps if "HotSwap" not in a]
            if clean_apps:
                combo_widget.configure(values=clean_apps)
                combo_widget.set(clean_apps[0])
            else:
                combo_widget.configure(values=["No apps found"])
                combo_widget.set("No apps found")
        except Exception as e:
            combo_widget.set("Scan error")
            print(f"Scan error: {e}")

    def add_from_combo(self, list_type, combo_widget):
        selection = combo_widget.get()
        exe = selection.split("(")[-1].strip(")") if "(" in selection else selection.strip()
        if not exe.lower().endswith(".exe"): return
        target = self.whitelist if list_type == "whitelist" else self.blacklist
        if exe and exe not in target:
            target.append(exe)
            self.update_display(list_type)
            self.save_settings()

    def _reset_detection_state(self, exe_name=None):
        if exe_name:
            if self.last_injected_exe == exe_name: self.last_injected_exe = ""
            if self.locked_app == exe_name: self.locked_app = None
            if self.last_injected_exe == exe_name: 
                self.last_obs_target = ""
            if self.suggested_app == exe_name:
                self.suggested_app = None
                self.hide_suggestion()
            if exe_name in self.temp_ignore_list: self.temp_ignore_list.remove(exe_name)
        else:
            self.last_injected_exe = ""
            self.last_obs_target = ""
            self.locked_app = None
            self.suggested_app = None
            self.temp_ignore_list.clear()
            self.hide_suggestion()

    def remove_item(self, list_type, item):
        target = self.whitelist if list_type == "whitelist" else self.blacklist
        if item in target:
            target.remove(item)
            self.update_display(list_type)
            self.save_settings()
            if list_type == "whitelist":
                for item in list(target): self._reset_detection_state(item)

    def clear_list(self, list_type):
        target = self.whitelist if list_type == "whitelist" else self.blacklist
        if not target: return
        dialog = ConfirmDialog(self, title="Clear List?", message=f"Are you sure you want to delete all apps from the {list_type}? This cannot be undone.", danger_action=True)
        if not dialog.result: return
        if list_type == "whitelist":
            for item in list(target): self._reset_detection_state(item)
        target.clear()
        self.update_display(list_type)
        self.save_settings()

    def update_display(self, list_type):
        self.after_idle(lambda: self._rebuild_list_display(list_type))
    def _rebuild_list_display(self, list_type):
        target = self.whitelist if list_type == "whitelist" else self.blacklist
        scroll = self.white_scroll if list_type == "whitelist" else self.black_scroll
        try:
            for child in list(scroll.winfo_children()):
                try: child.update_idletasks(); child.destroy()
                except Exception: pass
        except Exception: pass
        count = len(target)
        header_text = f"Total: {count} apps"
        ctk.CTkLabel(scroll, text=header_text, font=FONT_CAPTION, text_color=COLOR_MUTED).pack(pady=(0, SPACE_SM))
        for app in target:
            row = ctk.CTkFrame(scroll, fg_color=COLOR_SURFACE, corner_radius=6)
            row.pack(pady=SPACE_XS, padx=SPACE_SM, fill="x")
            lbl_btn = ctk.CTkButton(row, text=app, font=FONT_BODY, fg_color="transparent", hover_color=COLOR_MUTED, anchor="w", command=lambda a=app: print(f"Selected: {a}"))
            lbl_btn.pack(side="left", fill="x", expand=True)
            remove_btn = ctk.CTkButton(row, text="X", width=32, fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_DARK, command=lambda a=app, lt=list_type: self.remove_item(lt, a))
            remove_btn.pack(side="right", padx=SPACE_XS)
        if not target:
            ctk.CTkLabel(scroll, text="List empty", font=FONT_CAPTION, text_color=COLOR_MUTED).pack(pady=SPACE_MD)

    def detect_monitors(self):
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
        except Exception as e: print(f"Error detecting monitors: {e}")

    def _hide_from_capture(self):
        """Hide HotSwap from OBS/screen capture using Win32 display affinity."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception as e:
            print(f"[Cloak] Could not hide from capture: {e}")

    def _show_for_capture(self):
        """Make HotSwap visible to OBS/screen capture (for demo mode)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            SetWindowDisplayAffinity(hwnd, 0)
        except Exception as e:
            print(f"[Cloak] Could not show for capture: {e}")

    def toggle_pin(self):
        is_top = bool(self.attributes("-topmost"))
        new_state = not is_top
        self.attributes("-topmost", new_state)
        if new_state:
            self.btn_pin.configure(text_color=COLOR_SUCCESS, fg_color="#333333")
            self.pin_tooltip.text = "Unpin window"
        else:
            self.btn_pin.configure(text_color=COLOR_MUTED, fg_color="transparent")
            self.pin_tooltip.text = "Pin window on top"

    def save_settings(self):
        data = {
            "version": APP_VERSION,
            "password": self.entry_pass.get(),
            "video_source": self.video_source_var.get(),
            "audio_source": self.audio_source_var.get(),
            "auto_record": self.auto_rec_var.get(),
            "auto_fit": self.auto_fit_var.get(),
            "auto_tracking": self.switch_track.get() == 1,
            "hotkey": self.detection_hotkey,
            "toggle_hotkey": self.toggle_tracking_hotkey,
            "ignore_hotkey": self.ignore_alerts_hotkey,
            "game_detection_enabled": self.game_detection_enabled,
            "frame_drop_alerts_enabled": self.frame_drop_alerts_enabled,
            "disclaimer_accepted": self.disclaimer_accepted,
            "audio_feedback_enabled": self.audio_feedback_enabled,
            "popup_notifications_enabled": self.popup_notifications_enabled,
            "audio_volume": self.audio_volume,
            "sound_detected_path": self.sound_detected_path,
            "sound_switched_path": self.sound_switched_path,
            "detection_keys": self.detection_keys,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "detection_threshold": self.detection_threshold,
            "frame_drop_threshold": self.frame_drop_threshold,
            "total_swaps": self.total_swaps,
            "window_geometry": self.geometry(),
            "is_pinned": bool(self.attributes("-topmost")),
            "scene_collection_sources": self.scene_collection_sources
        }
        try:
            with open(CONFIG_FILE, "w") as f: json.dump(data, f, indent=2)
        except Exception: pass

    def load_settings(self):
        if not os.path.exists(CONFIG_FILE):
            if getattr(sys, 'frozen', False): app_dir = os.path.dirname(sys.executable)
            else: app_dir = os.path.dirname(os.path.abspath(__file__))
            old_config = os.path.join(app_dir, "obs_tracker_config.json")
            if os.path.exists(old_config):
                try: os.rename(old_config, CONFIG_FILE)
                except Exception: pass
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, "r") as f: data = json.load(f)
            if "password" in data: self.entry_pass.insert(0, data["password"])
            if "video_source" in data: self.video_source_var.set(data["video_source"])
            if "audio_source" in data: self.audio_source_var.set(data["audio_source"])
            if "auto_record" in data: self.auto_rec_var.set(data["auto_record"])
            if "auto_fit" in data: self.auto_fit_var.set(data["auto_fit"])
            if "whitelist" in data: self.whitelist = data["whitelist"]
            if "blacklist" in data: self.blacklist = data["blacklist"]
            if "hotkey" in data:
                self.detection_hotkey = data["hotkey"]
                self.btn_record_hotkey.configure(text=self.detection_hotkey.upper())
                self.btn_add_quick.configure(text=f"Add ({self.detection_hotkey.upper()})")
            if "toggle_hotkey" in data:
                self.toggle_tracking_hotkey = data["toggle_hotkey"]
                self.btn_record_toggle_hotkey.configure(text=self.toggle_tracking_hotkey.upper())
            if "ignore_hotkey" in data:
                self.ignore_alerts_hotkey = data["ignore_hotkey"]
                self.btn_record_ignore_hotkey.configure(text=self.ignore_alerts_hotkey.upper())
            if "game_detection_enabled" in data:
                self.game_detection_enabled = data["game_detection_enabled"]
                self.game_detection_var.set(self.game_detection_enabled)
            if "frame_drop_alerts_enabled" in data:
                self.frame_drop_alerts_enabled = data["frame_drop_alerts_enabled"]
                self.frame_drop_var.set(self.frame_drop_alerts_enabled)
            if "disclaimer_accepted" in data: self.disclaimer_accepted = data["disclaimer_accepted"]
            if "audio_feedback_enabled" in data:
                self.audio_feedback_enabled = data["audio_feedback_enabled"]
                self.audio_feedback_var.set(self.audio_feedback_enabled)
            if "popup_notifications_enabled" in data:
                self.popup_notifications_enabled = data["popup_notifications_enabled"]
                self.popup_var.set(self.popup_notifications_enabled)
            if "audio_volume" in data:
                self.audio_volume = float(data["audio_volume"])
                self.audio_volume_var.set(self.audio_volume)
                self.lbl_volume_pct.configure(text=f"{int(self.audio_volume * 100)}%")
            if "sound_detected_path" in data:
                self.sound_detected_path = data["sound_detected_path"]
                if self.sound_detected_path: self.lbl_sound_detected_file.configure(text=os.path.basename(self.sound_detected_path), text_color=COLOR_SUCCESS)
            if "sound_switched_path" in data:
                self.sound_switched_path = data["sound_switched_path"]
                if self.sound_switched_path: self.lbl_sound_switched_file.configure(text=os.path.basename(self.sound_switched_path), text_color=COLOR_SUCCESS)
            if "scene_collection_sources" in data: self.scene_collection_sources = data["scene_collection_sources"]
            if "detection_keys" in data: self.detection_keys = data["detection_keys"]
            self.update_key_display()
            if "detection_threshold" in data:
                self.slider_time.set(data["detection_threshold"])
                self.detection_threshold = data["detection_threshold"]
                self.lbl_time_val.configure(text=f"{self.detection_threshold:.1f}s")
            if "frame_drop_threshold" in data:
                self.frame_drop_threshold = data["frame_drop_threshold"]
                self.slider_drop.set(self.frame_drop_threshold)
                self.lbl_drop_val.configure(text=f"{self.frame_drop_threshold}")
            if "total_swaps" in data:
                self.total_swaps = data["total_swaps"]
                self.lbl_swap_counter.configure(text=f"Total HotSwaps: {self.total_swaps}")
            if "auto_tracking" in data and data["auto_tracking"]: self._pending_auto_tracking = True
            if "window_geometry" in data:
                try: self.geometry(data["window_geometry"])
                except: pass
            if "is_pinned" in data:
                if not data["is_pinned"]:
                    self.attributes("-topmost", False)
                    self.btn_pin.configure(text_color=COLOR_MUTED, fg_color="transparent")
                    self.pin_tooltip.text = "Pin window on top"
            self.update_display("whitelist")
            self.update_display("blacklist")
        except json.JSONDecodeError:
            try: os.remove(CONFIG_FILE)
            except Exception: pass
        except Exception: pass

    def on_close(self):
        self.save_settings()
        self.destroy()

    def toggle_tracking(self):
        if self.switch_track.get() == 1:
            if not self.obs_client:
                self.lbl_current_app.configure(text="Connect to OBS first", text_color=COLOR_WARNING)
                self.switch_track.deselect()
                return
            vid = self.video_source_var.get()
            if not vid or "Select" in vid:
                self.lbl_current_app.configure(text="Set Video Source in Settings", text_color=COLOR_WARNING)
                self.switch_track.deselect()
                return
            self._reset_detection_state()
            self.is_tracking = True
            self.lbl_track_status.configure(text="Tracking is ON", text_color=COLOR_SUCCESS)
            self.lbl_current_app.configure(text="Scanning...", text_color=COLOR_PRIMARY)
            threading.Thread(target=self.tracking_loop, daemon=True).start()
        else:
            self.is_tracking = False
            self._reset_detection_state()
            self.lbl_track_status.configure(text="Tracking is OFF", text_color=COLOR_DANGER)
            self.lbl_current_app.configure(text="Paused", text_color=COLOR_MUTED)
            self.lbl_alert.configure(text="SYSTEM NORMAL", text_color=COLOR_MUTED)

if __name__ == "__main__":
    # --- FIX 1: SINGLE INSTANCE LOCK ---
    mutex_name = "HotSwap_SingleInstance_Mutex"
    mutex = win32event.CreateMutex(None, False, mutex_name)
    last_error = win32api.GetLastError()

    if last_error == winerror.ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(0, "HotSwap is already running!", "HotSwap", 0x40 | 0x1)
        sys.exit(0)

    log_file = os.path.join(app_data_dir, "hotswap_debug.log")
    if getattr(sys, 'frozen', False):
        sys.stdout = open(log_file, "w")
        sys.stderr = sys.stdout

    print(f"--- HotSwap v{APP_VERSION} Log Started ---")
    
    app = HotSwap()
    try:
        app.mainloop()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(0, f"Critical Error:\n{e}\n\nCheck logs in Settings.", "HotSwap Crashed", 16)

# you have reached the end of the code. there is nothing more to show traveler.