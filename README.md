# ☀️ Klipper Auto Light

**Klipper Auto Light** is a flexible Python extension for Klipper that automatically adjusts your printer's case light brightness based on time schedules throughout the day.  
You can define up to **5 custom time schedules** with different brightness levels, and the script will automatically switch between them based on the current time.

---

## ✨ Features

- 🔆 Automatically adjusts light brightness based on time schedules  
- 📅 Support for up to **5 custom time schedules** with individual brightness levels  
- 🌙 Define different brightness for morning, afternoon, evening, and night  
- ⚙️ Simple integration with Klipper  
- 🕰️ Runs automatically on startup — no manual control needed  
- 🔧 Enable/disable individual schedules via G-Code commands  
- 🌍 Schedules can span across midnight (e.g., 23:00-07:00)  
- 🧩 Fully configurable via `printer.cfg`  
- 🏠 Full Home Assistant integration via Moonraker  

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
**Add the following section to your configuration:**
```ini
[auto_light]
pin: caselight              # The LED/light PIN name (as defined in [output_pin])
check_interval: 600         # Check every X seconds (default: 600 = 10 minutes)
enabled: True               # Auto-enable on startup

# Define up to 5 schedules (format: HH:MM-HH:MM=brightness)
# At least 1 schedule is required. Brightness range: 0.0 (off) to 1.0 (full)
schedule_1: 07:00-14:00=1.0     # Morning: 100% brightness
schedule_2: 14:00-19:00=0.6     # Afternoon: 60% brightness  
schedule_3: 19:00-23:00=0.3     # Evening: 30% brightness
schedule_4: 23:00-07:00=0.1     # Night: 10% brightness
# schedule_5: 12:00-13:00=0.5   # Optional 5th schedule
```

**⚠️ Important Notes:**
- Make sure the `pin` matches your printer's hardware pin for the case light (as defined in your `[output_pin]` section)
- At least **1 schedule** must be defined
- You can define **1 to 5 schedules** based on your needs
- Schedules can cross midnight (e.g., `23:00-07:00`)
- Times use 24-hour format with minutes (HH:MM)

### 5️⃣ Restart Klipper
```gcode
FIRMWARE_RESTART
```

---

## 🧩 Available G-Code Commands

You can manually control or test the light anytime using these G-Code commands:

| Command | Description |
|---------|-------------|
| `SET_AUTO_LIGHT` | Triggers an immediate check and adjusts light to current schedule |
| `AUTO_LIGHT_ENABLE` | Enables automatic control |
| `AUTO_LIGHT_DISABLE` | Disables automatic control |
| `AUTO_LIGHT_LIST_SCHEDULES` | Lists all configured schedules and their status |
| `AUTO_LIGHT_SCHEDULE_ENABLE ID=X` | Enables schedule X (1-5) |
| `AUTO_LIGHT_SCHEDULE_DISABLE ID=X` | Disables schedule X (1-5) |
| `AUTO_LIGHT_RESET_CACHE` | Resets cached brightness (forces update on next check) |

### Examples:
```gcode
# Disable afternoon schedule temporarily
AUTO_LIGHT_SCHEDULE_DISABLE ID=2

# Re-enable it later
AUTO_LIGHT_SCHEDULE_ENABLE ID=2

# See all schedules and their status
AUTO_LIGHT_LIST_SCHEDULES

# Force immediate brightness check
SET_AUTO_LIGHT
```

---

## 🧠 How It Works

1. `auto_light.py` runs as a Klipper extension
2. It checks the system time at regular intervals (default: every 10 minutes)
3. It compares the current time against all **enabled** schedules
4. During each time period, the light automatically adjusts to the configured brightness
5. If you manually change the brightness, it will be corrected on the next check cycle
6. You can enable/disable individual schedules without restarting Klipper

---

## 🔧 Example Use Cases

### Basic Day/Night Cycle
```ini
[auto_light]
pin: caselight
schedule_1: 08:00-20:00=1.0     # Day: Full brightness
schedule_2: 20:00-08:00=0.2     # Night: Dim light
```

### Multi-Level Brightness Throughout the Day
```ini
[auto_light]
pin: caselight
schedule_1: 07:00-12:00=1.0     # Morning: 100%
schedule_2: 12:00-14:00=0.5     # Lunch: 50% (reduce glare)
schedule_3: 14:00-19:00=0.8     # Afternoon: 80%
schedule_4: 19:00-23:00=0.3     # Evening: 30%
schedule_5: 23:00-07:00=0.1     # Night: 10%
```

### Workspace Optimization
```ini
[auto_light]
pin: caselight
schedule_1: 09:00-17:00=1.0     # Work hours: Full brightness
schedule_2: 17:00-22:00=0.4     # After work: Dim
schedule_3: 22:00-09:00=0.0     # Sleep: Off
```

## 🔧 Advanced Configuration

### Temporarily Disable a Schedule
If you want to temporarily disable a schedule without editing `printer.cfg`:
```gcode
AUTO_LIGHT_SCHEDULE_DISABLE ID=3
```

This is perfect for:
- Temporarily working late (disable evening/night schedules)
- Weekend adjustments
- Special events
- Testing different brightness levels

### Protection Against Errors
- At least **1 schedule must remain enabled** at all times
- The script prevents you from disabling the last active schedule
- If all schedules somehow become disabled, schedule 1 will be automatically re-enabled

---

## 💡 Tips & Best Practices

1. **Start simple**: Begin with 2-3 schedules and adjust based on your needs
2. **Overlap prevention**: Make sure your schedules don't have gaps (one should start when another ends)
3. **Midnight crossing**: Use schedules like `23:00-07:00` for overnight periods
4. **Testing**: Use `check_interval: 60` initially to test faster, then increase to 600 (10 minutes) for normal use
5. **Manual override**: If you manually change brightness, it will be corrected on the next automatic check

---

## 🧩 Uninstallation

If you ever want to remove it:
```bash
cd ~/klipper/klippy/extras
rm -f auto_light.py
```
Then remove the `[auto_light]` section from your `printer.cfg` and restart Klipper.

---

## 💬 Notes

- The script uses your Raspberry Pi's system time — make sure your timezone is set correctly
- Works with any Klipper-supported light control pin
- You can combine it with other light control macros for manual overrides if desired
- Schedules are sorted automatically by start time
- All times use 24-hour format
- Brightness values are from 0.0 (off) to 1.0 (full power)

---

## 🪄 License

This project is licensed under the MIT License.

---

## 🙏 Contributing

Contributions, issues, and feature requests are welcome!  
Feel free to check the [issues page](https://github.com/Niiikoc/Klipper_Auto_Light/issues).

---

## 📝 Changelog

### v2.0.0
- ✨ Added support for up to 5 custom time schedules
- 🔧 New commands to enable/disable individual schedules
- 🌍 Support for schedules crossing midnight
- 📊 Added schedule listing command
- 🏠 Enhanced Home Assistant integration
- 🇬🇧 All logs and messages in English

### v1.0.0
- 🎉 Initial release with basic day/night cycle
