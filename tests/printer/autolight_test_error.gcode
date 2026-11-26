; Auto Light test print: ends with an error after about 30 seconds.
; No heating, no motion, safe on any printer. Upload and print it.
; Expected: the 'printing' value, then the 'error' value for
; show_result_for seconds, then back to the schedule.
; The error is caused on purpose by an invalid AUTO_LIGHT_SET value.
M117 AutoLight test: printing
G4 P30000
M117 AutoLight test: error now
AUTO_LIGHT_SET VALUE=this_error_is_intended
