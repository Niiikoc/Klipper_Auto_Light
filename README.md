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
- 🔀 **Two switches per group**: *Schedule* (time of day) and *Print* (print state), each can be turned off on its own
- ✋ Manual values stay until you return to automatic or a print starts
- 💾 Switches and disabled schedules survive restarts (and are announced in the console)
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

## ⚙️ Configuration

### All options
```ini
[auto_light]
lights: caselight          # One or more lights, comma separated (see below)
#color: white              # Base colour that plain brightness values use (LEDs only)
#fade_time: 1.0            # Seconds to fade between values (0 = instant)
#enabled: True             # Start position of the Schedule and Print switches
                           # (see "How It Works" below)
#check_interval: 600       # Safety re-check in seconds (time changes, NTP sync)
#state_file: ~/printer_data/config/auto_light_state.json

# Time schedules: schedule_1 ... schedule_10
# Format: HH:MM-HH:MM=value [optional name]
schedule_1: 07:00-19:00=1.0 Day
schedule_2: 19:00-07:00=warm@0.2 Night

#idle: off                 # Used when no schedule matches (or instead of schedules)

# Print-aware values (all optional — anything not set falls back to the schedule)
#printing: white           # While a print is running
#paused: orange@0.6        # While paused (defaults to the 'printing' value)
#complete: green@0.5       # After a successful print ...
#error: red                # ... after an error ...
#cancelled: off            # ... after a cancelled print ...
#show_result_for: 300      # ... for this many seconds, then back to the schedule
```

> Renamed options: `default:` → `idle:`, `finish_hold:` → `show_result_for:`.
> The old names keep working.

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
| `effect:rainbow` | Run `[led_effect rainbow]` (see [✨ LED Effects](#-led-effects-klipper-led_effect)) |

On an `[output_pin]` a colour simply becomes its brightness (`green@0.5` → 50%).

---

## 🖨️ Print-Aware Lighting

Light up the printer only when it matters — great for cameras and timelapses:

```ini
[auto_light]
lights: caselight
idle: off               # Not printing: off
printing: 1.0           # Printing: full brightness
complete: 1.0           # Keep it on after the print so you can look at it ...
show_result_for: 600    # ... for 10 minutes ...
fade_time: 20           # ... then fade out slowly over 20 seconds
```

Or combine it with a day schedule: the schedule is the "idle" look, printing
overrides it, and when the print finishes the light fades back to the schedule.

---

## ✨ LED Effects (klipper-led_effect)

Animations are **not** rendered by Auto Light — that's the job of
[klipper-led_effect](https://github.com/julianschill/klipper-led_effect).
Auto Light only decides *which* effect should run *when*, and sends a single
`SET_LED_EFFECT` command when that changes. So it adds no load of its own.

1. Install led_effect and define your effects as usual, e.g.
   ```ini
   [led_effect sb_printing]
   leds: neopixel:sb_leds
   frame_rate: 12
   layers: breathing 3 1 top (0.0, 0.3, 1.0)
   ```
2. Use them anywhere a value is accepted, with `effect:<name>`:
   ```ini
   [auto_light sb]
   lights: sb_leds                 # used for the plain colours below
   idle: warm@0.2                  # not printing: static colour
   schedule_1: 23:00-07:00=off Night
   printing: effect:sb_printing    # animation while printing
   complete: effect:sb_rainbow     # celebrate ...
   error: effect:sb_error
   show_result_for: 120            # ... for 2 minutes, then back to warm@0.2
   fade_time: 1
   ```

How switching works:
- **Effect → effect:** crossfade (`REPLACE=1 FADETIME=fade_time`), the old one is stopped.
- **Effect → colour:** the effect fades out, then Auto Light fades the colour in.
- **Colour → effect:** the effect takes over the LEDs it is defined for.
- A group may consist of effects only — then `lights:` can be left out and `off` simply stops the effect.
- Unknown effect names are reported as a config error on startup.

> 💡 **Keep it light while printing:** animations are drawn by the Pi and sent to the
> MCU many times per second. Prefer a low `frame_rate` (10–15) and calm effects for
> `printing:`, and save the fancy ones for `complete:` or idle times.

---

## 🖱️ Control from Mainsail / Fluidd

### Control panel (Mainsail)
Run `AUTO_LIGHT_MENU` (or click **AUTOLIGHT_PANEL**, see below) and a dialog opens:

- Current state of every group: both switches, what the light shows and why
- **Auto / On / Dim / Off** buttons per group
- A button for every effect used in that group, to try them out (plays for `show_result_for` seconds)
- **Schedule: ON/OFF** and **Print: ON/OFF** toggle buttons

Requires Mainsail v2.9 or newer (macro prompts). Other interfaces simply show the
text in the console.

### Macro buttons (Mainsail and Fluidd)
With `[include auto_light_macros.cfg]` you get these buttons in the Macros panel:

| Button | What it does |
|---|---|
| `AUTOLIGHT_PANEL` | Opens the control panel |
| `AUTOLIGHT_AUTO` | End manual values, back to automatic now |
| `AUTOLIGHT_ON` | On until `AUTOLIGHT_AUTO` or the next print (`VALUE=` optional: `warm@0.5`, `effect:rainbow`…; `DURATION=` seconds optional) |
| `AUTOLIGHT_OFF` | Off until `AUTOLIGHT_AUTO` or the next print |
| `AUTOLIGHT_ENABLE` / `AUTOLIGHT_DISABLE` | Turn the switches on/off (`PART=schedule` or `PART=print` optional) |

All accept an optional `LIGHT=<group>`.

### Colour pickers and sliders
Mainsail/Fluidd already show sliders for `[output_pin]` and colour pickers for
neopixels. Auto Light respects what you set there **until the next schedule or
print change**, then takes over again — or click `AUTOLIGHT_AUTO` to return immediately.
(Values set with `AUTO_LIGHT_SET` / `AUTOLIGHT_ON` last longer, see below.)

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
idle: purple@0.3
printing: blue
complete: green
error: red
show_result_for: 900

[auto_light nozzle]               # Nozzle LEDs: only on while printing
lights: sb_leds:2-3
idle: off
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
| `AUTO_LIGHT_RESUME [LIGHT=]` | End manual values and show the automatic value now. If there is nothing automatic to show, it says why (old name: `SET_AUTO_LIGHT`) |
| `AUTO_LIGHT_ENABLE [PART=] [LIGHT=]` | Turn a switch on: `PART=schedule`, `PART=print`, or both without `PART` (saved) |
| `AUTO_LIGHT_DISABLE [PART=] [LIGHT=]` | Turn a switch off, same `PART` options (saved) |
| `AUTO_LIGHT_SET VALUE= [LIGHT=] [DURATION=]` | Set a value, colour or effect by hand (e.g. `VALUE=warm@0.5`, `VALUE=effect:rainbow`), see below |
| `AUTO_LIGHT_MENU [LIGHT=]` | Open the control panel dialog (Mainsail) |
| `AUTO_LIGHT_LIST_SCHEDULES [LIGHT=]` | Show switches, current value, schedules and print values |
| `AUTO_LIGHT_SCHEDULE_ENABLE ID= [LIGHT=]` | Enable schedule ID (saved) |
| `AUTO_LIGHT_SCHEDULE_DISABLE ID= [LIGHT=]` | Disable schedule ID (saved) |

### How long does a manual value last?
One rule: a value set with `AUTO_LIGHT_SET` (or the **On / Dim / Off** buttons) stays until
`AUTO_LIGHT_RESUME`, or until a print starts while the Print switch is on.
Schedule changes don't end it. On top of that:

| Value | Without `DURATION` | With `DURATION=30` | With `DURATION=0` |
|---|---|---|---|
| Colour / brightness / `off` | Until resume or print start | 30 s, then automatic | Until resume or print start |
| `effect:name` | `show_result_for` seconds (default 300), then automatic | 30 s, then automatic | Until resume or print start |

The console always says when the value ends, e.g.
`AutoLight [default]: 40% for 30 s (until 21:14:05), then automatic`.
If both switches are off, a timed value goes back to what was shown before it.

### Examples
```gcode
AUTO_LIGHT_SCHEDULE_DISABLE ID=2            # Working late: skip the evening dim
AUTO_LIGHT_SET VALUE=FF8800@0.5 LIGHT=logo  # Preview a colour
AUTO_LIGHT_SET VALUE=effect:rainbow DURATION=10  # Try an effect for 10 s
AUTO_LIGHT_RESUME                           # Back to the automatic value
AUTO_LIGHT_DISABLE PART=schedule            # Lights only react to prints
AUTO_LIGHT_DISABLE LIGHT=nozzle             # Turn off automation for one group
```

---

## 🏠 Status for Mainsail, Fluidd and Home Assistant

Each group exposes its status through Moonraker as the printer object
`auto_light` (or `auto_light <name>`):

```
schedule_enabled, print_enabled, manual, manual_value, manual_remaining,
mode (schedule / idle / manual / printing / paused / complete / error / cancelled / restored),
effect, current_brightness, current_color, target_brightness, target_color,
active_schedule_id, active_schedule_name, current_time, lights, schedules[],
enabled (true if any switch is on, kept for older setups)
```
`manual_remaining` is the number of seconds left on a timed manual value, and `null`
when the value lasts until resume.

Use it in macros (`printer["auto_light logo"].mode`) or with the
[Moonraker Home Assistant integration](https://github.com/marcolivierarsenault/moonraker-home-assistant)
to show which mode the lights are in.

---

## 🧠 How It Works

### Two switches per group
Every group has two independent switches. Both start in the position of `enabled:`
(default on).

| Switch | Controls | When it is OFF |
|---|---|---|
| **Schedule** | `schedule_N` and `idle` (time of day) | the light no longer changes with the time |
| **Print** | `printing`, `paused`, `complete`, `error`, `cancelled` | the light ignores prints |

- While a print value applies (printing or paused, then `show_result_for` seconds
  after the print), it wins over the schedule.
- If the Schedule switch is off, the light goes back to **what it showed before the
  print** once the result has been shown.
- `off` / `0` is just a brightness. It never stops the automation: the next
  schedule turns the light back on.
- A group without print values has only the Schedule switch.

Change the switches with `AUTO_LIGHT_ENABLE/DISABLE PART=schedule|print` (without `PART`
both change), with the **AUTOLIGHT_ENABLE/DISABLE** macros, or with the toggle buttons in the panel.

**Saved across restarts.** The switch positions are saved in `state_file`. On startup, any
switch that is off is announced in the console, e.g.
`AutoLight [default]: schedule OFF (saved in auto_light_state.json) - AUTO_LIGHT_ENABLE LIGHT=default to turn on`.
A saved position wins over `enabled:` **until you change `enabled:` in the config**, and
then the config wins. A state saved by v2 (`AUTO_LIGHT_DISABLE`) is kept and announced the same way.

### What do I see, and why?
`AUTO_LIGHT_LIST_SCHEDULES` and the panel show it for each group, e.g.
`AutoLight [default]: schedule ON | print ON | now: 30% (Evening 19:00-23:00)`.

| Console shows | Why | To change it |
|---|---|---|
| `now: 30% (Evening 19:00-23:00)` | The Schedule switch picked a schedule | — |
| `now: off (idle)` | No schedule matches right now, so `idle:` applies | — |
| `now: 80% (printing)` / `(complete)` | The Print switch shows a print value | wait, or `AUTO_LIGHT_DISABLE PART=print` |
| `now: 40% (manual, 25 s left)` / `(manual, until AUTO_LIGHT_RESUME ...)` | You set a value by hand | `AUTO_LIGHT_RESUME` |
| `now: 30% (as before the print)` | Schedule is off and the print is done, so the earlier look is back | — |
| `now: 100% (automation off, left as is)` | Both switches are off | `AUTO_LIGHT_ENABLE` |
| `now: 100% (no rule active, left as is)` | Schedule is off and no print value applies | `AUTO_LIGHT_ENABLE PART=schedule` |
| `schedule OFF` right after startup | Saved switch position (possibly from v2) | `AUTO_LIGHT_ENABLE` |

### Under the hood
1. On startup Auto Light applies the right value immediately.
2. It then **sleeps until the next schedule boundary**, so changes happen on the
   exact minute, with a safety re-check every `check_interval` seconds
   (clock changes, NTP sync on boot).
3. If the Print switch is on it also reads Klipper's print state every 2 s
   (a simple in-memory lookup, no G-code involved).
4. Changes fade in small steps, and each step is sent as a single batched command.
   Effects are only started/stopped; led_effect does the animating.
5. Changes made outside Auto Light (`SET_PIN`, `SET_LED`, UI sliders) are kept until
   the next schedule or print change.

### Protection Against Errors
- Wrong light names, times or colours are reported as a clear config error on startup
- Gaps or overlaps between schedules are logged as a warning in `klippy.log`
- The last enabled schedule can't be disabled unless an `idle` value is set

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
| Light doesn't change when automation is off | Expected: `AUTO_LIGHT_DISABLE` leaves the light as it is. Without `LIGHT=` it turns off **all** groups |
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

**In both cases:** remove the `[auto_light]` section(s) and any `[include auto_light_macros.cfg]` from your `printer.cfg`, delete the leftover `auto_light_state.json` from your config folder if present, and restart Klipper.

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
- 🔀 Two independent switches per group, Schedule and Print: `AUTO_LIGHT_ENABLE/DISABLE PART=schedule|print`, toggle buttons in the panel
- 👀 Switch positions, the manual value and its time left are shown in `AUTO_LIGHT_LIST_SCHEDULES`, the panel and the Moonraker status (`schedule_enabled`, `print_enabled`, `manual`, `manual_remaining`)
- 📢 Switches that are off after a restart (also from a v2 state file) are announced in the console, and changing `enabled:` in the config now takes effect
- ✋ One rule for manual values: they last until `AUTO_LIGHT_RESUME` or a print starts (or for `DURATION`), and the console says when they end
- 🏷️ Renamed: `SET_AUTO_LIGHT` → `AUTO_LIGHT_RESUME`, `default:` → `idle:`, `finish_hold:` → `show_result_for:` (old names still work)
- 🐛 `AUTO_LIGHT_RESUME` no longer reports "check executed" when automation is off; it reports what it did, or why it could not
- 🌅 Smooth fades (`fade_time`)
- ✨ klipper-led_effect integration: `effect:<name>` values with crossfades
- 🖱️ `AUTO_LIGHT_MENU` control panel (Mainsail) and `auto_light_macros.cfg` buttons
- ⏲️ `AUTO_LIGHT_SET ... DURATION=`; effects started by hand stop on their own after `show_result_for`
- ⏱️ Changes happen exactly at schedule boundaries instead of every `check_interval`
- 💾 Disabled schedules are now saved across restarts too
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
