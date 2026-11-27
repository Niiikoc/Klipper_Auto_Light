# ☀️ Klipper Auto Light

**Klipper Auto Light** is a lightweight Klipper extension that runs your printer's lights for you:
case lights, LED strips and neopixels follow the time of day, react to your prints
(bright while printing, a green "done" glow, red on error) and fade smoothly between it all.
With [klipper-led_effect](https://github.com/julianschill/klipper-led_effect) installed it can
also switch animations for you — without you writing a single macro.

---

## ✨ Features

- 🔆 Time schedules — up to **10** per light, schedules can cross midnight
- 🌈 **Colours** for neopixel / dotstar / `[led]` strips (`warm`, `FF8800`, `green@0.5`, RGBW…)
- 💡 Works with `[output_pin]` (PWM or on/off), `[neopixel]`, `[dotstar]`, `[led]`, `[pca9533]`, `[pca9632]`
- 🧩 **Several lights at once**, whole chains or only some LEDs (`sb_leds:2-3`)
- 🖨️ **Print-aware**: own value while printing / paused, a "done" or "error" colour after the print, then back to the schedule
- 🌅 **Smooth fades** between every change (e.g. slowly dim when a print finishes)
- ✨ **Animations via [klipper-led_effect](https://github.com/julianschill/klipper-led_effect)** — rainbow, breathing, comet… picked automatically by time or print state
- 🖱️ **Control panel in Mainsail** plus ready-made macro buttons for Mainsail / Fluidd
- 🎛️ Independent light groups with `[auto_light name]` sections — combine them however you like
- ✋ Manual values stay until you return to automatic or a print starts
- 🧾 No hidden state: after a restart everything runs exactly as the config says
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
That's all you need. See [🚀 Quick Start](#-quick-start) for print-aware lighting
and LED effects, [REFERENCE.md](REFERENCE.md) for every option, and
[`example.cfg`](example.cfg) for a commented example.

> Older configs that use `pin:` instead of `lights:` keep working unchanged.

### 5️⃣ Optional: buttons for Mainsail / Fluidd
```bash
cd ~/printer_data/config
curl -O https://raw.githubusercontent.com/Niiikoc/Klipper_Auto_Light/main/auto_light_macros.cfg
```
and add `[include auto_light_macros.cfg]` to `printer.cfg`
(see [🖱️ Control from Mainsail / Fluidd](#️-control-from-mainsail--fluidd)).

### 6️⃣ Restart Klipper
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
The installer symlinks `auto_light.py` into `~/klipper/klippy/extras/` and
`auto_light_macros.cfg` into `~/printer_data/config/`, so updates pulled by
Moonraker take effect immediately. Add `[include auto_light_macros.cfg]` to
`printer.cfg` if you want the UI buttons.
(Other locations: `KLIPPER_PATH=... CONFIG_PATH=... ./install.sh`)

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

## 🚀 Quick Start

Three typical setups. Copy one into `printer.cfg` and change the light name.
Every option is in [REFERENCE.md](REFERENCE.md) and [`example.cfg`](example.cfg).

**1. Case light by time of day**
```ini
[auto_light]
lights: caselight               # your [output_pin caselight]
schedule_1: 07:00-19:00=1.0 Day
schedule_2: 19:00-23:00=0.3 Evening
schedule_3: 23:00-07:00=off Night
```

**2. Light only while printing** (great for cameras and timelapses)
```ini
[auto_light]
lights: caselight
idle: off                       # not printing: off
printing: 1.0                   # printing: full brightness
complete: 1.0                   # keep it on after the print ...
show_result_for: 600            # ... for 10 minutes ...
fade_time: 20                   # ... then fade out over 20 s
```

**3. Status LEDs with animations** (needs [klipper-led_effect](https://github.com/julianschill/klipper-led_effect))
```ini
[auto_light leds]
lights: sb_leds                 # your [neopixel sb_leds]
idle: purple@0.3                # calm colour when not printing
printing: white
complete: effect:sb_rainbow     # your [led_effect sb_rainbow] ...
error: effect:sb_error          # ... and [led_effect sb_error]
show_result_for: 30             # results play for 30 s, then back to purple
```

Values can be a brightness (`0.6`), a colour (`warm`, `FF8800`, `green@0.5`), `off`
or `effect:<name>`. Several groups can run side by side, see
[Multiple groups](REFERENCE.md#multiple-groups).

You need **no macros** in `START_PRINT` / `END_PRINT`: Auto Light reads the print state
from Klipper by itself. Remove any `SET_LED` / `SET_PIN` for these lights from those
macros, or they will fight with Auto Light.

---

## 🧠 How It Works

Every group decides what to show in this order (the first match wins):

1. **A value you set by hand** (`AUTOLIGHT_ON`/`OFF`, panel buttons). It lasts
   until `AUTOLIGHT_AUTO` or the next print start.
2. **Print values**: `printing`/`paused` during the print, then `complete`, `error` or
   `cancelled` for `show_result_for` seconds.
3. **Schedules**: the matching `schedule_N`, otherwise `idle`.

`off` is just a brightness. It never stops Auto Light, and the next schedule turns
the light back on.

### Turning it off
| You want | Do |
|---|---|
| Stop Auto Light for now | `AUTO_LIGHT_DISABLE` (all groups) or `AUTO_LIGHT_DISABLE LIGHT=leds` |
| Turn it back on | `AUTO_LIGHT_ENABLE` (or just restart Klipper) |
| Stop it permanently | `enabled: False` in the section, or remove the section |

**Nothing is saved.** After a restart every group runs as the config says.
When Auto Light is off, the light is **left as it is**, not switched off.

> Advanced: `PART=schedule` or `PART=print` turns off only one half, e.g.
> `AUTO_LIGHT_DISABLE PART=schedule` keeps the print colours but stops following
> the time. See [Switches](REFERENCE.md#switches).

### What do I see, and why?
`AUTO_LIGHT_LIST_SCHEDULES` and the panel show it for each group, e.g.
`AutoLight [default]: schedule ON | print ON | now: 30% (Evening 19:00-23:00)`.

| The status ends in | Why | To change it |
|---|---|---|
| `(Evening 19:00-23:00)` | A schedule applies | — |
| `(idle)` | No schedule matches now, so `idle:` applies | — |
| `(printing)` / `(complete)` / `(error)` | A print value applies | wait |
| `(manual, 25 s left)` / `(manual, until AUTO_LIGHT_RESUME ...)` | You set a value by hand | `AUTOLIGHT_AUTO` |
| `(automation off, left as is)` | `AUTO_LIGHT_DISABLE` was used | `AUTO_LIGHT_ENABLE` |

---

## 🖱️ Control from Mainsail / Fluidd

With `[include auto_light_macros.cfg]` (see installation step 5) you get these buttons:

| Button | What it does |
|---|---|
| `AUTOLIGHT_PANEL` | Opens the control panel (Mainsail v2.9+): status, Auto / On / Dim / Off, effect buttons, Schedule and Print switches |
| `AUTOLIGHT_AUTO` | Back to automatic now |
| `AUTOLIGHT_ON` | On until `AUTOLIGHT_AUTO` or the next print (`VALUE=warm@0.5`, `VALUE=effect:rainbow`, `DURATION=30` optional) |
| `AUTOLIGHT_OFF` | Off until `AUTOLIGHT_AUTO` or the next print |
| `AUTOLIGHT_ENABLE` / `AUTOLIGHT_DISABLE` | Turn Auto Light on/off until the next restart |

All accept an optional `LIGHT=<group>`. A plain `[auto_light]` is `LIGHT=default`.
The full command list is in [REFERENCE.md](REFERENCE.md#g-code-commands).

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| Light changes at the wrong time | Check the Pi's timezone: `timedatectl`, then `sudo timedatectl set-timezone Europe/Athens` (your zone) |
| `light '...' not found` | Use the name after the section type, e.g. `[neopixel sb_leds]` → `sb_leds` |
| Brightness is only on/off | Your `[output_pin]` needs `pwm: True` |
| Colours look wrong | Check `color_order` in your `[neopixel]` section |
| `effect '...' not found` | Install klipper-led_effect and define `[led_effect <name>]` with exactly that name |
| No dialog appears | The control panel needs Mainsail v2.9+; use the `AUTOLIGHT_*` buttons otherwise |
| Hex colour ignored | Don't write `#` before the hex value |
| Light is off after `FIRMWARE_RESTART` | Klipper restarts every `[output_pin]` at its `value:` (0 by default). With Auto Light on, the light then fades to its automatic value (with `idle: off` it stays off). With Auto Light off, set `value: 1` in `[output_pin ...]` to start it on |
| `error:` value not shown | It applies when a print stops with an error while Klipper keeps running (e.g. a G-code or macro error). On a Klipper **shutdown** (thermal runaway, MCU lost, "Timer too close") every module stops, Auto Light included |
| Light doesn't change when Auto Light is off | Expected: `AUTO_LIGHT_DISABLE` leaves the light as it is. Without `LIGHT=` it turns off **all** groups |
| Auto Light is on again after a restart | Expected: nothing is saved. Use `enabled: False` for a permanent change |
| `option 'default' is now called 'idle'` | Rename the option as the message says (also `finish_hold` → `show_result_for`) |
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
rm -f ~/printer_data/config/auto_light_macros.cfg
rm -rf ~/Klipper_Auto_Light                    # remove the cloned repo
```
Then remove the `[update_manager auto_light]` block from your `moonraker.conf` and restart Moonraker.

**In both cases:** remove the `[auto_light]` section(s) and any `[include auto_light_macros.cfg]` from your `printer.cfg`, delete `auto_light_state.json` from your config folder if an older version left one, and restart Klipper.

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
- 🖨️ Print-aware values: `printing`, `paused`, `complete`, `error`, `cancelled`, `show_result_for`
- 🔀 `AUTO_LIGHT_ENABLE/DISABLE PART=schedule|print` to turn off only the time schedule or only the print reaction, toggle buttons in the panel
- 👀 Switch positions, the manual value and its time left are shown in `AUTO_LIGHT_LIST_SCHEDULES`, the panel and the Moonraker status (`schedule_enabled`, `print_enabled`, `manual`, `manual_remaining`)
- ⚠️ **Nothing is saved anymore:** `AUTO_LIGHT_DISABLE` and `AUTO_LIGHT_SCHEDULE_DISABLE` last until the next restart (v2.1 saved them, which could leave the lights paused without any sign). Use `enabled: False` for a permanent change; `auto_light_state.json` can be deleted
- ✋ One rule for manual values: they last until `AUTO_LIGHT_RESUME` or a print starts (or for `DURATION`), and the console says when they end
- 🏷️ `SET_AUTO_LIGHT` is now `AUTO_LIGHT_RESUME` (the old name still works)
- 🐛 `AUTO_LIGHT_RESUME` no longer reports "check executed" when automation is off; it reports what it did, or why it could not
- 🌅 Smooth fades (`fade_time`)
- ✨ klipper-led_effect integration: `effect:<name>` values with crossfades
- 🖱️ `AUTO_LIGHT_MENU` control panel (Mainsail) and `auto_light_macros.cfg` buttons
- ⏲️ `AUTO_LIGHT_SET ... DURATION=`; effects started by hand stop on their own after `show_result_for`
- ⏱️ Changes happen exactly at schedule boundaries instead of every `check_interval`
- 📚 Shorter README with a Quick Start; all details moved to `REFERENCE.md`
- 🧪 Simulation tests (`python -m unittest discover tests`) and test G-code files for the printer (`tests/printer/`)
- ✨ New `AUTO_LIGHT_SET` command, optional schedule names, `idle` value, up to 10 schedules
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
