obs = obslua

-- SwitchPilot Auto-Launcher
-- This script launches SwitchPilot when OBS starts.
-- Path is configured automatically by SwitchPilot's install button.

local app_path = "{{SWITCHPILOT_PATH}}"

function script_description()
    return "Launches SwitchPilot automatically when OBS starts.\n\nPath: " .. app_path
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