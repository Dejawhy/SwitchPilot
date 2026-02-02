# HotSwap

OBS does not warn you when your game capture fails, freezes, or points at the wrong window.

If you alt-tab, launch a new game, or forget to switch scenes, OBS will happily keep streaming the wrong thing — often without any indication that something went wrong.

HotSwap is a lightweight OBS assistant that detects when your active game changes and automatically updates your video/audio capture sources *while you're live*.

This isn’t about “forgetting”.
It’s about OBS providing no real-time feedback when capture silently fails.

## Common OBS Problems This Solves

- OBS keeps streaming the wrong game
- Game Capture freezes without warning
- Scene didn’t switch when launching a new game
- Alt-tabbing breaks capture mid-stream
- **Popups showing on stream:** HotSwap alerts are invisible to OBS capture
- **Multi-Monitor confusion:** Alerts now appear on the correct monitor

## Requirements

- Windows 10/11
- OBS Studio with WebSocket server enabled (Tools > WebSocket Server Settings)
- Python 3.8+ (only if running from source)

## How It Works

The app connects to OBS via WebSocket and monitors your foreground window. When you switch to a different application, it updates your designated video/audio sources to capture that window instead.

**Focus Lock**

When HotSwap switches to a game, it locks onto that game. This prevents unwanted switching when you alt-tab to Discord, a browser, or another app. The lock releases when:
- The game closes
- You toggle tracking off and back on (double-tap the hotkey)
- You add a new game via the quick-add hotkey (the lock transfers to the new game)

**Game Detection**

HotSwap watches for gaming activity by checking if you're holding down movement keys (WASD by default) or custom combinations (like Shift+W). If you're actively using an app that isn't already in your whitelist or blacklist, it'll pop up a suggestion to add it. This is purely detection - no keystrokes are recorded or stored anywhere.

**Stream-Safe Overlays**

All HotSwap popups (Game Detected, Frame Drops, etc.) use window affinity masking. This means **you** can see them on your screen, but **OBS cannot see them**. They will not appear on your stream, even if you are using Display Capture.

**Anti-Cheat Games**

Some anti-cheat software (Vanguard, EasyAntiCheat, BattlEye) might flag keyboard detection as suspicious. If you're playing games with aggressive anti-cheat, you can disable game detection in Settings. This disables the automatic "new game detected" feature, but tracking still works - you just need to add games to your whitelist manually.

## Setup

1. Open OBS and enable the WebSocket server (Tools > WebSocket Server Settings)
2. Set a password and note it down
3. Run HotSwap
4. Go to the Settings tab and enter your WebSocket password
5. Click Connect
6. Select your video capture source and audio capture source from the dropdowns
7. Choose which monitor to track
8. Enable auto-tracking on the Dashboard tab

## Auto-Launch with OBS

HotSwap can automatically start when you open OBS.

**Automatic Install (Recommended)**

1. In HotSwap, go to Settings
2. Scroll to "OBS Integration"
3. Click "Install OBS Script"
4. Open OBS and go to Tools > Scripts
5. Click the + button and select `HotSwap_Launcher.lua`

The script will now launch HotSwap whenever OBS starts.

**Manual Install (If automatic fails)**

If the automatic install doesn't work (permissions issues, non-standard OBS install, etc.):

1. Create a file called `HotSwap_Launcher.lua` with this content:

```lua
obs = obslua

local app_path = "C:\\path\\to\\HotSwap.exe"

function script_description()
    return "Launches HotSwap when OBS starts."
end

function on_event(event)
    if event == obs.OBS_FRONTEND_EVENT_FINISHED_LOADING then
        os.execute('start "" "' .. app_path .. '"')
    end
end

function script_load(settings)
    obs.obs_frontend_add_event_callback(on_event)
end

2. Replace the path with the actual path to HotSwap.exe (use double backslashes)
3. Save the file to `%APPDATA%\obs-studio\basic\scripts\`
4. In OBS, go to Tools > Scripts and add the script

## Configuration

All settings are saved to `hotswap_config.json` in the same folder as the executable. This includes your auto-tracking toggle state, so if you leave it enabled when you close the app, it'll be enabled next time you open it.

**Whitelist vs Blacklist**

- If the whitelist is empty, HotSwap tracks everything except blacklisted apps
- If you add apps to the whitelist, it only tracks those specific apps
- Common non-game apps (explorer, chrome, discord, etc.) are blacklisted by default

**Activity Keys**

The default keys for game detection are W, A, S, D. You can change these in Settings if your games use different controls.

**Hotkeys**

Hotkey	        Default	    Action
Quick-Add	        F9	    Adds the detected game to whitelist and switches to it
Toggle Tracking	    F10	    Turns auto-tracking on/off (releases focus lock when off)

Both hotkeys can be changed in Settings.

Common Issues
"Error: Port 4455 is closed"

HotSwap cannot find the OBS WebSocket server.

Ensure "Enable WebSocket server" is checked in OBS (Tools > WebSocket Server Settings).

Ensure the port in OBS is set to 4455.

"Capture failed - try running as Admin"

Some games require admin privileges to capture. Right-click HotSwap and run as administrator.


"Error: Incorrect WebSocket Password"

The server was found, but the password failed. Double-check it in OBS under Tools > WebSocket Server Settings.

**Source not switching**

Make sure you've selected the correct video source in Settings. It should be a Window Capture or Game Capture source, not a Display Capture.


"Error: Connection Timed Out"

Something is blocking the connection (usually a firewall).

Check your Windows Firewall or Antivirus settings.

Ensure HotSwap.exe is allowed to communicate on localhost

## Building from Source

Install dependencies:
```
pip install customtkinter obsws-python keyboard psutil pywin32
```

Run directly:
```
python HotSwap.py
```

Build executable:
```
pip install pyinstaller
pyinstaller HotSwap.spec
```

The executable will be in the `dist` folder.

## Uninstalling

HotSwap doesn't install anything to your system. To remove it:

1. Delete the HotSwap folder/files
2. Delete `hotswap_config.json` if it exists

That's it. No registry entries, no leftover files elsewhere.

Your OBS sources will keep working normally after removal - HotSwap only changes which window they capture, it doesn't modify OBS itself. Your sources will just stay pointed at whatever window they were last set to.

## Privacy

This app does not:
- Log keystrokes
- Send any data anywhere
- Access the internet (except localhost for OBS WebSocket)
- Store anything except your settings

The keyboard library is used solely to detect if movement keys are being held to identify gaming activity. The source code is available for review.

## License

GNU General Public License v3.0

## Support

If this saved you from forgetting to switch scenes, consider tossing a few bucks my way. Donations keep the project going but are never required.

