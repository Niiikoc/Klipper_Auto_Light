# Auto Light – printer checklist

Upload the two `.gcode` files from this folder in Mainsail/Fluidd. Run
`AUTO_LIGHT_LIST_SCHEDULES` after each step and compare the `schedule … | print … | now: …` line.

| # | Do | Expect |
|---|---|---|
| 1 | `FIRMWARE_RESTART` | `AUTO_LIGHT_LIST_SCHEDULES` shows `schedule ON \| print ON` |
| 2 | Print `autolight_test_complete.gcode` | `printing` value, then `complete` for `show_result_for` s, then the schedule |
| 3 | Print `autolight_test_error.gcode` | `printing`, then `error`, then the schedule |
| 4 | Print the complete test, press **Cancel** | `cancelled` value, then the schedule |
| 5 | `AUTO_LIGHT_DISABLE PART=schedule`, `AUTO_LIGHT_SET VALUE=0.3`, `AUTO_LIGHT_RESUME` | Resume says `schedule OFF and no print value applies now`, light stays 30% |
| 6 | Print the complete test | `printing` → `complete` → back to 30% (`as before the print`) |
| 7 | `AUTO_LIGHT_ENABLE`, then `AUTO_LIGHT_DISABLE PART=print`, print the complete test | Light ignores the print and follows the schedule |
| 8 | `AUTO_LIGHT_ENABLE`, `AUTO_LIGHT_SET VALUE=0.4`, start a print | Console: `print started, manual value ended` |
| 9 | `AUTO_LIGHT_SET VALUE=0.4 DURATION=30` | Console names the end time; after 30 s `manual value ended -> …` |
| 10 | `AUTO_LIGHT_DISABLE`, `FIRMWARE_RESTART` | After the restart both are ON again (nothing is saved) |
| 11 | `AUTO_LIGHT_RESUME` (still both off) | Says why nothing happens, never "check executed" |
| 12 | `AUTO_LIGHT_MENU` | Two toggle buttons `Schedule: ON/OFF` and `Print: ON/OFF`; clicking flips them |
| 13 | Set `enabled: False` in printer.cfg, restart | Both OFF, the light is not touched |
| 14 | Rename `idle:` to `default:` in printer.cfg, restart | Config error: `option 'default' is now called 'idle'`. Rename it back |
