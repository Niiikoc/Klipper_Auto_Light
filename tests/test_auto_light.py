"""Simulation tests for auto_light.py - no Klipper or printer needed.

Run from the repository root:
    python -m unittest discover tests -v

A small fake Klipper (reactor, gcode, print_stats, clock) drives the module
through schedules, prints, manual values, switches and restarts.
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import auto_light  # noqa: E402


# ----- fake Klipper -------------------------------------------------------

class ConfigError(Exception):
    pass


class FakeClock:
    """Replaces datetime.datetime inside auto_light."""
    now_value = datetime.datetime(2026, 11, 26, 12, 0, 0)

    @classmethod
    def now(cls):
        return cls.now_value


class FakeDatetimeModule:
    pass


FakeDatetimeModule.datetime = FakeClock
FakeDatetimeModule.timedelta = datetime.timedelta


class Reactor:
    NOW = 0.
    NEVER = 9999999999999999.

    def __init__(self):
        self.time = 1000.
        self.timers = []

    def monotonic(self):
        return self.time

    def register_timer(self, callback, waketime=NEVER):
        timer = [callback, waketime]
        self.timers.append(timer)
        return timer

    def update_timer(self, timer, waketime):
        timer[1] = waketime

    def run(self, seconds):
        """Advance time, firing timers in order."""
        end = self.time + seconds
        while True:
            due = [t for t in self.timers if t[1] <= end]
            if not due:
                break
            timer = min(due, key=lambda t: t[1])
            self.time = max(self.time, timer[1])
            timer[1] = self.NEVER
            timer[1] = timer[0](self.time)
        self.time = end


class GCode:
    def __init__(self):
        self.commands = {}
        self.messages = []
        self.scripts = []

    def register_command(self, name, func, desc=None):
        self.commands[name] = func

    def respond_info(self, msg):
        self.messages.append(msg)

    def respond_raw(self, msg):
        self.messages.append(msg)

    def run_script(self, script):
        self.scripts.extend(script.split('\n'))


class GCmd:
    def __init__(self, params, gcode):
        self.params = dict((k.upper(), str(v)) for k, v in params.items())
        self.gcode = gcode

    def error(self, msg):
        return ConfigError(msg)

    def get(self, name, default=Exception):
        if name in self.params:
            return self.params[name]
        if default is Exception:
            raise self.error("missing %s" % name)
        return default

    def get_float(self, name, default=Exception, minval=None):
        v = self.get(name, default)
        return None if v is None else float(v)

    def get_int(self, name, default=Exception, minval=None):
        return int(self.get(name, default))

    def respond_info(self, msg):
        self.gcode.respond_info(msg)


class PrintStats:
    def __init__(self):
        self.state = 'standby'

    def get_status(self, eventtime):
        return {'state': self.state}


class OutputPin:
    is_pwm = True


class Printer:
    def __init__(self, state_dir):
        self.reactor = Reactor()
        self.gcode = GCode()
        self.objects = {'gcode': self.gcode, 'print_stats': PrintStats(),
                        'output_pin caselight': OutputPin(),
                        'neopixel sb_leds': object(),
                        'led_effect rainbow': object(),
                        'led_effect printing_fx': object()}
        self.handlers = {}
        self.state_dir = state_dir
        self.config_error = ConfigError

    def get_reactor(self):
        return self.reactor

    def lookup_object(self, name, default=Exception):
        if name in self.objects:
            return self.objects[name]
        if default is Exception:
            raise KeyError(name)
        return default

    def add_object(self, name, obj):
        self.objects[name] = obj

    def register_event_handler(self, event, cb):
        self.handlers.setdefault(event, []).append(cb)

    def send_event(self, event):
        for cb in self.handlers.get(event, []):
            cb()

    def get_start_args(self):
        return {'config_file': os.path.join(self.state_dir, 'printer.cfg')}


class Config:
    def __init__(self, printer, name, options):
        self.printer = printer
        self.name = name
        self.options = dict(options)
        self.error = ConfigError

    def get_printer(self):
        return self.printer

    def get_name(self):
        return self.name

    def get(self, option, default=Exception):
        if option in self.options:
            return str(self.options[option])
        if default is Exception:
            raise ConfigError("missing " + option)
        return default

    def getfloat(self, option, default=Exception, minval=None):
        v = self.get(option, default)
        return None if v is None else float(v)

    def getboolean(self, option, default=Exception):
        v = self.get(option, default)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ('true', '1', 'yes')


# ----- helpers ------------------------------------------------------------

BASIC = {
    'lights': 'caselight',
    'fade_time': 0,
    'schedule_1': '07:00-19:00=1.0 Day',
    'schedule_2': '19:00-07:00=0.2 Night',
    'printing': '0.8',
    'complete': '0.5',
    'show_result_for': 60,
}


class Sim(unittest.TestCase):

    def setUp(self):
        auto_light.datetime = FakeDatetimeModule
        FakeClock.now_value = datetime.datetime(2026, 11, 26, 12, 0, 0)
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        auto_light.datetime = datetime
        shutil.rmtree(self.dir)

    def boot(self, options=BASIC, sections=None):
        """Start a fake Klipper with the given [auto_light] options."""
        self.printer = Printer(self.dir)
        sections = sections or {'auto_light': options}
        self.lights = {}
        for name, opts in sections.items():
            light = auto_light.load_config(Config(self.printer, name, opts))
            self.lights[light.light_name] = light
        self.light = list(self.lights.values())[0]
        self.printer.send_event('klippy:connect')
        self.printer.send_event('klippy:ready')
        self.advance(0.5)
        return self.light

    @property
    def gcode(self):
        return self.printer.gcode

    @property
    def ps(self):
        return self.printer.objects['print_stats']

    def advance(self, seconds):
        self.printer.reactor.run(seconds)

    def cmd(self, name, **params):
        self.gcode.messages = []
        self.gcode.commands[name](GCmd(params, self.gcode))
        self.advance(0.5)
        return "\n".join(self.gcode.messages)

    def pin(self):
        """Last value sent to the case light pin."""
        values = [s for s in self.gcode.scripts if 'PIN=caselight' in s]
        if not values:
            return None
        return float(values[-1].rsplit('=', 1)[1])

    def set_time(self, hh, mm):
        FakeClock.now_value = FakeClock.now_value.replace(hour=hh, minute=mm)

    def print_cycle(self, result='complete'):
        self.ps.state = 'printing'
        self.advance(3)
        self.ps.state = result
        self.advance(3)


# ----- tests --------------------------------------------------------------

class TestSwitches(Sim):

    def test_both_on_schedule_and_print(self):
        self.boot()
        self.assertEqual(self.pin(), 1.0)                  # Day
        self.print_cycle()
        self.assertEqual(self.pin(), 0.5)                  # result shown
        self.advance(61)
        self.assertEqual(self.pin(), 1.0)                  # back to Day
        status = self.light.get_status(0)
        self.assertTrue(status['schedule_enabled'])
        self.assertTrue(status['print_enabled'])
        self.assertEqual(status['mode'], 'schedule')

    def test_schedule_off_print_on_restores_previous(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE', PART='schedule')
        self.cmd('AUTO_LIGHT_SET', VALUE='0.3')
        self.cmd('AUTO_LIGHT_RESUME')            # manual gone, light stays
        self.set_time(20, 0)                     # time changes...
        self.advance(700)
        self.assertEqual(self.pin(), 0.3)        # ...light does not
        self.ps.state = 'printing'
        self.advance(3)
        self.assertEqual(self.pin(), 0.8)
        self.ps.state = 'complete'
        self.advance(3)
        self.assertEqual(self.pin(), 0.5)
        self.advance(61)
        self.assertEqual(self.pin(), 0.3)        # as before the print
        self.assertIn('now: 30%', self.light.status_line())

    def test_schedule_on_print_off_ignores_print(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE', PART='print')
        self.print_cycle()
        self.assertEqual(self.pin(), 1.0)
        self.set_time(19, 0)
        self.advance(700)
        self.assertEqual(self.pin(), 0.2)

    def test_print_off_during_print_goes_to_schedule(self):
        self.boot()
        self.ps.state = 'printing'
        self.advance(3)
        self.assertEqual(self.pin(), 0.8)
        self.cmd('AUTO_LIGHT_DISABLE', PART='print')
        self.assertEqual(self.pin(), 1.0)

    def test_both_off_nothing_changes(self):
        self.boot()
        msg = self.cmd('AUTO_LIGHT_DISABLE')
        self.assertIn('schedule OFF | print OFF', msg)
        before = len(self.gcode.scripts)
        self.set_time(20, 0)
        self.print_cycle()
        self.advance(700)
        self.assertEqual(len(self.gcode.scripts), before)

    def test_enable_reapplies(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE')
        self.set_time(20, 0)
        msg = self.cmd('AUTO_LIGHT_ENABLE', PART='schedule')
        self.assertEqual(self.pin(), 0.2)
        self.assertIn('schedule ON | print OFF', msg)

    def test_off_value_is_just_a_value(self):
        self.boot(dict(BASIC, schedule_2='19:00-07:00=off Night'))
        self.set_time(19, 0)
        self.advance(700)
        self.assertEqual(self.pin(), 0.0)
        self.assertTrue(self.light.is_on('schedule'))
        self.set_time(7, 0)
        self.advance(700)
        self.assertEqual(self.pin(), 1.0)

    def test_toggle_from_panel(self):
        self.boot()
        self.cmd('AUTO_LIGHT_MENU', ACTION='toggle', PART='schedule')
        self.assertFalse(self.light.is_on('schedule'))
        self.assertTrue(self.light.is_on('print'))
        out = "\n".join(self.gcode.messages)
        self.assertIn('Schedule: OFF', out)
        self.assertIn('Print: ON', out)
        self.cmd('AUTO_LIGHT_MENU', ACTION='toggle', PART='schedule')
        self.assertTrue(self.light.is_on('schedule'))

    def test_print_part_without_print_values(self):
        self.boot({'lights': 'caselight', 'schedule_1': '07:00-19:00=1.0'})
        msg = self.cmd('AUTO_LIGHT_DISABLE', PART='print')
        self.assertIn('no Print switch', msg)
        self.assertIn('print n/a', self.light.status_line())


class TestPrintStates(Sim):

    def test_paused_uses_printing_value(self):
        self.boot()
        self.ps.state = 'printing'
        self.advance(3)
        self.ps.state = 'paused'
        self.advance(3)
        self.assertEqual(self.pin(), 0.8)
        self.assertEqual(self.light.decision.mode, 'paused')

    def test_error_and_cancelled(self):
        self.boot(dict(BASIC, error='0.1', cancelled='0.0'))
        self.print_cycle('error')
        self.assertEqual(self.pin(), 0.1)
        self.advance(61)
        self.assertEqual(self.pin(), 1.0)
        self.print_cycle('cancelled')
        self.assertEqual(self.pin(), 0.0)

    def test_result_present_at_startup_is_not_shown(self):
        self.boot()
        self.ps.state = 'complete'          # stale result, never seen printing
        self.cmd('AUTO_LIGHT_DISABLE', PART='print')
        self.cmd('AUTO_LIGHT_ENABLE', PART='print')
        self.assertEqual(self.pin(), 1.0)


class TestResume(Sim):

    def test_resume_when_all_off_says_why(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE')
        msg = self.cmd('AUTO_LIGHT_RESUME')
        self.assertIn('nothing automatic to show', msg)
        self.assertIn('AUTO_LIGHT_ENABLE', msg)
        self.assertNotIn('executed', msg)

    def test_resume_schedule_off_no_print(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE', PART='schedule')
        msg = self.cmd('AUTO_LIGHT_RESUME')
        self.assertIn('schedule OFF and no print value applies', msg)

    def test_resume_applies_value(self):
        self.boot()
        self.cmd('AUTO_LIGHT_SET', VALUE='0.1')
        msg = self.cmd('AUTO_LIGHT_RESUME')
        self.assertEqual(self.pin(), 1.0)
        self.assertIn('automatic -> 100% (Day 07:00-19:00)', msg)

    def test_old_name_still_works(self):
        self.boot()
        self.cmd('AUTO_LIGHT_SET', VALUE='0.1')
        self.cmd('SET_AUTO_LIGHT')
        self.assertEqual(self.pin(), 1.0)


class TestManual(Sim):

    def test_manual_survives_schedule_change(self):
        self.boot()
        msg = self.cmd('AUTO_LIGHT_SET', VALUE='0.4')
        self.assertIn('until AUTO_LIGHT_RESUME LIGHT=default or a print '
                      'starts', msg)
        self.set_time(19, 0)
        self.advance(700)
        self.assertEqual(self.pin(), 0.4)
        self.assertIn('manual', self.light.status_line())

    def test_print_start_ends_manual(self):
        self.boot()
        self.cmd('AUTO_LIGHT_SET', VALUE='0.4')
        self.ps.state = 'printing'
        self.advance(3)
        self.assertEqual(self.pin(), 0.8)
        self.assertIsNone(self.light.manual)

    def test_print_start_keeps_manual_when_print_off(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE', PART='print')
        msg = self.cmd('AUTO_LIGHT_SET', VALUE='0.4')
        self.assertNotIn('print starts', msg)
        self.ps.state = 'printing'
        self.advance(3)
        self.assertEqual(self.pin(), 0.4)

    def test_duration_then_automatic(self):
        self.boot()
        msg = self.cmd('AUTO_LIGHT_SET', VALUE='0.4', DURATION=30)
        self.assertIn('for 30 s (until 12:00:30), then automatic', msg)
        self.assertEqual(self.light.get_status(0)['manual_remaining'], 29.5)
        self.advance(31)
        self.assertEqual(self.pin(), 1.0)
        self.assertIn('manual value ended -> 100%', self.gcode.messages[-1])

    def test_duration_with_automation_off_goes_back(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE')
        msg = self.cmd('AUTO_LIGHT_SET', VALUE='0.4', DURATION=30)
        self.assertIn('then back to 100%', msg)
        self.advance(31)
        self.assertEqual(self.pin(), 1.0)

    def test_effect_ends_after_show_result_for(self):
        self.boot(dict(BASIC, lights='sb_leds'))
        msg = self.cmd('AUTO_LIGHT_SET', VALUE='effect:rainbow')
        self.assertIn('for 60 s', msg)
        self.assertTrue(any('EFFECT=rainbow REPLACE=1' in s
                            for s in self.gcode.scripts))
        self.advance(61)
        self.assertTrue(any('EFFECT=rainbow STOP=1' in s
                            for s in self.gcode.scripts))
        self.assertIsNone(self.light.output.active_effect)

    def test_effect_with_everything_off_stops(self):
        self.boot(dict(BASIC, lights='sb_leds'))
        self.cmd('AUTO_LIGHT_DISABLE')
        self.cmd('AUTO_LIGHT_SET', VALUE='effect:rainbow')
        self.advance(61)
        self.assertIsNone(self.light.output.active_effect)

    def test_status_fields(self):
        self.boot()
        self.cmd('AUTO_LIGHT_SET', VALUE='0.4')
        st = self.light.get_status(0)
        self.assertTrue(st['manual'])
        self.assertEqual(st['manual_value'], '40%')
        self.assertIsNone(st['manual_remaining'])
        self.assertEqual(st['mode'], 'manual')


class TestNothingSaved(Sim):

    def test_disable_lasts_until_restart(self):
        self.boot()
        self.cmd('AUTO_LIGHT_DISABLE')
        self.cmd('AUTO_LIGHT_SCHEDULE_DISABLE', ID=2)
        self.boot()
        self.assertTrue(self.light.is_on('schedule'))
        self.assertTrue(self.light.is_on('print'))
        self.assertTrue(self.light.schedules[1].enabled)
        self.assertEqual(os.listdir(self.dir), [])     # no state file

    def test_old_state_file_is_ignored(self):
        with open(os.path.join(self.dir, 'auto_light_state.json'), 'w') as f:
            json.dump({'enabled': False}, f)            # v2.1 format
        self.boot()
        self.assertTrue(self.light.is_on('schedule'))

    def test_enabled_false_in_config(self):
        self.boot(dict(BASIC, enabled=False))
        self.assertFalse(self.light.automation_on())
        self.assertEqual(self.gcode.scripts, [])
        self.assertIn('automation off', self.light.status_line())
        self.cmd('AUTO_LIGHT_ENABLE')
        self.assertEqual(self.pin(), 1.0)

    def test_state_file_option_still_accepted(self):
        self.boot(dict(BASIC, state_file='~/x.json'))
        self.assertEqual(self.pin(), 1.0)


class TestConfigNames(Sim):

    def test_renamed_options_give_clear_error(self):
        for old, new in (('default', 'idle'),
                         ('finish_hold', 'show_result_for')):
            with self.assertRaises(ConfigError) as ctx:
                self.boot(dict(BASIC, **{old: '0.3'}))
            self.assertIn("'%s' is now called '%s'" % (old, new),
                          str(ctx.exception))

    def test_idle(self):
        light = self.boot({'lights': 'caselight', 'idle': '0.3'})
        self.assertEqual(self.pin(), 0.3)
        self.assertEqual(light.decision.mode, 'idle')

    def test_report(self):
        self.boot()
        out = self.cmd('AUTO_LIGHT_LIST_SCHEDULES')
        self.assertIn('AutoLight [default]: schedule ON | print ON | now: '
                      '100% (Day 07:00-19:00)', out)


class TestMultipleGroups(Sim):

    def test_part_applies_to_each_group(self):
        self.boot(sections={
            'auto_light case': BASIC,
            'auto_light logo': {'lights': 'sb_leds:1', 'idle': 'purple'},
        })
        msg = self.cmd('AUTO_LIGHT_DISABLE', PART='print')
        self.assertIn('[logo]: has no print values', msg)
        self.assertFalse(self.lights['case'].is_on('print'))


if __name__ == '__main__':
    unittest.main()
