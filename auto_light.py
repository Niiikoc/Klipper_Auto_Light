# Klipper Auto Light
#
# Time-schedule and print-aware control for case lights, LED strips and
# neopixels, with smooth fades, colours and optional led_effect animations.
#
# How it decides (AutoLight.decide), first match wins:
#
#   1. a manual value (AUTO_LIGHT_SET)        until RESUME / print start /
#                                             DURATION
#   2. Print switch:  printing / paused, then complete / error / cancelled
#                     for `show_result_for` seconds
#   3. Schedule switch:  the matching schedule_N, else `idle`
#   4. Schedule switch off: after a print, what was shown before it
#   5. nothing: the light is left as it is
#
# The two switches start as `enabled:` says and can be flipped with
# AUTO_LIGHT_ENABLE/DISABLE until the next restart. Nothing is saved: the
# config is always the truth.
#
# Design goals: never get in Klipper's way. The module does no work between
# events - it sleeps until the next schedule boundary, only polls the print
# state (a cheap dict lookup every few seconds) when the Print switch is on,
# and sends each fade step as one batched G-code script. Animations are
# never rendered here: they are delegated to the klipper-led_effect
# extension, which Auto Light only starts and stops.
#
# Licensed under the MIT License.

import collections
import datetime
import logging

MAX_SCHEDULES = 10
FADE_STEP = 0.1        # seconds between fade steps (10 updates/s)
PRINT_POLL = 2.0       # seconds between print-state checks
LED_PREFIXES = ('neopixel', 'dotstar', 'led', 'pca9533', 'pca9632')
PRINT_STATES = ('printing', 'paused', 'complete', 'cancelled', 'error')
RESULT_STATES = ('complete', 'cancelled', 'error')
# Options renamed before v3 was released: a clear error beats a silent alias
RENAMED = {'default': 'idle', 'finish_hold': 'show_result_for'}

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


class LightOutput:
    """Sends values to the lights of one group: fades colours, starts and
    stops led_effect animations.

    All G-code goes out from this class's own timer, never from inside a
    G-code command, so commands may call show() at any time."""

    def __init__(self, printer, name, targets, fade_time):
        self.reactor = printer.get_reactor()
        self.gcode = printer.lookup_object('gcode')
        self.name = name
        self.targets = targets
        self.fade_time = fade_time
        self.current = None         # last colour sent (None during effects)
        self.active_effect = None   # name of the effect we started
        self.pending = []           # scripts to send before the next fade
        self.fade = None
        self.generation = 0         # bumped by every show()
        self.sending = False
        self.timer = None

    def start(self):
        self.timer = self.reactor.register_timer(self._output_cb)

    def stop(self):
        self.fade = None
        self.pending = []

    def shown(self):
        """The value the lights show (or are fading to), None = unknown."""
        if self.active_effect:
            return EffectValue(self.active_effect)
        if self.fade is not None:
            return self.fade['to']
        return self.current

    def show(self, value):
        """Show a colour (with fade) or start an effect."""
        self.generation += 1
        if is_effect(value):
            self._start_effect(value.name)
        else:
            self._fade_to(value)
        if self.timer is not None and not self.sending:
            # A callback busy sending notices the new generation by itself;
            # re-arming the timer then could run it twice at once.
            self.reactor.update_timer(self.timer, self.reactor.NOW)

    def _effect_cmd(self, name, action):
        return "SET_LED_EFFECT EFFECT=%s %s=1 FADETIME=%.2f" % (
            name, action, self.fade_time)

    def _start_effect(self, name):
        self.fade = None
        if name == self.active_effect:
            return
        self.pending.append(self._effect_cmd(name, 'REPLACE'))
        if self.active_effect:
            self.pending.append(self._effect_cmd(self.active_effect, 'STOP'))
        self.active_effect = name
        self.current = None
        for target in self.targets:
            if target.kind == 'led':
                target.current = None       # the effect owns these now
                target.last_script = None

    def _fade_to(self, color):
        start_at = 0.
        if self.active_effect:
            self.pending.append(self._effect_cmd(self.active_effect, 'STOP'))
            self.active_effect = None
            # led_effect fades out and finally writes black, so only start
            # our own colour once it is done.
            start_at = self.reactor.monotonic() + self.fade_time + 0.3
            for target in self.targets:
                if target.kind == 'led':
                    target.current = OFF
                    target.last_script = None
        if not self.targets:                # effects-only group
            self.fade = None
            self.current = color
            return
        steps = 1
        if self.fade_time > 0. and all(
                t.current is not None for t in self.targets) and any(
                t.can_fade for t in self.targets):
            steps = max(1, int(round(self.fade_time / FADE_STEP)))
        self.fade = {'from': [t.current or color for t in self.targets],
                     'to': color, 'steps': steps, 'step': 0,
                     'start_at': start_at}

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
        last = fade['step'] >= fade['steps']
        t = float(fade['step']) / fade['steps']
        scripts = []
        for target, start in zip(self.targets, fade['from']):
            if last:
                color = fade['to']          # exact, no rounding drift
            else:
                color = tuple(a + (b - a) * t
                              for a, b in zip(start, fade['to']))
            target.current = color
            script = target.script(color)
            if script != target.last_script:
                scripts.append(script)
                target.last_script = script
        self.current = tuple(self.targets[0].current)
        self._run(scripts)
        if self.generation != generation:
            return self.reactor.NOW
        if last:
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
                            self.name, e)
        finally:
            self.sending = False


# What the automation wants: value None = nothing, leave the light alone.
# mode: schedule, idle, a print state, 'restored' or None.
Decision = collections.namedtuple('Decision', 'value mode schedule')
NOTHING = Decision(None, None, None)


class AutoLight:
    """One [auto_light] / [auto_light name] group. See the top of the file
    for how it decides what to show."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.section = config.get_name()
        parts = self.section.split(None, 1)
        self.light_name = parts[1] if len(parts) > 1 else 'default'

        for old, new in RENAMED.items():
            if config.get(old, None) is not None:
                raise config.error("AutoLight: option '%s' is now called "
                                   "'%s', please rename it in [%s]"
                                   % (old, new, self.section))
        if config.get('state_file', None) is not None:     # v2.1 option
            logging.info("AutoLight: 'state_file' is no longer used, the "
                         "config is always the truth")

        # --- options ------------------------------------------------------
        self.check_interval = config.getfloat('check_interval', 600.,
                                              minval=60.)
        fade_time = config.getfloat('fade_time', 1., minval=0.)
        self.show_result_for = config.getfloat('show_result_for', 300.,
                                               minval=0.)
        enabled = config.getboolean('enabled', True)

        self.base_color = NAMED_COLORS['white']  # until 'color' is read
        self.base_color = self._parse_opt(config, 'color', 'white')
        if is_effect(self.base_color):
            raise config.error("AutoLight: 'color' must be a colour")
        self.idle_value = self._parse_opt(config, 'idle')
        self.print_values = {}
        for state in PRINT_STATES:
            value = self._parse_opt(config, state)
            if value is not None:
                self.print_values[state] = value
        self.schedules = self._parse_schedules(config)
        if not self.schedules and self.idle_value is None:
            raise config.error("AutoLight: define at least one schedule_N "
                               "or an 'idle' value")
        self._warn_coverage()

        # The switches this group has: Print only with print values.
        self.switches = {'schedule': enabled}
        if self.print_values:
            self.switches['print'] = enabled

        # --- lights -------------------------------------------------------
        # A group that only uses effects (and 'off') needs no lights of its
        # own; otherwise fall back to the v1/v2 default pin name.
        spec = config.get('lights', None)
        if spec is None:
            spec = config.get('pin', None)       # v1/v2 option, still works
        if spec is None and any(not is_effect(v) and max(v) > 0.
                                for v in self._all_values()):
            spec = 'case_light'
        targets = [LightTarget(s, config.error)
                   for s in (spec or '').split(',') if s.strip()]
        self.output = LightOutput(self.printer, self.light_name, targets,
                                  fade_time)

        # --- runtime state ------------------------------------------------
        self.decision = NOTHING     # what the automation chose last
        self.manual = None          # value set by hand (AUTO_LIGHT_SET)
        self.manual_until = None    # reactor time it ends, None = open
        self.before_manual = None   # shown before the manual value
        self.before_print = None    # shown before the print took over
        self.print_stats = None
        self.print_state = None     # last print state seen
        self.print_state_since = 0.
        self.force = False          # re-send even if nothing changed
        self.shutdown = False
        self.update_timer = None
        self.manual_timer = None

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

    def _parse_opt(self, config, option, default=None):
        raw = config.get(option, default)
        if raw is None:
            return None
        try:
            return parse_value(raw, self.base_color)
        except ValueError as e:
            raise config.error("AutoLight: invalid %s '%s': %s"
                               % (option, raw, e))

    def _parse_schedules(self, config):
        schedules = []
        for i in range(1, MAX_SCHEDULES + 1):
            raw = config.get('schedule_%d' % i, None)
            if raw is None:
                continue
            try:
                body, _, label = raw.strip().partition(' ')
                times, value = body.split('=', 1)
                start, end = times.split('-')
                schedules.append(Schedule(
                    i, _parse_hhmm(start), _parse_hhmm(end),
                    parse_value(value, self.base_color), label.strip()))
            except Exception as e:
                raise config.error("AutoLight: invalid schedule_%d '%s' (%s). "
                                   "Format: HH:MM-HH:MM=value [name]"
                                   % (i, raw, e))
        schedules.sort(key=lambda s: s.start)
        return schedules

    def _all_values(self):
        values = [s.color for s in self.schedules]
        values += list(self.print_values.values())
        if self.idle_value is not None:
            values.append(self.idle_value)
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
            fallback = ("'idle'" if self.idle_value is not None
                        else "the earliest schedule")
            logging.warning("AutoLight [%s]: schedules leave %d minute(s) of "
                            "the day uncovered; %s is used there",
                            self.light_name, gaps, fallback)
        if overlaps:
            logging.warning("AutoLight [%s]: schedules overlap for %d "
                            "minute(s); the one starting earliest wins",
                            self.light_name, overlaps)

    def _effect_exists(self, name):
        return self.printer.lookup_object('led_effect ' + name,
                                          None) is not None

    def _handle_connect(self):
        # Errors raised here are reported to the user as config errors
        error = self.printer.config_error
        for target in self.output.targets:
            target.resolve(self.printer, error)
        for name in self.known_effects():
            if not self._effect_exists(name):
                raise error("AutoLight [%s]: effect '%s' not found. Define "
                            "[led_effect %s] (requires klipper-led_effect)"
                            % (self.light_name, name, name))
        if self.print_values:
            self.print_stats = self.printer.lookup_object('print_stats', None)

    def _handle_ready(self):
        self.output.start()
        self.update_timer = self.reactor.register_timer(self._update_cb)
        self.manual_timer = self.reactor.register_timer(self._manual_end_cb)
        self.force = True
        self._wake()

    def _handle_shutdown(self):
        self.shutdown = True
        self.output.stop()

    # ===== switches =======================================================

    def is_on(self, part):
        return self.switches.get(part, False)

    def automation_on(self):
        return any(self.switches.values())

    def _wake(self):
        """Run the update timer now, or park it if there is nothing to do."""
        if self.update_timer is None:
            return
        waketime = self.reactor.NEVER
        if self.automation_on() and not self.shutdown:
            waketime = self.reactor.NOW
        self.reactor.update_timer(self.update_timer, waketime)

    def switch(self, part, on):
        """AUTO_LIGHT_ENABLE/DISABLE: part is schedule, print or all,
        on=None toggles. Lasts until restart. Returns the console message."""
        if part != 'all' and part not in self.switches:
            return ("AutoLight [%s]: has no print values (printing:, "
                    "complete: ...), so there is no Print switch"
                    % self.light_name)
        parts = list(self.switches) if part == 'all' else [part]
        if on is None:
            on = not any(self.switches[p] for p in parts)
        for p in parts:
            self.switches[p] = on
        if not self.is_on('print'):
            self.print_state = None
        if not self.shutdown:
            self._update(self.reactor.monotonic(), force=on)
        self._wake()
        msg = "AutoLight [%s]: %s" % (self.light_name, self.status_line())
        if on and self.manual is not None:
            msg += ("\n  the manual value stays until AUTO_LIGHT_RESUME "
                    "LIGHT=%s" % self.light_name)
        return msg

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
        if (not enabled and self.idle_value is None
                and sum(s.enabled for s in self.schedules) <= 1):
            raise gcmd.error("AutoLight: cannot disable the last enabled "
                             "schedule (or set an 'idle' value)")
        sched.enabled = enabled
        gcmd.respond_info("AutoLight [%s]: %s %s (until restart)"
                          % (self.light_name,
                             "enabled" if enabled else "disabled", sched.name))
        self._wake()

    # ===== deciding =======================================================

    def _watch_print(self, eventtime):
        """Track the print state. Returns it, or None if Print is off."""
        if not self.is_on('print') or self.print_stats is None:
            return None
        state = self.print_stats.get_status(eventtime).get('state')
        prev = self.print_state
        if state != prev:
            self.print_state = state
            # A result that was already there when we started watching is
            # old news: don't show it.
            self.print_state_since = eventtime if prev is not None else -1e9
            if (state == 'printing' and prev not in ('printing', 'paused')
                    and self.manual is not None):
                self._clear_manual()
                self.gcode.respond_info("AutoLight [%s]: print started, "
                                        "manual value ended" % self.light_name)
        return state

    def decide(self, eventtime, now):
        """What the switches ask for right now (manual values aside)."""
        state = self._watch_print(eventtime)
        value = self.print_values.get(state)
        if value is None and state == 'paused':
            value = self.print_values.get('printing')
        if value is not None and (
                state in ('printing', 'paused')
                or eventtime - self.print_state_since < self.show_result_for):
            return Decision(value, state, None)
        if self.is_on('schedule'):
            minute = now.hour * 60 + now.minute
            enabled = [s for s in self.schedules if s.enabled]
            for s in enabled:
                if s.contains(minute):
                    return Decision(s.color, 'schedule', s)
            if self.idle_value is not None:
                return Decision(self.idle_value, 'idle', None)
            if enabled:                       # a gap and no idle value
                return Decision(enabled[0].color, 'schedule', enabled[0])
        elif self.before_print is not None:
            return Decision(self.before_print, 'restored', None)
        return NOTHING

    def _update(self, eventtime, force=False, announce=True, now=None):
        """decide() and show the result, unless a manual value is active.
        Returns the automatic value (None = nothing to show)."""
        new = self.decide(eventtime, now or datetime.datetime.now())
        old = self.decision
        # Remember what was there before a print, to go back to it when the
        # Schedule switch is off.
        if new.mode in PRINT_STATES and old.mode not in PRINT_STATES:
            shown = self.output.shown()
            self.before_print = OFF if shown is None else shown
        elif new.mode in ('schedule', 'idle'):
            self.before_print = None
        changed = new.value != old.value or new.mode != old.mode
        self.decision = new
        if new.value is None or self.manual is not None:
            return new.value
        if changed or force:
            self.output.show(new.value)
            if new.mode == 'restored':
                self.before_print = None
            if changed and announce:
                self.gcode.respond_info("AutoLight [%s]: %s -> %s"
                                        % (self.light_name, self._label(),
                                           describe(new.value)))
        return new.value

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
        if self.shutdown or not self.automation_on():
            return self.reactor.NEVER
        now = datetime.datetime.now()
        try:
            self._update(eventtime, force=self.force, now=now)
            self.force = False
        except Exception:
            logging.exception("AutoLight [%s]: update failed",
                              self.light_name)
        wait = self.check_interval
        if self.is_on('schedule'):
            wait = min(wait, self._seconds_to_boundary(now))
        if self.is_on('print') and self.print_stats is not None:
            wait = min(wait, PRINT_POLL)
        return eventtime + wait

    # ===== manual values ==================================================
    #
    # One rule: a manual value lasts until AUTO_LIGHT_RESUME, until a print
    # starts (when the Print switch is on), or until DURATION runs out.
    # Effects get DURATION = show_result_for by default.

    def parse_command_value(self, gcmd, text):
        try:
            value = parse_value(text, self.base_color)
        except ValueError as e:
            raise gcmd.error("AutoLight: invalid VALUE '%s': %s" % (text, e))
        if is_effect(value) and not self._effect_exists(value.name):
            raise gcmd.error("AutoLight: effect '%s' not found" % value.name)
        if not is_effect(value) and max(value) > 0. and \
                not self.output.targets:
            raise gcmd.error("AutoLight [%s]: this group has no 'lights', "
                             "only effects or off" % self.light_name)
        return value

    def _manual_ends(self):
        """What ends an open-ended manual value, for the console."""
        ends = "until AUTO_LIGHT_RESUME LIGHT=%s" % self.light_name
        if self.is_on('print'):
            ends += " or a print starts"
        return ends

    def set_manual(self, value, duration=None):
        """AUTO_LIGHT_SET. Returns the console message."""
        if duration is None:
            duration = self.show_result_for if is_effect(value) else 0.
        if self.manual is None:
            shown = self.output.shown()
            self.before_manual = OFF if shown is None else shown
        self.manual = value
        self.output.show(value)
        self.manual_until = None
        waketime = self.reactor.NEVER
        if duration > 0.:
            waketime = self.manual_until = self.reactor.monotonic() + duration
        if self.manual_timer is not None:
            self.reactor.update_timer(self.manual_timer, waketime)
        if duration > 0.:
            end = datetime.datetime.now() + datetime.timedelta(
                seconds=duration)
            until = "for %d s (until %02d:%02d:%02d), then %s" % (
                round(duration), end.hour, end.minute, end.second,
                "automatic" if self.automation_on() else "back to "
                + describe(self.before_manual))
        else:
            until = self._manual_ends()
        return "AutoLight [%s]: %s %s" % (self.light_name, describe(value),
                                          until)

    def _clear_manual(self):
        self.manual = None
        self.manual_until = None
        self.before_manual = None
        if self.manual_timer is not None:
            self.reactor.update_timer(self.manual_timer, self.reactor.NEVER)

    def _manual_end_cb(self, eventtime):
        """DURATION ran out."""
        if self.manual is None or self.shutdown:
            return self.reactor.NEVER
        before = self.before_manual
        self._clear_manual()
        value = None
        if self.automation_on():
            value = self._update(eventtime, force=True, announce=False)
        if value is not None:
            result = "%s (%s)" % (describe(value), self._label())
        elif before is not None:
            self.output.show(before)
            result = "%s (as before)" % describe(before)
        else:
            result = describe(self.output.shown())
        self.gcode.respond_info("AutoLight [%s]: manual value ended -> %s"
                                % (self.light_name, result))
        return self.reactor.NEVER

    def resume(self):
        """AUTO_LIGHT_RESUME: end the manual value and show the automatic
        value now. The message never claims more than actually happened."""
        had_manual = self.manual is not None
        self._clear_manual()
        value = None
        if self.automation_on() and not self.shutdown:
            value = self._update(self.reactor.monotonic(), force=True,
                                 announce=False)
        name = self.light_name
        if value is not None:
            return "AutoLight [%s]: automatic -> %s (%s)" % (
                name, describe(value), self._label())
        if not self.automation_on():
            why = ("%s OFF - AUTO_LIGHT_ENABLE LIGHT=%s to turn on"
                   % (" and ".join(self.switches), name))
        else:
            why = ("schedule OFF and no print value applies now - "
                   "AUTO_LIGHT_ENABLE PART=schedule LIGHT=%s" % name)
        return "AutoLight [%s]: nothing automatic to show (%s)%s; light " \
               "stays %s" % (name, why,
                             ", manual value ended" if had_manual else "",
                             describe(self.output.shown()))

    # ===== status =========================================================

    def _label(self):
        """Why the automation picked its current value."""
        d = self.decision
        if d.schedule is not None:
            return "%s %s" % (d.schedule.name, d.schedule.span())
        if d.mode == 'restored':
            return "as before the print"
        return d.mode or "-"

    def _manual_remaining(self):
        if self.manual is None or self.manual_until is None:
            return None
        return max(0., self.manual_until - self.reactor.monotonic())

    def _reason(self):
        """Why the light shows what it shows now."""
        if self.manual is not None:
            left = self._manual_remaining()
            if left is not None:
                return "manual, %d s left" % round(left)
            return "manual, " + self._manual_ends()
        if self.decision.mode is not None:
            return self._label()
        if not self.automation_on():
            return "automation off, left as is"
        return "no rule active, left as is"

    def status_line(self):
        """e.g. 'schedule ON | print ON | now: 30% (Evening 19:00-23:00)'"""
        def word(part):
            if part not in self.switches:
                return "n/a"
            return "ON" if self.switches[part] else "OFF"
        return "schedule %s | print %s | now: %s (%s)" % (
            word('schedule'), word('print'),
            describe(self.output.shown()), self._reason())

    def report(self):
        lines = ["AutoLight [%s]: %s" % (self.light_name, self.status_line()),
                 "  lights: " + (", ".join(t.spec for t in self.output.targets)
                                 or "(effects only)")]
        for s in self.schedules:
            lines.append("  %d. %s [%s]: %s = %s"
                         % (s.id, s.name, "ENABLED" if s.enabled
                            else "DISABLED", s.span(), describe(s.color)))
        if self.idle_value is not None:
            lines.append("  idle: %s" % describe(self.idle_value))
        for state in PRINT_STATES:
            if state in self.print_values:
                lines.append("  %s: %s" % (state,
                                           describe(self.print_values[state])))
        if any(s in self.print_values for s in RESULT_STATES):
            lines.append("  results shown for %d s" % self.show_result_for)
        return "\n".join(lines)

    # ===== Moonraker / UI status ==========================================

    def get_status(self, eventtime):
        now = datetime.datetime.now()
        out = self.output
        sched = self.decision.schedule
        current = None if out.active_effect else out.current
        target = self.decision.value
        target = None if is_effect(target) else target
        remaining = self._manual_remaining()
        return {
            'enabled': self.automation_on(),
            'schedule_enabled': self.is_on('schedule'),
            'print_enabled': self.is_on('print'),
            'manual': self.manual is not None,
            'manual_value': (describe(self.manual)
                             if self.manual is not None else None),
            'manual_remaining': (round(remaining, 1)
                                 if remaining is not None else None),
            'light': self.light_name,
            'mode': 'manual' if self.manual is not None
                    else self.decision.mode,
            'effect': out.active_effect,
            'current_brightness': level(current),
            'current_color': list(current) if current else None,
            'target_brightness': level(target),
            'target_color': list(target) if target else None,
            'active_schedule_id': sched.id if sched else None,
            'active_schedule_name': sched.name if sched else None,
            'current_time': "%02d:%02d" % (now.hour, now.minute),
            'lights': [t.spec for t in out.targets],
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


class AutoLightManager:
    """Owns the shared G-code commands and dispatches them by LIGHT=name."""

    def __init__(self, printer):
        self.lights = {}
        self.printer = printer
        self.gcode = gcode = printer.lookup_object('gcode')
        for cmd in ('AUTO_LIGHT_RESUME', 'AUTO_LIGHT_ENABLE',
                    'AUTO_LIGHT_DISABLE', 'AUTO_LIGHT_SET',
                    'AUTO_LIGHT_SCHEDULE_ENABLE', 'AUTO_LIGHT_SCHEDULE_DISABLE',
                    'AUTO_LIGHT_LIST_SCHEDULES', 'AUTO_LIGHT_MENU'):
            gcode.register_command(cmd, getattr(self, 'cmd_' + cmd),
                                   desc=getattr(self, 'cmd_%s_help' % cmd))
        # v2 name of AUTO_LIGHT_RESUME
        gcode.register_command('SET_AUTO_LIGHT', self.cmd_AUTO_LIGHT_RESUME,
                               desc="Old name of AUTO_LIGHT_RESUME")

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
        return sorted(self.lights.values(), key=lambda l: l.light_name)

    cmd_AUTO_LIGHT_RESUME_help = ("End manual values and show the automatic "
                                  "value now")

    def cmd_AUTO_LIGHT_RESUME(self, gcmd):
        for light in self._select(gcmd):
            gcmd.respond_info(light.resume())

    @staticmethod
    def _get_part(gcmd):
        part = gcmd.get('PART', 'all').lower()
        if part not in ('all', 'schedule', 'print'):
            raise gcmd.error("AutoLight: PART must be schedule, print or all")
        return part

    def _switch(self, gcmd, on):
        """Turn the Schedule and/or Print switch on/off (None = toggle)."""
        part = self._get_part(gcmd)
        for light in self._select(gcmd):
            gcmd.respond_info(light.switch(part, on))

    cmd_AUTO_LIGHT_ENABLE_help = ("Turn automatic control on "
                                  "[PART=schedule|print|all] (until restart)")

    def cmd_AUTO_LIGHT_ENABLE(self, gcmd):
        self._switch(gcmd, True)

    cmd_AUTO_LIGHT_DISABLE_help = ("Turn automatic control off "
                                   "[PART=schedule|print|all] (until restart)")

    def cmd_AUTO_LIGHT_DISABLE(self, gcmd):
        self._switch(gcmd, False)

    cmd_AUTO_LIGHT_SET_help = ("Set a value by hand (VALUE=warm@0.5 or "
                               "effect:name) [DURATION=seconds]")

    def cmd_AUTO_LIGHT_SET(self, gcmd):
        self._set_manual(gcmd)

    def _set_manual(self, gcmd):
        text = gcmd.get('VALUE')
        duration = gcmd.get_float('DURATION', None, minval=0.)
        for light in self._select(gcmd):
            value = light.parse_command_value(gcmd, text)
            gcmd.respond_info(light.set_manual(value, duration))

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
                gcmd.respond_info(light.resume())
        elif action == 'set':
            self._set_manual(gcmd)
        elif action in ('enable', 'disable', 'toggle'):
            self._switch(gcmd, {'enable': True, 'disable': False}.get(action))
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
                                                 light.status_line()))
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
                 "prompt_text %s" % light.status_line(),
                 "prompt_button_group_start",
                 "prompt_button Auto|%s ACTION=auto|primary" % cmd]
        if light.output.targets:
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
        lines.append("prompt_text Switches (click to toggle):")
        lines.append("prompt_button_group_start")
        for part, on in light.switches.items():
            lines.append("prompt_button %s: %s|%s ACTION=toggle PART=%s|%s"
                         % (part.capitalize(), "ON" if on else "OFF", cmd,
                            part, "success" if on else "warning"))
        lines.append("prompt_button_group_end")
        if back:
            lines.append("prompt_footer_button Back|AUTO_LIGHT_MENU")
        lines += ["prompt_footer_button Close|AUTO_LIGHT_MENU ACTION=close",
                  "prompt_show"]
        self._prompt(lines)


def load_config(config):
    return AutoLight(config)


def load_config_prefix(config):
    return AutoLight(config)
