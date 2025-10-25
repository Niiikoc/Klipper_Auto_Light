import datetime
import logging

class AutoLight:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name()
        
        # Basic settings
        self.pin_name = config.get('pin', 'case_light')
        self.check_interval = config.getfloat('check_interval', 600.0, minval=60.0)
        self.enabled = config.getboolean('enabled', True)
        
        # Parse up to 5 schedules from config
        self.schedules = []
        for i in range(1, 6):  # schedule_1 to schedule_5
            option_name = f'schedule_{i}'
            schedule_str = config.get(option_name, None)
            
            if schedule_str is None:
                continue
            try:
                # Format: "07:00-14:00=1.0" or "14:00-19:00=0.6"
                time_part, brightness_part = schedule_str.split('=')
                start_time, end_time = time_part.split('-')
                
                start_hour, start_min = map(int, start_time.split(':'))
                end_hour, end_min = map(int, end_time.split(':'))
                brightness = float(brightness_part)
                
                if not (0.0 <= brightness <= 1.0):
                    raise ValueError("Brightness must be between 0.0 and 1.0")
                
                self.schedules.append({
                    'id': i,
                    'start_hour': start_hour,
                    'start_min': start_min,
                    'end_hour': end_hour,
                    'end_min': end_min,
                    'brightness': brightness,
                    'enabled': True,  # All schedules enabled by default
                    'name': f'Schedule {i}'
                })
                logging.info(f"AutoLight: Loaded schedule_{i}: "
                           f"{start_hour:02d}:{start_min:02d}-{end_hour:02d}:{end_min:02d} "
                           f"= {int(brightness*100)}%")
            except Exception as e:
                logging.error(f"AutoLight: Error parsing {option_name}: {e}")
                raise config.error(f"Invalid schedule format for {option_name}: {schedule_str}")
        
        # Require at least one schedule
        if not self.schedules:
            raise config.error("AutoLight: At least one schedule (schedule_1) must be defined")
        
        # Validate: Must have at least 1 enabled schedule at all times
        if len(self.schedules) < 1:
            raise config.error("AutoLight: At least 1 schedule required")
        
        # Sort schedules by start time
        self.schedules.sort(key=lambda s: s['start_hour'] * 60 + s['start_min'])
        
        # State tracking
        self.last_brightness = None
        self.current_schedule_id = None
        self.timer = None
        self.reactor = self.printer.get_reactor()
        self.gcode = None
        
        # Register event handlers
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)
        
    def _handle_ready(self):
        """Called when Klipper is ready"""
        try:
            self.gcode = self.printer.lookup_object('gcode')
            
            # Register commands
            self.gcode.register_command('SET_AUTO_LIGHT',
                                       self.cmd_SET_AUTO_LIGHT,
                                       desc=self.cmd_SET_AUTO_LIGHT_help)
            self.gcode.register_command('AUTO_LIGHT_ENABLE',
                                       self.cmd_AUTO_LIGHT_ENABLE,
                                       desc=self.cmd_AUTO_LIGHT_ENABLE_help)
            self.gcode.register_command('AUTO_LIGHT_DISABLE',
                                       self.cmd_AUTO_LIGHT_DISABLE,
                                       desc=self.cmd_AUTO_LIGHT_DISABLE_help)
            self.gcode.register_command('AUTO_LIGHT_SCHEDULE_ENABLE',
                                       self.cmd_AUTO_LIGHT_SCHEDULE_ENABLE,
                                       desc=self.cmd_AUTO_LIGHT_SCHEDULE_ENABLE_help)
            self.gcode.register_command('AUTO_LIGHT_SCHEDULE_DISABLE',
                                       self.cmd_AUTO_LIGHT_SCHEDULE_DISABLE,
                                       desc=self.cmd_AUTO_LIGHT_SCHEDULE_DISABLE_help)
            self.gcode.register_command('AUTO_LIGHT_LIST_SCHEDULES',
                                       self.cmd_AUTO_LIGHT_LIST_SCHEDULES,
                                       desc=self.cmd_AUTO_LIGHT_LIST_SCHEDULES_help)
            
            # Start auto check if enabled
            if self.enabled:
                self.start_auto_check()
                logging.info("AutoLight: Automatic control started")
        except Exception as e:
            logging.error(f"AutoLight: Initialization error: {e}")
    
    def _handle_shutdown(self):
        """Called on shutdown - cleanup"""
        self.stop_auto_check()
    
    def _get_minutes_from_midnight(self, hour, minute):
        """Convert hour:minute to minutes from midnight"""
        return hour * 60 + minute
    
    def _get_enabled_schedules(self):
        """Get list of currently enabled schedules"""
        return [s for s in self.schedules if s['enabled']]
    
    def _find_active_schedule(self, current_hour, current_min):
        """Find which enabled schedule should be active now"""
        current_minutes = self._get_minutes_from_midnight(current_hour, current_min)
        enabled_schedules = self._get_enabled_schedules()
        
        if not enabled_schedules:
            logging.error("AutoLight: No enabled schedules! Re-enabling schedule 1")
            self.schedules[0]['enabled'] = True
            enabled_schedules = [self.schedules[0]]
        
        for schedule in enabled_schedules:
            start_minutes = self._get_minutes_from_midnight(
                schedule['start_hour'], schedule['start_min'])
            end_minutes = self._get_minutes_from_midnight(
                schedule['end_hour'], schedule['end_min'])
            
            # Handle schedules that cross midnight
            if start_minutes > end_minutes:  # e.g., 20:00 to 08:00
                if current_minutes >= start_minutes or current_minutes < end_minutes:
                    return schedule
            else:  # Normal schedule within same day
                if start_minutes <= current_minutes < end_minutes:
                    return schedule
        
        # If no schedule matches, use the first enabled schedule as default
        return enabled_schedules[0] if enabled_schedules else None
    
    def start_auto_check(self):
        """Start timer for automatic checking"""
        if self.timer is not None:
            return  # Already running
        
        self.timer = self.reactor.register_timer(
            self._timer_callback, 
            self.reactor.NOW
        )
        logging.info("AutoLight: Timer enabled")
    
    def stop_auto_check(self):
        """Stop the timer"""
        if self.timer is not None:
            self.reactor.unregister_timer(self.timer)
            self.timer = None
            logging.info("AutoLight: Timer disabled")
    
    def _timer_callback(self, eventtime):
        """Timer callback - runs in reactor event loop (non-blocking)"""
        logging.info(f"AutoLight: Timer callback triggered (enabled={self.enabled})")
        
        if not self.enabled:
            logging.info("AutoLight: Timer stopped (disabled)")
            return self.reactor.NEVER
        
        try:
            # Get current time
            now = datetime.datetime.now()
            current_hour = now.hour
            current_min = now.minute
            
            logging.info(f"AutoLight: Checking brightness at {current_hour:02d}:{current_min:02d}")
            
            # Find active schedule
            active_schedule = self._find_active_schedule(current_hour, current_min)
            
            if active_schedule:
                target_brightness = active_schedule['brightness']
                schedule_name = active_schedule['name']
                schedule_id = active_schedule['id']
                
                logging.info(f"AutoLight: Active {schedule_name} "
                           f"({active_schedule['start_hour']:02d}:{active_schedule['start_min']:02d}"
                           f"-{active_schedule['end_hour']:02d}:{active_schedule['end_min']:02d}) "
                           f"Target: {int(target_brightness*100)}%")
                
                # Get current PIN value
                current_pin_value = None
                try:
                    pin_obj = self.printer.lookup_object(f'output_pin {self.pin_name}')
                    if hasattr(pin_obj, 'last_value'):
                        current_pin_value = pin_obj.last_value
                        logging.info(f"AutoLight: Read PIN value from last_value: {current_pin_value}")
                    elif hasattr(pin_obj, 'value'):
                        current_pin_value = pin_obj.value
                        logging.info(f"AutoLight: Read PIN value from value: {current_pin_value}")
                    else:
                        logging.warning(f"AutoLight: PIN object has no last_value or value attribute")
                        logging.warning(f"AutoLight: Available attributes: {dir(pin_obj)}")
                        current_pin_value = self.last_brightness
                except Exception as e:
                    logging.warning(f"AutoLight: Could not read PIN value ({e}), using cached")
                    current_pin_value = self.last_brightness
                
                # If we still don't have a value, use 0
                if current_pin_value is None:
                    logging.warning(f"AutoLight: No PIN value available, assuming 0")
                    current_pin_value = 0
                
                logging.info(f"AutoLight: Comparison - Current: {current_pin_value}, Target: {target_brightness}")
                
                # Check if change is needed
                brightness_diff = abs(target_brightness - current_pin_value)
                
                if brightness_diff > 0.01:
                    logging.info(f"AutoLight: Brightness change needed: {current_pin_value} -> "
                               f"{target_brightness} (diff: {brightness_diff:.3f})")
                    self.reactor.register_callback(
                        lambda et: self._set_brightness(target_brightness, schedule_name, 
                                                       current_hour, current_min)
                    )
                    self.last_brightness = target_brightness
                    self.current_schedule_id = schedule_id
                else:
                    logging.info(f"AutoLight: Brightness unchanged at {target_brightness} "
                               f"(diff: {brightness_diff:.3f})")
            else:
                logging.warning("AutoLight: No active schedule found!")
            
        except Exception as e:
            logging.error(f"AutoLight: Timer error: {e}")
        
        # Return next execution time
        next_time = eventtime + self.check_interval
        logging.info(f"AutoLight: Next check in {self.check_interval}s")
        return next_time
    
    def _set_brightness(self, brightness, schedule_name, hour, minute):
        """Set brightness (async callback)"""
        try:
            if self.gcode is None:
                return
            
            gcmd = f"SET_PIN PIN={self.pin_name} VALUE={brightness:.3f}"
            self.gcode.run_script_from_command(gcmd)
            
            msg = (f"AutoLight: {schedule_name} - "
                  f"Brightness {int(brightness * 100)}% "
                  f"(Time: {hour:02d}:{minute:02d})")
            self.gcode.respond_info(msg)
            logging.info(msg)
            
        except Exception as e:
            logging.error(f"AutoLight: Brightness adjustment error: {e}")
    
    def _manual_check(self):
        """Manual check (for G-code command)"""
        try:
            now = datetime.datetime.now()
            active_schedule = self._find_active_schedule(now.hour, now.minute)
            
            if active_schedule:
                brightness = active_schedule['brightness']
                schedule_name = active_schedule['name']
                self._set_brightness(brightness, schedule_name, now.hour, now.minute)
                self.last_brightness = brightness
                self.current_schedule_id = active_schedule['id']
                logging.info(f"AutoLight: Manual check executed, using {schedule_name}")
            else:
                if self.gcode:
                    self.gcode.respond_info("AutoLight: No active schedule found")
            
        except Exception as e:
            if self.gcode:
                self.gcode.respond_info(f"AutoLight Error: {e}")
            logging.error(f"AutoLight: Manual check failed: {e}")
    
    # ===== G-CODE COMMANDS =====
    
    cmd_SET_AUTO_LIGHT_help = "Manually adjust brightness based on current time schedule"
    def cmd_SET_AUTO_LIGHT(self, gcmd):
        """Manual execution of the check"""
        self._manual_check()
        gcmd.respond_info("AutoLight: Check executed")
    
    cmd_AUTO_LIGHT_ENABLE_help = "Enable automatic light control"
    def cmd_AUTO_LIGHT_ENABLE(self, gcmd):
        """Enable automatic control"""
        self.enabled = True
        self.start_auto_check()
        gcmd.respond_info("AutoLight: ENABLED")
        logging.info("AutoLight: Enabled via G-code")
    
    cmd_AUTO_LIGHT_DISABLE_help = "Disable automatic light control"
    def cmd_AUTO_LIGHT_DISABLE(self, gcmd):
        """Disable automatic control"""
        self.enabled = False
        self.stop_auto_check()
        gcmd.respond_info("AutoLight: DISABLED")
        logging.info("AutoLight: Disabled via G-code")
    
    cmd_AUTO_LIGHT_SCHEDULE_ENABLE_help = "Enable a specific schedule (ID=1-5)"
    def cmd_AUTO_LIGHT_SCHEDULE_ENABLE(self, gcmd):
        """Enable a specific schedule"""
        try:
            schedule_id = gcmd.get_int('ID', minval=1, maxval=5)
            
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    schedule['enabled'] = True
                    gcmd.respond_info(f"AutoLight: Enabled {schedule['name']}")
                    logging.info(f"AutoLight: Schedule {schedule_id} enabled via G-code")
                    return
            
            gcmd.respond_info(f"AutoLight: Schedule {schedule_id} not found in config")
            
        except Exception as e:
            gcmd.respond_info(f"AutoLight: Error: {e}")
    
    cmd_AUTO_LIGHT_SCHEDULE_DISABLE_help = "Disable a specific schedule (ID=1-5). At least one must remain enabled."
    def cmd_AUTO_LIGHT_SCHEDULE_DISABLE(self, gcmd):
        """Disable a specific schedule"""
        try:
            schedule_id = gcmd.get_int('ID', minval=1, maxval=5)
            
            # Count currently enabled schedules
            enabled_count = sum(1 for s in self.schedules if s['enabled'])
            
            if enabled_count <= 1:
                gcmd.respond_info("AutoLight: Cannot disable - at least one schedule must remain enabled")
                return
            
            for schedule in self.schedules:
                if schedule['id'] == schedule_id:
                    if not schedule['enabled']:
                        gcmd.respond_info(f"AutoLight: {schedule['name']} is already disabled")
                        return
                    
                    schedule['enabled'] = False
                    gcmd.respond_info(f"AutoLight: Disabled {schedule['name']}")
                    logging.info(f"AutoLight: Schedule {schedule_id} disabled via G-code")
                    return
            
            gcmd.respond_info(f"AutoLight: Schedule {schedule_id} not found in config")
            
        except Exception as e:
            gcmd.respond_info(f"AutoLight: Error: {e}")
    
    cmd_AUTO_LIGHT_LIST_SCHEDULES_help = "List all configured schedules and their status"
    def cmd_AUTO_LIGHT_LIST_SCHEDULES(self, gcmd):
        """List all schedules"""
        if not self.schedules:
            gcmd.respond_info("AutoLight: No schedules configured")
            return
        
        enabled_count = sum(1 for s in self.schedules if s['enabled'])
        gcmd.respond_info(f"AutoLight: {len(self.schedules)} schedule(s) configured "
                         f"({enabled_count} enabled):")
        
        for schedule in self.schedules:
            status = "ENABLED" if schedule['enabled'] else "DISABLED"
            gcmd.respond_info(f"  {schedule['id']}. {schedule['name']} [{status}]: "
                            f"{schedule['start_hour']:02d}:{schedule['start_min']:02d}"
                            f"-{schedule['end_hour']:02d}:{schedule['end_min']:02d} "
                            f"= {int(schedule['brightness']*100)}%")
    
    def get_status(self, eventtime):
        """Return status for Moonraker API"""
        now = datetime.datetime.now()
        active_schedule = self._find_active_schedule(now.hour, now.minute)
        
        return {
            'enabled': self.enabled,
            'current_brightness': self.last_brightness,
            'target_brightness': active_schedule['brightness'] if active_schedule else None,
            'active_schedule_id': active_schedule['id'] if active_schedule else None,
            'active_schedule_name': active_schedule['name'] if active_schedule else None,
            'current_time': f"{now.hour:02d}:{now.minute:02d}",
            'schedules': [
                {
                    'id': s['id'],
                    'name': s['name'],
                    'start': f"{s['start_hour']:02d}:{s['start_min']:02d}",
                    'end': f"{s['end_hour']:02d}:{s['end_min']:02d}",
                    'brightness': s['brightness'],
                    'enabled': s['enabled']
                }
                for s in self.schedules
            ]
        }

def load_config(config):
    return AutoLight(config)