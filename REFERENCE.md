# Klipper Auto Light – Reference

Everything in detail. For a first setup, the [README](README.md) is enough.

- [All options](#all-options)
- [Light names](#light-names)
- [Values and colours](#values-and-colours)
- [How a value is chosen](#how-a-value-is-chosen)
- [Switches](#switches)
- [Manual values](#manual-values)
- [LED effects](#led-effects)
- [Multiple groups](#multiple-groups)
- [G-code commands](#g-code-commands)
- [Moonraker status](#moonraker-status)
- [Under the hood](#under-the-hood)

---

## All options
```ini
[auto_light]               # or [auto_light <name>] for more groups
lights: caselight          # One or more lights, comma separated (see below)
#color: white              # Base colour that plain brightness values use (LEDs only)
#fade_time: 1.0            # Seconds to fade between values (0 = instant)
#enabled: True             # False = start with Auto Light off for this group
#check_interval: 600       # Safety re-check in seconds (time changes, NTP sync)

# Time schedules: schedule_1 ... schedule_10
# Format: HH:MM-HH:MM=value [optional name]
schedule_1: 07:00-19:00=1.0 Day
schedule_2: 19:00-07:00=warm@0.2 Night

#idle: off                 # Used when no schedule matches (or instead of schedules)

# Print values (all optional, anything not set falls back to the schedule)
#printing: white           # While a print is running
#paused: orange@0.6        # While paused (defaults to the 'printing' value)
#complete: green@0.5       # After a successful print ...
#error: red                # ... after an error ...
#cancelled: off            # ... after a cancelled print ...
#show_result_for: 300      # ... for this many seconds (one value for all three)
```

At least one `schedule_N` or an `idle` value is required.
Older options: `pin:` (v1/v2) still works as `lights:`. `state_file:` (v2.1) is
accepted but no longer used.

## Light names
`lights:` takes the names of your existing Klipper sections, and Auto Light finds out
the type by itself:

| Your section | Write |
|---|---|
| `[output_pin caselight]` | `lights: caselight` |
| `[neopixel sb_leds]` | `lights: sb_leds` |
| Only LEDs 2 and 3 of that chain | `lights: sb_leds:2-3` |
| Only LED 1 | `lights: sb_leds:1` |
| Several at once | `lights: caselight, sb_leds:2-3, bed_strip` |

Supported: `[output_pin]` (PWM or on/off), `[neopixel]`, `[dotstar]`, `[led]`,
`[pca9533]`, `[pca9632]`. Non-PWM `[output_pin]`s (plain relays) are switched **on**
for any value above 0.

## Values and colours
Every schedule, `idle`, print value and the `AUTO_LIGHT_SET` command accept:

| Value | Meaning |
|---|---|
| `0.6` | Brightness 0.0–1.0 (of the base `color`, white by default) |
| `warm` | Named colour: `off`, `white`, `warm`, `red`, `green`, `blue`, `yellow`, `orange`, `purple`, `magenta`, `cyan` |
| `FF8800` | Hex colour `RRGGBB`, **without `#`** (Klipper treats `#` as a comment) |
| `FFFFFF80` | Hex `RRGGBBWW` for RGBW strips (white channel) |
| `warm@0.4` | Any colour at a given brightness |
| `effect:rainbow` | Run `[led_effect rainbow]` (see [LED effects](#led-effects)) |

On an `[output_pin]` a colour simply becomes its brightness (`green@0.5` → 50%).

## How a value is chosen
The first match wins:

1. A **manual value** (`AUTO_LIGHT_SET`), see [Manual values](#manual-values).
2. **Print values**, if the Print switch is on: `printing` / `paused` while the print
   runs, then `complete`, `error` or `cancelled` for `show_result_for` seconds.
3. **Schedules**, if the Schedule switch is on: the matching `schedule_N`. If none
   matches, `idle`. Without `idle`, the earliest schedule fills gaps.
4. Schedule switch off, a print just ended: **what was shown before the print**.
5. Nothing: the light is left as it is.

A print result that is already there when Auto Light starts watching (e.g. after
`AUTO_LIGHT_ENABLE`) is not shown again.

`off` / `0` is just a brightness. It never stops the automation.

## Switches
Each group has two switches, both set by `enabled:` (default on):

| Switch | Controls | When it is OFF |
|---|---|---|
| **Schedule** | `schedule_N` and `idle` (time of day) | the light no longer changes with the time |
| **Print** | `printing`, `paused`, `complete`, `error`, `cancelled` | the light ignores prints |

- `AUTO_LIGHT_DISABLE` / `AUTO_LIGHT_ENABLE` without `PART` change both.
- `PART=schedule` or `PART=print` changes only one. The panel has a toggle button for each.
- A group without print values has only the Schedule switch.
- **Nothing is saved.** Switches (and `AUTO_LIGHT_SCHEDULE_DISABLE`) last until the
  next restart. For a permanent change, edit the config.
- Turning a switch off leaves the light as it is.

## Manual values
A value set with `AUTO_LIGHT_SET` (or the **On / Dim / Off** buttons) stays until
`AUTO_LIGHT_RESUME`, or until a print starts while the Print switch is on.
Schedule changes don't end it.

| Value | Without `DURATION` | With `DURATION=30` | With `DURATION=0` |
|---|---|---|---|
| Colour / brightness / `off` | Until resume or print start | 30 s, then automatic | Until resume or print start |
| `effect:name` | `show_result_for` seconds, then automatic | 30 s, then automatic | Until resume or print start |

The console always says when the value ends, e.g.
`AutoLight [default]: 40% for 30 s (until 21:14:05), then automatic`.
If both switches are off, a timed value goes back to what was shown before it.

Changes made outside Auto Light (`SET_PIN`, `SET_LED`, the sliders and colour pickers
in Mainsail/Fluidd) are not tracked: they stay until the next schedule or print change.

## LED effects
Animations are **not** rendered by Auto Light. That's the job of
[klipper-led_effect](https://github.com/julianschill/klipper-led_effect).
Auto Light only decides *which* effect should run *when*, and sends a single
`SET_LED_EFFECT` command when that changes, so it adds no load of its own.

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
   idle: warm@0.2
   schedule_1: 23:00-07:00=off Night
   printing: effect:sb_printing
   complete: effect:sb_rainbow
   error: effect:sb_error
   show_result_for: 120
   fade_time: 1
   ```

How switching works:
- **Effect → effect:** crossfade (`REPLACE=1 FADETIME=fade_time`), and the old one is stopped.
- **Effect → colour:** the effect fades out, then Auto Light fades the colour in.
- **Colour → effect:** the effect takes over the LEDs it is defined for.
- A group may consist of effects only. Then `lights:` can be left out and `off` simply stops the effect.
- Unknown effect names are reported as a config error on startup.

> 💡 **Keep it light while printing:** animations are drawn by the Pi and sent to the
> MCU many times per second. Prefer a low `frame_rate` (10–15) and calm effects for
> `printing:`, and save the fancy ones for `complete:` or idle times.

## Multiple groups
Each `[auto_light name]` section is an independent group with its own lights,
schedules and print values. For example, on a Stealthburner:

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

## G-code commands
`LIGHT=<name>` is optional. Without it a command applies to **all** groups
(the schedule commands need it only when you have more than one group).

| Command | Description |
|---------|-------------|
| `AUTO_LIGHT_RESUME [LIGHT=]` | End manual values and show the automatic value now. If there is nothing automatic to show, it says why (v2 name: `SET_AUTO_LIGHT`) |
| `AUTO_LIGHT_ENABLE [PART=] [LIGHT=]` | Turn switches on until restart: `PART=schedule`, `PART=print`, or both without `PART` |
| `AUTO_LIGHT_DISABLE [PART=] [LIGHT=]` | Turn switches off until restart, same `PART` options |
| `AUTO_LIGHT_SET VALUE= [LIGHT=] [DURATION=]` | Set a value, colour or effect by hand (see [Manual values](#manual-values)) |
| `AUTO_LIGHT_MENU [LIGHT=]` | Open the control panel dialog (Mainsail v2.9+) |
| `AUTO_LIGHT_LIST_SCHEDULES [LIGHT=]` | Show switches, current value, schedules and print values |
| `AUTO_LIGHT_SCHEDULE_ENABLE ID= [LIGHT=]` | Enable schedule ID until restart |
| `AUTO_LIGHT_SCHEDULE_DISABLE ID= [LIGHT=]` | Disable schedule ID until restart |

```gcode
AUTO_LIGHT_SCHEDULE_DISABLE ID=2            # Working late: skip the evening dim
AUTO_LIGHT_SET VALUE=FF8800@0.5 LIGHT=logo  # Preview a colour
AUTO_LIGHT_SET VALUE=effect:rainbow DURATION=10  # Try an effect for 10 s
AUTO_LIGHT_RESUME                           # Back to the automatic value
AUTO_LIGHT_DISABLE PART=schedule            # Lights only react to prints
AUTO_LIGHT_DISABLE LIGHT=nozzle             # Turn off one group
```

## Moonraker status
Each group exposes its status through Moonraker as the printer object
`auto_light` (or `auto_light <name>`):

```
schedule_enabled, print_enabled, manual, manual_value, manual_remaining,
mode (schedule / idle / manual / printing / paused / complete / error / cancelled / restored),
effect, current_brightness, current_color, target_brightness, target_color,
active_schedule_id, active_schedule_name, current_time, lights, schedules[],
enabled (true if any switch is on)
```
`manual_remaining` is the number of seconds left on a timed manual value, and `null`
when the value lasts until resume.

Use it in macros (`printer["auto_light logo"].mode`) or with the
[Moonraker Home Assistant integration](https://github.com/marcolivierarsenault/moonraker-home-assistant).

## Under the hood
1. On startup Auto Light applies the right value immediately.
2. It then **sleeps until the next schedule boundary**, so changes happen on the
   exact minute, with a safety re-check every `check_interval` seconds
   (clock changes, NTP sync on boot).
3. If the Print switch is on it also reads Klipper's print state every 2 s
   (a simple in-memory lookup, no G-code involved).
4. Changes fade in small steps, and each step is sent as a single batched command.
   Effects are only started/stopped; led_effect does the animating.
5. Config mistakes (light names, times, colours, unknown effects, renamed options)
   are reported as a clear config error on startup. Gaps or overlaps between
   schedules are logged as a warning in `klippy.log`.

### Tests
`python -m unittest discover tests` runs a simulation of Klipper (no printer needed).
[`tests/printer/`](tests/printer/) has two harmless test prints (no heating, no
motion) and a checklist for trying a new version on a real printer.
