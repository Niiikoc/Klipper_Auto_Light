# ☀️ Klipper Auto Light

**Klipper Auto Light** is a simple Python extension for Klipper that automatically adjusts your printer’s case light brightness based on the time of day.  
You can define custom brightness levels for **daytime** and **nighttime**, and the script will smoothly switch between them automatically.

---

## ✨ Features

- 🔆 Automatically adjusts light brightness depending on the time of day  
- 🌙 Customizable day/night brightness levels  
- ⚙️ Simple integration with Klipper  
- 🕰️ Runs automatically on startup — no manual control needed  
- 🧩 Fully configurable via `printer.cfg`

---

## 📦 Installation

### 1️⃣ Connect to your Raspberry Pi via SSH

```bash
ssh pi@{printer_IP}.local  <= Replace {printer_IP} with the IP address of your printer.
```
2️⃣ Navigate to the Klipper extras directory

```bash
cd ~/klipper/klippy/extras
```

3️⃣ Clone the repository
```bash
git clone https://github.com/Niiikoc/Klipper_Auto_Light.git
```
This will create a new folder named Klipper_Auto_Light containing the auto_light.py script.

4️⃣ Edit your printer.cfg

**Add the following section to your configuration:**

```bash
[auto_light]
pin: caselight               # The LED/light PIN name (as defined in [output_pin]) 
morning_hour: 8              # Hour to start low brightness (0-23)
evening_hour: 20             # Hour to start high brightness (0-23)
day_brightness: 1.0          # Day brightness (0.0-1.0)
night_brightness: 0.3        # Night brightness (0.0-1.0)
check_interval: 600          # Check every X seconds (minimum: 60, default: 600)
enabled: True                # Auto-enable on startup (True/False)
```

**⚠️ Make sure the light_pin matches your printer’s hardware pin for the case light.**

5️⃣ Restart Klipper

```bash
FIRMWARE_RESTART
```

**🧠 How It Works**

auto_light.py runs as a Klipper extension.
It checks the system time at regular intervals and compares it against the configured day_start and night_start values.

During daytime, the light will automatically set to day_brightness.

During nighttime, the light will automatically dim to night_brightness.

You can freely change the hours and brightness values to match your environment.

## 🔧 Example Use Case

| Time           | Brightness | Description           |
|----------------|-------------|------------------------|
| 08:00 → 20:00  | 100%        | Day mode, full brightness |
| 20:00 → 08:00  | 30%         | Night mode, softer light  |

Perfect if your printer runs in your workspace or bedroom and you don’t want full light overnight.

**🧩 Uninstallation**

If you ever want to remove it:

```bash
cd ~/klipper/klippy/extras
rm -rf Klipper_Auto_Light
```

Then remove the [auto_light] section from your printer.cfg and restart Klipper.

💬 Notes

The script uses your Raspberry Pi’s system time — make sure your timezone is set correctly.

Works with any Klipper-supported light control pin.

You can combine it with other light control macros for manual overrides if desired.
