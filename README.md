# ☀️ Klipper Auto Light

**Klipper Auto Light** is a lightweight Klipper extension that runs your printer's lights for you:
case lights, LED strips and neopixels follow the time of day, react to your prints
(bright while printing, a green "done" glow, red on error) and fade smoothly between it all.

---

## ✨ Features

- 🔆 Time schedules — up to **10** per light, schedules can cross midnight
- 🌈 **Colours** for neopixel / dotstar / `[led]` strips (`warm`, `FF8800`, `green@0.5`, RGBW…)
- 💡 Works with `[output_pin]` (PWM or on/off), `[neopixel]`, `[dotstar]`, `[led]`, `[pca9533]`, `[pca9632]`
- 🧩 **Several lights at once**, whole chains or only some LEDs (`sb_leds:2-3`)
- 🖨️ **Print-aware**: own value while printing / paused, a "done" or "error" colour after the print, then back to the schedule
- 🌅 **Smooth fades** between every change (e.g. slowly dim when a print finishes)
- 🎛️ Independent light groups with `[auto_light name]` sections — combine them however you like
- ✋ Manual changes are respected until the next schedule or print change
- 💾 Enabled/disabled state (and disabled schedules) survive restarts
- 🪶 Lightweight: sleeps until the next change, no busy loops

---

## 📦 Installation

### 1️⃣ Connect to your Raspberry Pi via SSH
```bash
ssh pi@{printer_IP}.local
```
Replace `{printer_IP}` with the IP address of your printer.

### 2️⃣ Navigate to the Klipper extras directory
```bash
cd ~/klipper/klippy/extras
```

### 3️⃣ Download the script
```bash
curl -O https://raw.githubusercontent.com/Niiikoc/Klipper_Auto_Light/main/auto_light.py
```

### 4️⃣ Edit your printer.cfg
**Minimal setup — add this section:**
```ini
[auto_light]
lights: caselight               # Name of your [output_pin] / [neopixel] / [led] ...
schedule_1: 07:00-19:00=1.0     # Day: 100%
schedule_2: 19:00-23:00=0.3     # Evening: 30%
schedule_3: 23:00-07:00=0.0     # Night: off
```
That's all you need. See [⚙️ Configuration](#️-configuration) for colours,
print-aware lighting, fades and multiple lights, and
[`example.cfg`](example.cfg) for a fully commented reference.

> Older configs that use `pin:` instead of `lights:` keep working unchanged.

### 5️⃣ Restart Klipper
```gcode
FIRMWARE_RESTART
```

---

## 🔄 Updating via Moonraker (Update Manager)

Instead of the loose-file `curl` method above, you can install the module as a
git repository so it appears in Mainsail/Fluidd's **Update** panel and can be
updated with a single click.

### 1️⃣ Clone the repo and run the installer
```bash
cd ~
git clone https://github.com/Niiikoc/Klipper_Auto_Light.git
cd ~/Klipper_Auto_Light
chmod +x install.sh
./install.sh
```
The installer symlinks `auto_light.py` into `~/klipper/klippy/extras/`, so
updates pulled by Moonraker take effect immediately.

> **Note:** If you previously installed with the `curl` method, delete the old
> copy first so the symlink can be created:
> `rm -f ~/klipper/klippy/extras/auto_light.py`

### 2️⃣ Add the Update Manager section to `moonraker.conf`
```ini
[update_manager auto_light]
type: git_repo
path: ~/Klipper_Auto_Light
origin: https://github.com/Niiikoc/Klipper_Auto_Light.git
primary_branch: main
managed_services: klipper
install_script: install.sh
```

### 3️⃣ Restart Moonraker
```bash
sudo systemctl restart moonraker
```

`auto_light` will now show up in the Update Manager. When a new version is
pushed to GitHub, click **Update** and Moonraker pulls the changes and restarts
Klipper for you.

---

## ⚙️ Configuration

### All options
```ini
[auto_light]
lights: caselight          # One or more lights, comma separated (see below)
#color: white              # Base colour that plain brightness values use (LEDs only)
#fade_time: 1.0            # Seconds to fade between values (0 = instant)
#enabled: True             # Default on the very first startup (afterwards the
                           # saved AUTO_LIGHT_ENABLE/DISABLE choice is used)
#check_interval: 600       # Safety re-check in seconds (time changes, NTP sync)
#state_file: ~/printer_data/config/auto_light_state.json

# Time schedules: schedule_1 ... schedule_10
# Format: HH:MM-HH:MM=value [optional name]
schedule_1: 07:00-19:00=1.0 Day
schedule_2: 19:00-07:00=warm@0.2 Night

#default: off              # Used when no schedule matches (or instead of schedules)

# Print-aware values (all optional — anything not set falls back to the schedule)
#printing: white           # While a print is running
#paused: orange@0.6        # While paused (defaults to the 'printing' value)
#complete: green@0.5       # After a successful print ...
#error: red                # ... after an error ...
#cancelled: off            # ... after a cancelled print ...
#finish_hold: 300          # ... for this many seconds, then back to the schedule
```

### Light names
`lights:` takes the names of your existing Klipper sections — Auto Light finds out
the type by itself:

| Your section | Write |
|---|---|
| `[output_pin caselight]` | `lights: caselight` |
| `[neopixel sb_leds]` | `lights: sb_leds` |
| Only LEDs 2 and 3 of that chain | `lights: sb_leds:2-3` |
| Only LED 1 | `lights: sb_leds:1` |
| Several at once | `lights: caselight, sb_leds:2-3, bed_strip` |

Non-PWM `[output_pin]`s (plain on/off relays) are switched **on** for any value above 0.

### Values and colours
Every schedule, `default`, print value and the `AUTO_LIGHT_SET` command accept:

| Value | Meaning |
|---|---|
| `0.6` | Brightness 0.0–1.0 (of the base `color`, white by default) |
| `warm` | Named colour: `off`, `white`, `warm`, `red`, `green`, `blue`, `yellow`, `orange`, `purple`, `magenta`, `cyan` |
| `FF8800` | Hex colour `RRGGBB` — **without `#`** (Klipper treats `#` as a comment) |
| `FFFFFF80` | Hex `RRGGBBWW` for RGBW strips (white channel) |
| `warm@0.4` | Any colour at a given brightness |

On an `[output_pin]` a colour simply becomes its brightness (`green@0.5` → 50%).

---

## 🖨️ Print-Aware Lighting

Light up the printer only when it matters — great for cameras and timelapses:

```ini
[auto_light]
lights: caselight
default: off            # Idle: off
printing: 1.0           # Printing: full brightness
complete: 1.0           # Keep it on after the print so you can look at it ...
finish_hold: 600        # ... for 10 minutes ...
fade_time: 20           # ... then fade out slowly over 20 seconds
```

Or combine it with a day schedule: the schedule is the "idle" look, printing
overrides it, and when the print finishes the light fades back to the schedule.

---

## 🌈 Multiple Lights and Combinations

Each `[auto_light name]` section is an independent group with its own lights,
schedules and print rules. Mix them freely — e.g. on a Stealthburner:

```ini
[auto_light case]                 # Case light follows the time of day
lights: caselight
schedule_1: 08:00-22:00=0.8
schedule_2: 22:00-08:00=0.1
printing: 1.0

[auto_light logo]                 # Logo LED: calm colour, status colours on print
lights: sb_leds:1
default: purple@0.3
printing: blue
complete: green
error: red
finish_hold: 900

[auto_light nozzle]               # Nozzle LEDs: only on while printing
lights: sb_leds:2-3
default: off
printing: FFFFFFFF                # RGBW full white
fade_time: 3
```

A plain `[auto_light]` (no name) is addressed as `LIGHT=default`.

---

## 🧩 G-Code Commands

`LIGHT=<name>` is optional — without it a command applies to **all** groups
(the schedule commands need it only when you have more than one group).

| Command | Description |
|---------|-------------|
| `SET_AUTO_LIGHT [LIGHT=]` | Re-apply the value for the current time/print state now |
| `AUTO_LIGHT_ENABLE [LIGHT=]` | Enable automatic control (saved across restarts) |
| `AUTO_LIGHT_DISABLE [LIGHT=]` | Disable automatic control (saved across restarts) |
| `AUTO_LIGHT_SET VALUE= [LIGHT=]` | Temporarily set a value/colour (e.g. `VALUE=warm@0.5`) until the next change — handy to try colours |
| `AUTO_LIGHT_LIST_SCHEDULES [LIGHT=]` | Show lights, schedules, print values and status |
| `AUTO_LIGHT_SCHEDULE_ENABLE ID= [LIGHT=]` | Enable schedule ID (saved) |
| `AUTO_LIGHT_SCHEDULE_DISABLE ID= [LIGHT=]` | Disable schedule ID (saved) |

### Examples
```gcode
AUTO_LIGHT_SCHEDULE_DISABLE ID=2            # Working late: skip the evening dim
AUTO_LIGHT_SET VALUE=FF8800@0.5 LIGHT=logo  # Preview a colour
SET_AUTO_LIGHT                              # Back to the automatic value
AUTO_LIGHT_DISABLE LIGHT=nozzle             # Turn off automation for one group
```

### A button for Mainsail / Fluidd
```ini
[gcode_macro LIGHTS_AUTO]
description: Return all lights to automatic mode
gcode:
    SET_AUTO_LIGHT
```

---

## 🏠 Status for Mainsail, Fluidd and Home Assistant

Each group exposes its status through Moonraker as the printer object
`auto_light` (or `auto_light <name>`):

```
enabled, light, mode (schedule / default / printing / paused / complete / error / cancelled),
current_brightness, current_color, target_brightness, target_color,
active_schedule_id, active_schedule_name, current_time, lights, schedules[]
```

Use it in macros (`printer["auto_light logo"].mode`) or with the
[Moonraker Home Assistant integration](https://github.com/marcolivierarsenault/moonraker-home-assistant)
to show which mode the lights are in.

---

## 🧠 How It Works

1. On startup Auto Light applies the right value immediately.
2. It then **sleeps until the next schedule boundary** — changes happen on the
   exact minute, not up to 10 minutes late — with a safety re-check every
   `check_interval` seconds (clock changes, NTP sync on boot).
3. If print values are configured it also reads Klipper's print state every 2 s
   (a simple in-memory lookup, no G-code involved).
4. Changes are faded in small steps; each step is sent as a single batched command.
5. Your manual changes (`SET_PIN`, `SET_LED`, UI sliders) are **kept until the
   next schedule or print change** — use `SET_AUTO_LIGHT` to return to automatic.
6. `AUTO_LIGHT_ENABLE/DISABLE` and disabled schedules are saved to `state_file`.

### Protection Against Errors
- Wrong light names, times or colours are reported as a clear config error on startup
- Gaps or overlaps between schedules are logged as a warning in `klippy.log`
- The last enabled schedule can't be disabled unless a `default` value is set

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| Light changes at the wrong time | Check the Pi's timezone: `timedatectl`, then `sudo timedatectl set-timezone Europe/Athens` (your zone) |
| `light '...' not found` | Use the name after the section type, e.g. `[neopixel sb_leds]` → `sb_leds` |
| Brightness is only on/off | Your `[output_pin]` needs `pwm: True` |
| Colours look wrong | Check `color_order` in your `[neopixel]` section |
| Hex colour ignored | Don't write `#` before the hex value |
| Something else | Search `klippy.log` for `AutoLight` and open an [issue](https://github.com/Niiikoc/Klipper_Auto_Light/issues) with that part of the log |

---

## 🧩 Uninstallation

**If you installed with the `curl` method:**
```bash
cd ~/klipper/klippy/extras
rm -f auto_light.py
```

**If you installed via the Update Manager (git clone):**
```bash
rm -f ~/klipper/klippy/extras/auto_light.py   # remove the symlink
rm -rf ~/Klipper_Auto_Light                    # remove the cloned repo
```
Then remove the `[update_manager auto_light]` block from your `moonraker.conf` and restart Moonraker.

**In both cases:** remove the `[auto_light]` section from your `printer.cfg`, delete the leftover `auto_light_state.json` from your config folder if present, and restart Klipper.

---

## 🪄 License

This project is licensed under the MIT License.

---

## 🙏 Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to check the [issues page](https://github.com/Niiikoc/Klipper_Auto_Light/issues).

---

## 📝 Changelog

### v3.0.0
- 🌈 Support for `[neopixel]`, `[dotstar]`, `[led]`, `[pca9533]`, `[pca9632]` with colours (named, hex, RGBW, `colour@brightness`)
- 🧩 Several lights per group (`lights:`), LED index ranges (`sb_leds:2-3`) and independent `[auto_light name]` groups
- 🖨️ Print-aware values: `printing`, `paused`, `complete`, `error`, `cancelled`, `finish_hold`
- 🌅 Smooth fades (`fade_time`)
- ⏱️ Changes happen exactly at schedule boundaries instead of every `check_interval`
- ✋ Manual light changes are no longer overwritten until the next scheduled change
- 💾 Disabled schedules are now saved across restarts too
- ✨ New `AUTO_LIGHT_SET` command, optional schedule names, `default` value, up to 10 schedules
- 🛡️ Clear config errors, warnings for schedule gaps/overlaps, safer G-code execution from timers
- 📄 `Macro.txt` renamed to `example.cfg`
- ♻️ Existing v2 configs (`pin:` + `schedule_N`) work unchanged

### v2.1.0
- 💾 Enable/disable state now persists across restarts (saved to a JSON state file)
- ⚙️ New optional `state_file` config option to customize where state is stored
- 🔄 Added Moonraker Update Manager support (`install.sh`) for one-click updates
- 🐛 Removed a non-existent `AUTO_LIGHT_RESET_CACHE` command from the docs

### v2.0.0
- ✨ Added support for up to 5 custom time schedules
- 🔧 New commands to enable/disable individual schedules
- 🌍 Support for schedules crossing midnight
- 📊 Added schedule listing command
- 🏠 Enhanced Home Assistant integration
- 🇬🇧 All logs and messages in English

### v1.0.0
- 🎉 Initial release with basic day/night cycle
