; Auto Light test print: ends as "complete" after about 90 seconds.
; No heating, no motion, safe on any printer. Upload and print it.
; Expected: the 'printing' value while it runs, then the 'complete' value
; for show_result_for seconds, then back to the schedule (or, with the
; Schedule switch off, back to what was shown before the print).
; Press CANCEL during it to test the 'cancelled' value instead.
M117 AutoLight test: printing
AUTO_LIGHT_LIST_SCHEDULES
G4 P30000
AUTO_LIGHT_LIST_SCHEDULES
G4 P30000
G4 P30000
M117 AutoLight test: done
