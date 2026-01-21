# SwitchPilot

Automatic OBS source switching for streamers who forget to switch scenes.

SwitchPilot detects which application you're using and automatically updates your OBS video/audio capture sources to follow it. If you play multiple games in a stream and constantly forget to switch your game capture, this fixes that.

## Requirements

- Windows 10/11
- OBS Studio with WebSocket server enabled (Tools > WebSocket Server Settings)
- Python 3.8+ (only if running from source)

## How It Works

The app connects to OBS via WebSocket and monitors your foreground window. When you switch to a different application, it updates your designated video/audio sources to capture that window instead.

**Game Detection**

SwitchPilot watches for gaming activity by checking if you're holding down movement keys (WASD by default). If you're actively using an app that isn't already in your whitelist or blacklist, it'll pop up a suggestion to add it. This is purely detection - no keystrokes are recorded or stored anywhere.

The relevant code is in the `heuristic_loop` function if you want to verify:
```python
for key in self.detection_keys:
    if keyboard.is_pressed(key):
        is_active = True
        break
```

That's it. It checks if keys are currently held, nothing more.

## Setup

1. Open OBS and enable the WebSocket server (Tools > WebSocket Server Settings)
2. Set a password and note it down
3. Run SwitchPilot
4. Go to the Settings tab and enter your WebSocket password
5. Click Connect
6. Select your video capture source and audio capture source from the dropdowns
7. Choose which monitor to track
8. Enable auto-tracking on the Dashboard tab

## Auto-Launch with OBS

SwitchPilot can automatically start when you open OBS.

**Automatic Install (Recommended)**

1. In SwitchPilot, go to Settings
2. Scroll to "OBS Integration"
3. Click "Install OBS Script"
4. Open OBS and go to Tools > Scripts
5. Click the + button and select `SwitchPilot_Launcher.lua`

The script will now launch SwitchPilot whenever OBS starts.

**Manual Install (If automatic fails)**

If the automatic install doesn't work (permissions issues, non-standard OBS install, etc.):

1. Create a file called `SwitchPilot_Launcher.lua` with this content:

```lua
obs = obslua

local app_path = "C:\\path\\to\\SwitchPilot.exe"

function script_description()
    return "Launches SwitchPilot when OBS starts."
end

function on_event(event)
    if event == obs.OBS_FRONTEND_EVENT_FINISHED_LOADING then
        os.execute('start "" "' .. app_path .. '"')
    end
end

function script_load(settings)
    obs.obs_frontend_add_event_callback(on_event)
end
```

2. Replace the path with the actual path to SwitchPilot.exe (use double backslashes)
3. Save the file to `%APPDATA%\obs-studio\basic\scripts\`
4. In OBS, go to Tools > Scripts and add the script

## Configuration

All settings are saved to `switchpilot_config.json` in the same folder as the executable. This includes your auto-tracking toggle state, so if you leave it enabled when you close the app, it'll be enabled next time you open it.

**Whitelist vs Blacklist**

- If the whitelist is empty, SwitchPilot tracks everything except blacklisted apps
- If you add apps to the whitelist, it only tracks those specific apps
- Common non-game apps (explorer, chrome, discord, etc.) are blacklisted by default

**Activity Keys**

The default keys for game detection are W, A, S, D. You can change these in Settings if your games use different controls.

## Common Issues

**"Connect to OBS first"**

The WebSocket connection failed. Check that:
- OBS is running
- WebSocket server is enabled in OBS (Tools > WebSocket Server Settings)
- The password matches
- Port 4455 isn't blocked

**"Capture failed - try running as Admin"**

Some games require admin privileges to capture. Right-click SwitchPilot and run as administrator.

**"Incorrect password"**

The WebSocket password doesn't match. Double-check it in OBS under Tools > WebSocket Server Settings.

**Source not switching**

Make sure you've selected the correct video source in Settings. It should be a Window Capture or Game Capture source, not a Display Capture.

## Building from Source

Install dependencies:
```
pip install customtkinter obsws-python keyboard psutil pywin32
```

Run directly:
```
python SwitchPilot.py
```

Build executable:
```
pip install pyinstaller
pyinstaller SwitchPilot.spec
```

The executable will be in the `dist` folder.

## Uninstalling

SwitchPilot doesn't install anything to your system. To remove it:

1. Delete the SwitchPilot folder/files
2. Delete `switchpilot_config.json` if it exists

That's it. No registry entries, no leftover files elsewhere.

Your OBS sources will keep working normally after removal - SwitchPilot only changes which window they capture, it doesn't modify OBS itself. Your sources will just stay pointed at whatever window they were last set to.

## Privacy

This app does not:
- Log keystrokes
- Send any data anywhere
- Access the internet (except localhost for OBS WebSocket)
- Store anything except your settings

The keyboard library is used solely to detect if movement keys are being held to identify gaming activity. The source code is available for review.

## License

MIT License - do whatever you want with it.

## Support

If this saved you from forgetting to switch scenes, consider tossing a few bucks my way. Donations keep the project going but are never required.
