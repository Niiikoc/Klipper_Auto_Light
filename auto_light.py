import datetime
import logging

class AutoLight:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name()
        
        # Settings from config
        self.pin_name = config.get('pin', 'case_light')
        self.morning_hour = config.getint('morning_hour', 8)
        self.evening_hour = config.getint('evening_hour', 20)
        self.day_brightness = config.getfloat('day_brightness', 0.3, 
                                             minval=0.0, maxval=1.0)
        self.night_brightness = config.getfloat('night_brightness', 1.0,
                                               minval=0.0, maxval=1.0)
        self.check_interval = config.getfloat('check_interval', 600.0, minval=60.0)
        self.enabled = config.getboolean('enabled', True)
        
        # State tracking
        self.last_brightness = None
        self.timer = None
        self.reactor = self.printer.get_reactor()
        self.gcode = None  # Will get this after ready event
        
        # Register event handlers
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)
        
    def _handle_ready(self):
        """Called when Klipper is ready"""
        try:
            # Now we can safely get the gcode object
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
            
            # Start auto check if enabled
            if self.enabled:
                self.start_auto_check()
                logging.info("AutoLight: Automatic control started")
        except Exception as e:
            logging.error(f"AutoLight: Initialization error: {e}")
    
    def _handle_shutdown(self):
        """Called on shutdown - cleanup"""
        self.stop_auto_check()
    
    def start_auto_check(self):
        """Start timer for automatic checking"""
        if self.timer is not None:
            return  # Already running
        
        # Register timer with callback
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
            # Quick time retrieval (non-blocking)
            current_hour = datetime.datetime.now().hour
            logging.info(f"AutoLight: Checking brightness at hour {current_hour}")
            
            # Calculate target brightness
            if self.morning_hour <= current_hour < self.evening_hour:
                target_brightness = self.day_brightness
                period = "Day"
            else:
                target_brightness = self.night_brightness
                period = "Night"
            
            # Get current PIN value to compare
            current_pin_value = self.last_brightness  # Default fallback
            try:
                pin_obj = self.printer.lookup_object(f'output_pin {self.pin_name}')
                # Try different possible attributes
                if hasattr(pin_obj, 'last_value'):
                    current_pin_value = pin_obj.last_value
                elif hasattr(pin_obj, 'value'):
                    current_pin_value = pin_obj.value
                elif hasattr(pin_obj, 'last_print_time'):
                    # For some pins, we need to get the mcu_pin value
                    current_pin_value = getattr(pin_obj, 'last_value', self.last_brightness)
                logging.info(f"AutoLight: Current PIN value: {current_pin_value}, Target: {target_brightness}")
            except Exception as e:
                logging.info(f"AutoLight: Could not read PIN value ({e}), using cached: {current_pin_value}")
            
            # Change if target is different from current
            # Use a small tolerance for floating point comparison
            brightness_diff = abs(target_brightness - (current_pin_value if current_pin_value is not None else 0))
            if brightness_diff > 0.01:
                logging.info(f"AutoLight: Brightness change needed: {current_pin_value} -> {target_brightness} (diff: {brightness_diff:.3f})")
                # Use reactor.register_callback for async execution
                self.reactor.register_callback(
                    lambda et: self._set_brightness(target_brightness, period, current_hour)
                )
                self.last_brightness = target_brightness
            else:
                logging.info(f"AutoLight: Brightness unchanged at {target_brightness} (diff: {brightness_diff:.3f})")
            
        except Exception as e:
            logging.error(f"AutoLight: Timer error: {e}")
        
        # Return next execution time
        next_time = eventtime + self.check_interval
        logging.info(f"AutoLight: Next check in {self.check_interval}s (at {next_time:.1f})")
        return next_time
    
    def _set_brightness(self, brightness, period, hour):
        """Set brightness (async callback)"""
        try:
            if self.gcode is None:
                return
            
            # Create G-code command
            gcmd = f"SET_PIN PIN={self.pin_name} VALUE={brightness:.3f}"
            
            # Run script (this may take some time, but runs async)
            self.gcode.run_script_from_command(gcmd)
            
            # Log and respond
            msg = (f"AutoLight: {period} - "
                  f"Brightness {int(brightness * 100)}% "
                  f"(Hour: {hour:02d}:xx)")
            self.gcode.respond_info(msg)
            logging.info(msg)
            
        except Exception as e:
            logging.error(f"AutoLight: Brightness adjustment error: {e}")
    
    def _manual_check(self):
        """Manual check (for G-code command)"""
        try:
            current_hour = datetime.datetime.now().hour
            
            if self.morning_hour <= current_hour < self.evening_hour:
                brightness = self.day_brightness
                period = "Day"
            else:
                brightness = self.night_brightness
                period = "Night"
            
            # Force brightness change (ignore last_brightness)
            self._set_brightness(brightness, period, current_hour)
            self.last_brightness = brightness
            logging.info(f"AutoLight: Manual check executed, brightness set to {brightness}")
            
        except Exception as e:
            if self.gcode:
                self.gcode.respond_info(f"AutoLight Error: {e}")
            logging.error(f"AutoLight: Manual check failed: {e}")
    
    # ===== G-CODE COMMANDS =====
    
    cmd_SET_AUTO_LIGHT_help = "Manually adjust brightness based on time"
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
    
    def get_status(self, eventtime):
        """Return status for Moonraker API"""
        current_hour = datetime.datetime.now().hour
        is_day = self.morning_hour <= current_hour < self.evening_hour
        
        return {
            'enabled': self.enabled,
            'current_brightness': self.last_brightness,
            'target_brightness': self.day_brightness if is_day else self.night_brightness,
            'period': 'day' if is_day else 'night',
            'day_brightness': self.day_brightness,
            'night_brightness': self.night_brightness,
            'morning_hour': self.morning_hour,
            'evening_hour': self.evening_hour,
            'current_hour': current_hour
        }

def load_config(config):
    return AutoLight(config)