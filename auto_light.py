# Klipper Auto Light
#
# Time-schedule and print-aware control for case lights, LED strips and
# neopixels, with smooth fades, colours and optional led_effect animations.
#
# Design goals: never get in Klipper's way. The module does no work between
# events - it sleeps until the next schedule boundary, only polls the print
# state (a cheap dict lookup every few seconds) when print rules are
# configured, and sends each fade step as one batched G-code script.
# Animations are never rendered here: they are delegated to the
# klipper-led_effect extension, which Auto Light only starts and stops.
#
# Licensed under the MIT License.

import datetime
import json
import logging
import os

MAX_SCHEDULES = 10
FADE_STEP = 0.1        # seconds between fade steps (10 updates/s)
PRINT_POLL = 2.0       # seconds between print-state checks
LED_PREFIXES = ('neopixel', 'dotstar', 'led', 'pca9533', 'pca9632')
PRINT_STATES = ('printing', 'paused', 'complete', 'cancelled', 'error')

# name -> (red, green, blue, white), all 0.0 - 1.0
NAMED_COLORS = {
    'off': (0., 0., 0., 0.),
    'white': (1., 1., 1., 0.),
    'warm': (1., .6, .25, 0.),
    'red': (1., 0., 0., 0.),
    'green': (0., 1., 0., 0.),
    'blue': (0., 0., 1., 0.),
    'yellow': (1., 1., 0., 0.),
    'orange': (1., .4, 0., 0.),
    'purple': (.6, 0., 1., 0.),
    'magenta': (1., 0., 1., 0.),
    'cyan': (0., 1., 1., 0.),
}
_HEX = set('0123456789abcdef')
OFF = (0., 0., 0., 0.)


class EffectValue:
    """A value that runs a [led_effect NAME] instead of a static colour."""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return isinstance(other, EffectValue) and other.name == self.name

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(('effect', self.name))


def is_effect(value):
    return isinstance(value, EffectValue)


def level(value):
    """Brightness 0.0-1.0 of a colour value, None for effects / no value."""
    if value is None or is_effect(value):
        return None
    return max(value)


def parse_value(text, base_color=(1., 1., 1., 0.)):
    """Parse a light value into an (r, g, b, w) tuple.

    Accepted forms:
      0.6            brightness, applied to the section's base `color`
      warm           a named colour at full brightness
      FF8800         RRGGBB hex colour (no '#', Klipper treats it as comment)
      FF880080       RRGGBBWW hex colour (RGBW strips)
      warm@0.4       any colour scaled to a brightness
      effect:name    start [led_effect name] (klipper-led_effect)
    """
    text = text.strip()
    if text.lower().startswith('effect:'):
        name = text[7:].strip()
        if not name or ' ' in name:
            raise ValueError("invalid effect name '%s'" % name)
        return EffectValue(name)
    text = text.lower()
    brightness = None
    if '@' in text:
        text, b = text.split('@', 1)
        text = text.strip()
        brightness = float(b)
    if text in NAMED_COLORS:
        color = NAMED_COLORS[text]
    elif len(text) in (6, 8) and set(text) <= _HEX:
        color = tuple(int(text[i:i + 2], 16) / 255.
                      for i in range(0, len(text), 2))
        color = (color + (0.,))[:4]
    else:
        if brightness is not None:
            raise ValueError("unknown colour '%s'" % text)
        brightness = float(text)
        color = base_color
    if brightness is None:
        brightness = 1.
    if not 0. <= brightness <= 1.:
        raise ValueError("brightness must be between 0.0 and 1.0")
    return tuple(round(c * brightness, 4) for c in color)


def describe(color):
    """Short human description of a colour tuple."""
    if color is None:
        return "none"
    if is_effect(color):
        return "effect %s" % color.name
    level = max(color)
    if level <= 0.:
        return "off"
    r, g, b, w = color
    if abs(r - g) < 1e-3 and abs(g - b) < 1e-3 and w == 0.:
        return "%d%%" % round(level * 100)
    hexcol = "%02X%02X%02X" % tuple(int(round(c * 255)) for c in (r, g, b))
    if w:
        hexcol += "%02X" % int(round(w * 255))
    return "%s (%d%%)" % (hexcol, round(level * 100))


def _parse_hhmm(text):
    hour, minute = map(int, text.strip().split(':'))
    if not (0 <= hour <= 24 and 0 <= minute <= 59) or (
            hour == 24 and minute):
        raise ValueError("invalid time '%s'" % text)
    return (hour * 60 + minute) % 1440


def _fmt_min(minutes):
    return "%02d:%02d" % (minutes // 60, minutes % 60)


class LightTarget:
    """One physical light: an [output_pin] or an LED chain (or part of it)."""

    def __init__(self, spec, error):
        self.spec = spec.strip()
        name, _, idx = self.spec.partition(':')
        self.name = name.strip()
        if not self.name:
            raise error("AutoLight: empty light name in '%s'" % spec)
        self.indices = None
        if idx.strip():
            try:
                first, _, last = idx.partition('-')
                first = int(first)
                last = int(last) if last else first
                if first < 1 or last < first:
                    raise ValueError()
            except ValueError:
                raise error("AutoLight: invalid LED index in '%s' "
                            "(use name:3 or name:1-4)" % spec)
            self.indices = list(range(first, last + 1))
        self.kind = None
        self.is_pwm = True
        self.last_script = None
        self.current = None         # colour last sent to this light

    def resolve(self, printer, error):
        pin = printer.lookup_object('output_pin ' + self.name, None)
        if pin is not None:
            if self.indices:
                raise error("AutoLight: '%s' is an [output_pin]; LED indexes "
                            "only work with LED chains" % self.spec)
            self.kind = 'pin'
            self.is_pwm = getattr(pin, 'is_pwm', True)
            return
        for prefix in LED_PREFIXES:
            if printer.lookup_object('%s %s' % (prefix, self.name),
                                     None) is not None:
                self.kind = 'led'
                return
        raise error("AutoLight: light '%s' not found. Use the name of an "
                    "[output_pin], [neopixel], [dotstar], [led], [pca9533] "
                    "or [pca9632] section" % self.name)

    @property
    def can_fade(self):
        return self.kind == 'led' or self.is_pwm

    def script(self, color):
        if self.kind == 'pin':
            value = max(color)
            if not self.is_pwm:
                value = 1. if value > 0. else 0.
            return "SET_PIN PIN=%s VALUE=%.3f" % (self.name, value)
        base = ("SET_LED LED=%s RED=%.3f GREEN=%.3f BLUE=%.3f WHITE=%.3f "
                "SYNC=0" % ((self.name,) + tuple(color)))
        if not self.indices:
            return base
        last = self.indices[-1]
        return "\n".join("%s INDEX=%d TRANSMIT=%d" % (base, i, i == last)
                         for i in self.indices)


class Schedule:
    def __init__(self, sid, start, end, color, label):
        self.id = sid
        self.start = start
        self.end = end
        self.color = color
        self.name = label or "Schedule %d" % sid
        self.enabled = True

    def contains(self, minute):
        if self.start == self.end:
            return True                       # all day
        if self.start < self.end:
            return self.start <= minute < self.end
        return minute >= self.start or minute < self.end   # crosses midnight

    def span(self):
        return "%s-%s" % (_fmt_min(self.start), _fmt_min(self.end))


class AutoLightManager:
    """Owns the shared G-code commands and dispatches them by LIGHT=name."""

    def __init__(self, printer):
        self.lights = {}
        self.printer = printer
        self.gcode = gcode = printer.lookup_object('gcode')
        for cmd in ('SET_AUTO_LIGHT', 'AUTO_LIGHT_ENABLE', 'AUTO_LIGHT_DISABLE',
                    'AUTO_LIGHT_SET', 'AUTO_LIGHT_SCHEDULE_ENABLE',
                    'AUTO_LIGHT_SCHEDULE_DISABLE', 'AUTO_LIGHT_LIST_SCHEDULES',
                    'AUTO_LIGHT_MENU'):
            gcode.register_command(cmd, getattr(self, 'cmd_' + cmd),
                                   desc=getattr(self, 'cmd_%s_help' % cmd))

    def add(self, light):
        self.lights[light.light_name] = light

    def _select(self, gcmd, single=False):
        name = gcmd.get('LIGHT', None)
        if name is not None:
            light = self.lights.get(name)
            if light is None:
                raise gcmd.error("AutoLight: unknown LIGHT '%s' (configured: "
                                 "%s)" % (name, ", ".join(sorted(self.lights))))
            return [light]
        if single and len(self.lights) > 1:
            raise gcmd.error("AutoLight: several lights are configured, add "
                             "LIGHT=<name> (one of: %s)"
                             % ", ".join(sorted(self.lights)))
        return list(self.lights.values())

    cmd_SET_AUTO_LIGHT_help = "Re-apply the light value for the current time"

    def cmd_SET_AUTO_LIGHT(self, gcmd):
        for light in self._select(gcmd):
            light.request_update(force=True)
        gcmd.respond_info("AutoLight: check executed")

    cmd_AUTO_LIGHT_ENABLE_help = "Enable automatic light control"

    def cmd_AUTO_LIGHT_ENABLE(self, gcmd):
        for light in self._select(gcmd):
            light.set_enabled(True)
            gcmd.respond_info("AutoLight [%s]: ENABLED" % light.light_name)

    cmd_AUTO_LIGHT_DISABLE_help = "Disable automatic light control"

    def cmd_AUTO_LIGHT_DISABLE(self, gcmd):
        for light in self._select(gcmd):
            light.set_enabled(False)
            gcmd.respond_info("AutoLight [%s]: DISABLED" % light.light_name)

    cmd_AUTO_LIGHT_SET_help = ("Temporarily set a value (VALUE=warm@0.5 or "
                               "effect:name) [DURATION=seconds]")

    def cmd_AUTO_LIGHT_SET(self, gcmd):
        self._set_manual(gcmd)

    def _set_manual(self, gcmd):
        text = gcmd.get('VALUE')
        duration = gcmd.get_float('DURATION', None, minval=0.)
        for light in self._select(gcmd):
            value = light.parse_command_value(gcmd, text)
            seconds = light.set_manual(value, duration)
            if seconds:
                until = "for %d s" % round(seconds)
            else:
                until = ("until the next change (SET_AUTO_LIGHT LIGHT=%s "
                         "returns to automatic)" % light.light_name)
            gcmd.respond_info("AutoLight [%s]: %s %s"
                              % (light.light_name, describe(value), until))

    cmd_AUTO_LIGHT_SCHEDULE_ENABLE_help = "Enable a schedule (ID=n)"

    def cmd_AUTO_LIGHT_SCHEDULE_ENABLE(self, gcmd):
        light = self._select(gcmd, single=True)[0]
        light.set_schedule_enabled(gcmd, gcmd.get_int('ID', minval=1), True)

    cmd_AUTO_LIGHT_SCHEDULE_DISABLE_help = ("Disable a schedule (ID=n). At "
                                            "least one must remain enabled.")

    def cmd_AUTO_LIGHT_SCHEDULE_DISABLE(self, gcmd):
        light = self._select(gcmd, single=True)[0]
        light.set_schedule_enabled(gcmd, gcmd.get_int('ID', minval=1), False)

    cmd_AUTO_LIGHT_LIST_SCHEDULES_help = "Show lights, schedules and status"

    def cmd_AUTO_LIGHT_LIST_SCHEDULES(self, gcmd):
        for light in self._select(gcmd):
            gcmd.respond_info(light.report())

    # ----- Mainsail / Fluidd dialog ---------------------------------------

    cmd_AUTO_LIGHT_MENU_help = "Open the Auto Light control panel (Mainsail)"

    def cmd_AUTO_LIGHT_MENU(self, gcmd):
        action = gcmd.get('ACTION', 'show').lower()
        if action == 'close':
            self._prompt(["prompt_end"])
            return
        name = gcmd.get('LIGHT', None)
        lights = self._select(gcmd)
        if action == 'auto':
            for light in lights:
                light.resume_auto()
        elif action == 'set':
            self._set_manual(gcmd)
        elif action in ('enable', 'disable'):
            for light in lights:
                light.set_enabled(action == 'enable')
        elif action != 'show':
            raise gcmd.error("AutoLight: unknown ACTION '%s'" % action)
        if name is None and len(self.lights) > 1:
            self._show_overview()
        else:
            self._show_light(lights[0], back=len(self.lights) > 1)

    def _prompt(self, lines):
        for line in lines:
            self.gcode.respond_raw("// action:" + line)

    def _show_overview(self):
        lines = ["prompt_begin Auto Light"]
        for light in sorted(self.lights.values(), key=lambda l: l.light_name):
            lines.append("prompt_text %s: %s" % (light.light_name,
                                                 light.summary()))
        lines.append("prompt_button_group_start")
        for name in sorted(self.lights):
            lines.append("prompt_button %s|AUTO_LIGHT_MENU LIGHT=%s|info"
                         % (name, name))
        lines += ["prompt_button_group_end",
                  "prompt_button_group_start",
                  "prompt_button All auto|AUTO_LIGHT_MENU ACTION=auto|primary",
                  "prompt_button All off|AUTO_LIGHT_MENU ACTION=set "
                  "VALUE=off|secondary",
                  "prompt_button_group_end",
                  "prompt_footer_button Close|AUTO_LIGHT_MENU ACTION=close",
                  "prompt_show"]
        self._prompt(lines)

    def _show_light(self, light, back):
        cmd = "AUTO_LIGHT_MENU LIGHT=%s" % light.light_name
        lines = ["prompt_begin Auto Light: %s" % light.light_name,
                 "prompt_text %s" % light.summary(),
                 "prompt_button_group_start",
                 "prompt_button Auto|%s ACTION=auto|primary" % cmd]
        if light.targets:
            lines += ["prompt_button On|%s ACTION=set VALUE=1.0|secondary"
                      % cmd,
                      "prompt_button Dim|%s ACTION=set VALUE=0.3|secondary"
                      % cmd]
        lines += ["prompt_button Off|%s ACTION=set VALUE=off|secondary" % cmd,
                  "prompt_button_group_end"]
        effects = light.known_effects()
        if effects:
            lines.append("prompt_text Effects:")
            for i in range(0, len(effects), 3):
                lines.append("prompt_button_group_start")
                for eff in effects[i:i + 3]:
                    lines.append("prompt_button %s|%s ACTION=set "
                                 "VALUE=effect:%s|info" % (eff, cmd, eff))
                lines.append("prompt_button_group_end")
        if light.enabled:
            lines.append("prompt_footer_button Pause automation|%s "
                         "ACTION=disable|warning" % cmd)
        else:
            lines.append("prompt_footer_button Resume automation|%s "
                         "ACTION=enable|primary" % cmd)
        if back:
            lines.append("prompt_footer_button Back|AUTO_LIGHT_MENU")
        lines += ["prompt_footer_button Close|AUTO_LIGHT_MENU ACTION=close",
                  "prompt_show"]
        self._prompt(lines)


class AutoLight:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.section = config.get_name()
        parts = self.section.split(None, 1)
        self.light_name = parts[1] if len(parts) > 1 else 'default'

        # --- timing -------------------------------------------------------
        self.check_interval = config.getfloat('check_interval', 600.,
                                              minval=60.)
        self.fade_time = config.getfloat('fade_time', 1., minval=0.)
        self.finish_hold = config.getfloat('finish_hold', 300., minval=0.)
        self.enabled = config.getboolean('enabled', True)

        # --- values -------------------------------------------------------
        self.base_color = self._parse_opt(config, 'color', 'white',
                                          (1., 1., 1., 0.))
        if is_effect(self.base_color):
            raise config.error("AutoLight: 'color' must be a colour")
        self.default_value = self._parse_opt(config, 'default', None,
                                             base=self.base_color)
        self.print_values = {}
        for state in PRINT_STATES:
            value = self._parse_opt(config, state, None, base=self.base_color)
            if value is not None:
                self.print_values[state] = value
        self.print_aware = bool(self.print_values)

        self.schedules = []
        for i in range(1, MAX_SCHEDULES + 1):
            raw = config.get('schedule_%d' % i, None)
            if raw is None:
                continue
            try:
                body, _, label = raw.strip().partition(' ')
                times, value = body.split('=', 1)
                start, end = times.split('-')
                sched = Schedule(i, _parse_hhmm(start), _parse_hhmm(end),
                                 parse_value(value, self.base_color),
                                 label.strip())
            except Exception as e:
                raise config.error("AutoLight: invalid schedule_%d '%s' (%s). "
                                   "Format: HH:MM-HH:MM=value [name]"
                                   % (i, raw, e))
            self.schedules.append(sched)
        if not self.schedules and self.default_value is None:
            raise config.error("AutoLight: define at least one schedule_N "
                               "or a 'default' value")
        self.schedules.sort(key=lambda s: s.start)
        self._warn_coverage()

        # --- lights -------------------------------------------------------
        # A group that only uses effects (and 'off') needs no lights of its
        # own; otherwise fall back to the v1/v2 default pin name.
        lights = config.get('lights', None)
        pin = config.get('pin', None)            # v1/v2 option, still works
        spec = lights if lights is not None else pin
        if spec is None and any(not is_effect(v) and max(v) > 0.
                                for v in self._all_values()):
            spec = 'case_light'
        self.targets = [LightTarget(s, config.error)
                        for s in (spec or '').split(',') if s.strip()]

        state_file = config.get('state_file', None)
        self.state_file = os.path.expanduser(
            state_file or self._default_state_file())

        # --- runtime state ------------------------------------------------
        self.print_stats = None
        self.print_state = None
        self.print_state_since = 0.
        self.mode = None            # what the automation selected
        self.manual = None          # value set by hand, until next change
        self.manual_timer = None    # ends a timed manual value
        self.manual_until = None    # reactor time the manual value ends
        self.active_schedule = None
        self.target = None          # value the automation wants
        self.current = None         # last colour sent (None during effects)
        self.active_effect = None   # name of the effect we started
        self.force = False
        self.update_timer = None
        self.output_timer = None
        self.pending = []           # scripts to send before the next fade
        self.fade = None
        self.generation = 0
        self.sending = False

        manager = self.printer.lookup_object('auto_light_manager', None)
        if manager is None:
            manager = AutoLightManager(self.printer)
            self.printer.add_object('auto_light_manager', manager)
        if self.light_name in manager.lights:
            raise config.error("AutoLight: duplicate light name '%s'"
                               % self.light_name)
        manager.add(self)

        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:shutdown",
                                            self._handle_shutdown)

    # ===== setup ==========================================================

    @staticmethod
    def _parse_opt(config, option, default, fallback=None,
                   base=(1., 1., 1., 0.)):
        raw = config.get(option, default)
        if raw is None:
            return fallback
        try:
            return parse_value(raw, base)
        except ValueError as e:
            raise config.error("AutoLight: invalid %s '%s': %s"
                               % (option, raw, e))

    def _all_values(self):
        values = [s.color for s in self.schedules]
        values += list(self.print_values.values())
        if self.default_value is not None:
            values.append(self.default_value)
        return values

    def known_effects(self):
        names = []
        for value in self._all_values():
            if is_effect(value) and value.name not in names:
                names.append(value.name)
        return names

    def _warn_coverage(self):
        if not self.schedules:
            return
        cover = [0] * 1440
        for s in self.schedules:
            for m in range(1440):
                if s.contains(m):
                    cover[m] += 1
        gaps = cover.count(0)
        overlaps = sum(1 for c in cover if c > 1)
        if gaps:
            fallback = ("'default'" if self.default_value is not None
                        else "the earliest schedule")
            logging.warning("AutoLight [%s]: schedules leave %d minute(s) of "
                            "the day uncovered; %s is used there",
                            self.light_name, gaps, fallback)
        if overlaps:
            logging.warning("AutoLight [%s]: schedules overlap for %d "
                            "minute(s); the one starting earliest wins",
                            self.light_name, overlaps)

    def _default_state_file(self):
        try:
            config_file = self.printer.get_start_args().get('config_file')
            if config_file:
                return os.path.join(os.path.dirname(config_file),
                                    'auto_light_state.json')
        except Exception:
            pass
        return os.path.expanduser('~/auto_light_state.json')

    def _effect_exists(self, name):
        return self.printer.lookup_object('led_effect ' + name,
                                          None) is not None

    def _handle_connect(self):
        # Errors raised here are reported to the user as config errors
        error = self.printer.config_error
        for target in self.targets:
            target.resolve(self.printer, error)
        for name in self.known_effects():
            if not self._effect_exists(name):
                raise error("AutoLight [%s]: effect '%s' not found. Define "
                            "[led_effect %s] (requires klipper-led_effect)"
                            % (self.light_name, name, name))
        if self.print_aware:
            self.print_stats = self.printer.lookup_object('print_stats', None)

    def _handle_ready(self):
        self._load_state()
        self.update_timer = self.reactor.register_timer(self._update_cb)
        self.output_timer = self.reactor.register_timer(self._output_cb)
        self.manual_timer = self.reactor.register_timer(self._manual_end_cb)
        if self.enabled:
            self.request_update(force=True)

    def _handle_shutdown(self):
        self.enabled = False
        self.fade = None
        self.pending = []

    # ===== persistence ====================================================

    def _read_state_file(self):
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
        except (IOError, OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        if isinstance(data.get('enabled'), bool):   # v2.1 single-light format
            data = {'auto_light': {'enabled': data['enabled']}}
        return data

    def _load_state(self):
        state = self._read_state_file().get(self.section)
        if not isinstance(state, dict):
            return
        if 'enabled' in state:
            self.enabled = bool(state['enabled'])
        off = set(state.get('disabled_schedules', []))
        for s in self.schedules:
            s.enabled = s.id not in off
        self._ensure_one_schedule()
        logging.info("AutoLight [%s]: restored state enabled=%s, disabled "
                     "schedules=%s", self.light_name, self.enabled, sorted(off))

    def _save_state(self):
        data = self._read_state_file()
        data[self.section] = {
            'enabled': self.enabled,
            'disabled_schedules': [s.id for s in self.schedules
                                   if not s.enabled],
        }
        tmp_file = self.state_file + '.tmp'
        try:
            with open(tmp_file, 'w') as f:
                json.dump(data, f, indent=1)
            os.replace(tmp_file, self.state_file)
        except Exception as e:
            logging.error("AutoLight: could not save state to %s: %s",
                          self.state_file, e)

    def _ensure_one_schedule(self):
        if (self.schedules and self.default_value is None
                and not any(s.enabled for s in self.schedules)):
            self.schedules[0].enabled = True

    # ===== decision logic =================================================

    def _find_schedule(self, minute):
        for s in self.schedules:
            if s.enabled and s.contains(minute):
                return s
        return None

    def _desired(self, eventtime, now):
        """Return (value, mode, schedule) the lights should show now."""
        if self.print_stats is not None:
            state = self.print_stats.get_status(eventtime).get('state')
            if state != self.print_state:
                self.print_state = state
                self.print_state_since = eventtime
            value = self.print_values.get(state)
            if value is None and state == 'paused':
                value = self.print_values.get('printing')
            if value is not None and (
                    state in ('printing', 'paused')
                    or eventtime - self.print_state_since < self.finish_hold):
                return value, state, None
        sched = self._find_schedule(now.hour * 60 + now.minute)
        if sched is not None:
            return sched.color, 'schedule', sched
        if self.default_value is not None:
            return self.default_value, 'default', None
        enabled = [s for s in self.schedules if s.enabled]
        if enabled:
            return enabled[0].color, 'schedule', enabled[0]
        return None, 'none', None

    def _seconds_to_boundary(self, now):
        sod = (now.hour * 3600 + now.minute * 60 + now.second
               + now.microsecond / 1e6)
        best = 86400.
        for s in self.schedules:
            for minute in (s.start, s.end):
                delta = (minute * 60 - sod) % 86400
                if delta > 0.5:
                    best = min(best, delta)
        return best + 0.5

    def _update_cb(self, eventtime):
        if not self.enabled:
            return self.reactor.NEVER
        now = datetime.datetime.now()
        try:
            value, mode, sched = self._desired(eventtime, now)
            changed = value != self.target or mode != self.mode
            self.mode = mode
            self.active_schedule = sched
            if value is not None and (changed or self.force):
                self.target = value
                self._clear_manual()
                self.apply(value)
                if changed:
                    label = sched.name if sched is not None else mode
                    self.gcode.respond_info("AutoLight [%s]: %s -> %s"
                                            % (self.light_name, label,
                                               describe(value)))
            self.force = False
        except Exception:
            logging.exception("AutoLight [%s]: update failed",
                              self.light_name)
        wait = min(self.check_interval, self._seconds_to_boundary(now))
        if self.print_stats is not None:
            wait = min(wait, PRINT_POLL)
        return eventtime + wait

    # ===== output =========================================================
    #
    # All G-code is sent from the output timer, never from inside a G-code
    # command, so commands can safely request changes at any time.

    def apply(self, value):
        """Show a colour (with fade) or start an effect."""
        self.generation += 1
        fade = self.fade_time
        if is_effect(value):
            self.fade = None
            if value.name != self.active_effect:
                self.pending.append("SET_LED_EFFECT EFFECT=%s REPLACE=1 "
                                    "FADETIME=%.2f" % (value.name, fade))
                if self.active_effect:
                    self.pending.append("SET_LED_EFFECT EFFECT=%s STOP=1 "
                                        "FADETIME=%.2f"
                                        % (self.active_effect, fade))
                self.active_effect = value.name
                self.current = None
                for target in self.targets:
                    if target.kind == 'led':
                        target.current = None   # the effect owns these now
                        target.last_script = None
        else:
            start_at = 0.
            if self.active_effect:
                self.pending.append("SET_LED_EFFECT EFFECT=%s STOP=1 "
                                    "FADETIME=%.2f" % (self.active_effect, fade))
                self.active_effect = None
                # led_effect fades out and finally writes black, so only
                # start our own colour once it is done.
                start_at = self.reactor.monotonic() + fade + 0.3
                for target in self.targets:
                    if target.kind == 'led':
                        target.current = OFF
                        target.last_script = None
            if self.targets:
                steps = 1
                if self.fade_time > 0. and all(
                        t.current is not None for t in self.targets) and any(
                        t.can_fade for t in self.targets):
                    steps = max(1, int(round(self.fade_time / FADE_STEP)))
                self.fade = {
                    'from': [t.current or value for t in self.targets],
                    'to': value, 'steps': steps, 'step': 0,
                    'start_at': start_at,
                }
            else:
                self.fade = None
                self.current = value
        self._kick_output()

    def _kick_output(self):
        # A callback that is busy sending notices the new generation by
        # itself; re-arming the timer then could run it twice at once.
        if self.output_timer is not None and not self.sending:
            self.reactor.update_timer(self.output_timer, self.reactor.NOW)

    def _output_cb(self, eventtime):
        generation = self.generation
        if self.pending:
            scripts, self.pending = self.pending, []
            self._run(scripts)
            if self.generation != generation:
                return self.reactor.NOW
        fade = self.fade
        if fade is None:
            return self.reactor.NEVER
        if eventtime < fade['start_at']:
            return fade['start_at']
        fade['step'] += 1
        t = float(fade['step']) / fade['steps']
        scripts = []
        for target, start in zip(self.targets, fade['from']):
            color = tuple(a + (b - a) * t for a, b in zip(start, fade['to']))
            target.current = color
            script = target.script(color)
            if script != target.last_script:
                scripts.append(script)
                target.last_script = script
        self.current = tuple(self.targets[0].current)
        self._run(scripts)
        if self.generation != generation:
            return self.reactor.NOW
        if fade['step'] >= fade['steps']:
            self.fade = None
            return self.reactor.NEVER
        return eventtime + FADE_STEP

    def _run(self, scripts):
        if not scripts:
            return
        self.sending = True
        try:
            self.gcode.run_script("\n".join(scripts))
        except Exception as e:
            for target in self.targets:
                target.last_script = None
            logging.warning("AutoLight [%s]: could not set lights: %s",
                            self.light_name, e)
        finally:
            self.sending = False

    # ===== command helpers ================================================

    def parse_command_value(self, gcmd, text):
        try:
            value = parse_value(text, self.base_color)
        except ValueError as e:
            raise gcmd.error("AutoLight: invalid VALUE '%s': %s" % (text, e))
        if is_effect(value) and not self._effect_exists(value.name):
            raise gcmd.error("AutoLight: effect '%s' not found" % value.name)
        if not is_effect(value) and max(value) > 0. and not self.targets:
            raise gcmd.error("AutoLight [%s]: this group has no 'lights', "
                             "only effects or off" % self.light_name)
        return value

    def set_manual(self, value, duration=None):
        """Show a value by hand. Effects end on their own after
        `finish_hold` seconds unless DURATION is given (0 = until the next
        automatic change); colours last until the next change by default.
        Returns the duration in seconds (0 = until the next change)."""
        if duration is None:
            duration = self.finish_hold if is_effect(value) else 0.
        self.manual = value
        self.apply(value)
        self.manual_until = None
        if self.manual_timer is not None:
            waketime = self.reactor.NEVER
            if duration > 0.:
                waketime = self.manual_until = (self.reactor.monotonic()
                                                + duration)
            self.reactor.update_timer(self.manual_timer, waketime)
        return duration

    def _clear_manual(self):
        self.manual = None
        self.manual_until = None
        if self.manual_timer is not None:
            self.reactor.update_timer(self.manual_timer, self.reactor.NEVER)

    def _manual_end_cb(self, eventtime):
        if self.manual is not None:
            self.manual = None
            self.manual_until = None
            if self.enabled:
                self.request_update(force=True)
            elif self.active_effect:
                self.apply(OFF)          # paused: just stop the effect
        return self.reactor.NEVER

    def resume_auto(self):
        if not self.enabled:
            self.set_enabled(True)
        else:
            self.request_update(force=True)

    def request_update(self, force=False):
        if force:
            self.force = True
        if self.update_timer is not None and self.enabled:
            self.reactor.update_timer(self.update_timer, self.reactor.NOW)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.mode = None
            if self.update_timer is not None:
                self.reactor.update_timer(self.update_timer,
                                          self.reactor.NEVER)
        self._save_state()
        if enabled:
            self.request_update(force=True)

    def set_schedule_enabled(self, gcmd, sid, enabled):
        sched = next((s for s in self.schedules if s.id == sid), None)
        if sched is None:
            raise gcmd.error("AutoLight [%s]: schedule %d is not configured"
                             % (self.light_name, sid))
        if sched.enabled == enabled:
            gcmd.respond_info("AutoLight [%s]: %s is already %s"
                              % (self.light_name, sched.name,
                                 "enabled" if enabled else "disabled"))
            return
        if (not enabled and self.default_value is None
                and sum(s.enabled for s in self.schedules) <= 1):
            raise gcmd.error("AutoLight: cannot disable the last enabled "
                             "schedule (or set a 'default' value)")
        sched.enabled = enabled
        self._save_state()
        gcmd.respond_info("AutoLight [%s]: %s %s"
                          % (self.light_name,
                             "enabled" if enabled else "disabled", sched.name))
        self.request_update()

    def _shown(self):
        if self.active_effect:
            return EffectValue(self.active_effect)
        if self.fade is not None:
            return self.fade['to']
        return self.current

    def summary(self):
        if not self.enabled:
            state = "automation paused"
        elif self.manual is not None:
            if self.manual_until is not None:
                left = max(0., self.manual_until - self.reactor.monotonic())
                state = "manual, %d s left" % round(left)
            else:
                state = "manual until next change"
        elif self.active_schedule is not None:
            state = "%s (%s)" % (self.active_schedule.name,
                                 self.active_schedule.span())
        else:
            state = self.mode or "-"
        return "%s, %s" % (describe(self._shown()), state)

    def report(self):
        lines = ["AutoLight [%s]: %s, mode: %s, now: %s"
                 % (self.light_name,
                    "ENABLED" if self.enabled else "DISABLED",
                    "manual" if self.manual is not None else self.mode or "-",
                    describe(self._shown())),
                 "  lights: " + (", ".join(t.spec for t in self.targets)
                                 or "(effects only)")]
        for s in self.schedules:
            lines.append("  %d. %s [%s]: %s = %s"
                         % (s.id, s.name, "ENABLED" if s.enabled
                            else "DISABLED", s.span(), describe(s.color)))
        if self.default_value is not None:
            lines.append("  default: %s" % describe(self.default_value))
        for state in PRINT_STATES:
            if state in self.print_values:
                lines.append("  %s: %s" % (state,
                                           describe(self.print_values[state])))
        return "\n".join(lines)

    # ===== Moonraker / UI status ==========================================

    def get_status(self, eventtime):
        now = datetime.datetime.now()
        sched = self.active_schedule
        current = None if self.active_effect else self.current
        target = None if is_effect(self.target) else self.target
        return {
            'enabled': self.enabled,
            'light': self.light_name,
            'mode': 'manual' if self.manual is not None else self.mode,
            'effect': self.active_effect,
            'current_brightness': level(current),
            'current_color': list(current) if current else None,
            'target_brightness': level(target),
            'target_color': list(target) if target else None,
            'active_schedule_id': sched.id if sched else None,
            'active_schedule_name': sched.name if sched else None,
            'current_time': "%02d:%02d" % (now.hour, now.minute),
            'lights': [t.spec for t in self.targets],
            'schedules': [{
                'id': s.id,
                'name': s.name,
                'start': _fmt_min(s.start),
                'end': _fmt_min(s.end),
                'brightness': level(s.color),
                'color': None if is_effect(s.color) else list(s.color),
                'effect': s.color.name if is_effect(s.color) else None,
                'enabled': s.enabled,
            } for s in self.schedules],
        }


def load_config(config):
    return AutoLight(config)


def load_config_prefix(config):
    return AutoLight(config)
