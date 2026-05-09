"""
ESP32-C3 MicroPython AC-FREE UART IR controller.

Main interfaces:
- OLED + buttons for local control
- BLE local remote for phone control
- optional minimal web diagnostics when explicitly enabled
"""

import time
try:
    import ntptime
except ImportError:
    ntptime = None
try:
    import ujson as json
except ImportError:
    import json

from src.config import load_config, save_config, config_missing_wifi
from src.ir_profiles import load_profile, command_path as profile_command_path
from src.ir_uart import from_config as ir_from_config, legacy_command_path
from src.sensor_dht import from_config as dht_from_config
from src.climate_controller import ClimateController, MODE_AC_FREE, MODE_OFF
from src.wifi_manager import WifiManager
from src.oled_ui import OledUi
from src.web_config import WebConfigServer
from src.ble_remote import BleRemote
from src.buttons import Buttons
from src.local_os import LocalOs
from src.utils import log


def file_exists(path):
    try:
        with open(path, "rb"):
            return True
    except OSError:
        return False


def local_time_text(config):
    offset = int(config.get("timezone_offset_hours", 8)) * 3600
    try:
        t = time.localtime(time.time() + offset)
        return ("%02d:%02d" % (t[3], t[4]))
    except Exception:
        return "--:--"


def fmt_number(value, digits=1):
    if value is None:
        return "--"
    try:
        return ("{:." + str(digits) + "f}").format(float(value))
    except Exception:
        return "--"


def local_tuple(config):
    offset = int(config.get("timezone_offset_hours", 8)) * 3600
    try:
        return time.localtime(time.time() + offset)
    except Exception:
        return None


def sync_time():
    if ntptime is None:
        return False
    try:
        ntptime.host = "pool.ntp.org"
        ntptime.settime()
        log("ntp", "synced UTC")
        return True
    except Exception as exc:
        log("ntp", "failed: " + str(exc))
        return False


def build_command_resolver(config):
    def resolve(command_name):
        profile_name = config.get("ir", {}).get("profile", "default")
        profile = load_profile(profile_name)
        if profile:
            path = profile_command_path(profile_name, profile, command_name)
            if path and file_exists(path):
                return path

        legacy = {
            "strong": "strong_001.bin",
            "power_on": "strong_001.bin",
            "power_off": "guan_001.bin",
        }
        if command_name in legacy:
            path = legacy_command_path(legacy[command_name])
            if file_exists(path):
                return path
        return None
    return resolve


def main():
    log("boot", "ESP32 UART IR AC controller")
    config = load_config()

    wifi = WifiManager(config.get("device_name", "ntu_ac_controller"))
    setup_mode = False
    setup_ip = ""
    time_synced = False
    wifi_status = "--"
    if config_missing_wifi(config):
        setup_mode = True
        setup_ip = wifi.start_ap()
        wifi_status = "AP"
        log("setup", "Wi-Fi config missing; AP at " + setup_ip)
    else:
        if wifi.connect(config["wifi"]["ssid"], config["wifi"].get("password", "")):
            log("wifi", "STA connected")
            time_synced = sync_time()
            wifi_status = "OK"
            wifi.stop_all()
            log("wifi", "radio stopped after NTP")
        else:
            setup_mode = True
            setup_ip = wifi.start_ap()
            wifi_status = "AP"
            log("wifi", "STA failed; setup AP at " + setup_ip)

    ir = ir_from_config(config)
    sensor = dht_from_config(config)
    oled = OledUi(config)
    oled.init()

    command_path = build_command_resolver(config)
    climate = ClimateController(config, ir, command_path)
    local_os = LocalOs(config, save_config, climate, oled)
    oled.on_before_auto_off = local_os.idle_before_screen_off
    if setup_mode:
        local_os.open_wifi_setup()

    def web_state():
        avg_ms = int(config.get("climate", {}).get("control_average_ms", 60000))
        return {
            "mode": climate.mode,
            "time": local_time_text(config) if time_synced else "--:--",
            "wifi": wifi_status,
            "ip": setup_ip,
            "status": climate.status,
            "temperature": fmt_number(sensor.temperature, 1),
            "temperature_avg": fmt_number(sensor.average_temperature(avg_ms), 1),
            "humidity": fmt_number(sensor.humidity, 0),
            "target_temperature": config["climate"]["target_temperature"],
            "fan_mode": config["climate"]["fan_mode"],
            "active_cooling": climate.active_cooling,
            "ir_send_count": climate.send_count,
            "last_ir_command": ir.last_command,
            "error": climate.error,
        }

    web = WebConfigServer(config, save_config, climate, oled, command_path, web_state)
    if setup_mode and config.get("web", {}).get("enabled", True):
        web.start()

    def handle_ble_command(command):
        if command.startswith("{"):
            try:
                data = json_loads(command)
                return handle_blinker_json(data)
            except Exception as exc:
                climate.error = str(exc)
                return "ERR json " + str(exc)
        parts = command.strip().split()
        if not parts:
            return "ERR empty"
        key = parts[0].upper()
        try:
            if key == "POWER" and len(parts) >= 2:
                climate.set_power(parts[1].upper() == "ON")
            elif key == "MODE" and len(parts) >= 2:
                climate.set_mode(parts[1])
            elif key == "TEMP" and len(parts) >= 2:
                climate.set_target_temperature(float(parts[1]))
            elif key == "TEMP_DELTA" and len(parts) >= 2:
                climate.adjust_target_temperature(float(parts[1]))
            elif key == "FAN" and len(parts) >= 2:
                climate.set_fan_mode(parts[1])
            elif key == "SCREEN" and len(parts) >= 2:
                if parts[1].upper() == "ON":
                    oled.wake()
                else:
                    oled.screen_off()
            elif key == "STATUS":
                pass
            elif key == "LEARN":
                climate.status = "learn via OLED"
                return "ERR learn use OLED"
            elif key == "WIFI":
                climate.status = "wifi via setup web"
                return "ERR wifi use setup web"
            else:
                return "ERR bad command"
            save_config(config)
            return "OK"
        except Exception as exc:
            climate.error = str(exc)
            return "ERR " + str(exc)

    def json_loads(text):
        return json.loads(text)

    def blinker_state_json():
        return json.dumps(blinker_state_dict())

    def blinker_state_dict():
        ids = config.get("blinker", {})
        fan_mode = config["climate"].get("fan_mode", "fan_1")
        fan_value = 6 if fan_mode == "strong" else int(fan_mode[-1]) if fan_mode.startswith("fan_") else 1
        state = {}
        state[ids.get("power", "btn-0fh")] = {"switch": "on" if climate.mode == MODE_AC_FREE else "off"}
        state[ids.get("fan", "ran-5hc")] = {"value": fan_value}
        temp_widget = ids.get("target_temperature", "ran-egl")
        target_value = int(float(config["climate"].get("target_temperature", 25)))
        state[temp_widget] = {
            "value": target_value
        }
        if temp_widget != "ran-egl":
            state["ran-egl"] = {
                "value": target_value
            }
        state["tex-status"] = {"text": "off" if climate.mode == MODE_OFF else climate.status}
        state[ids.get("current_temperature", "num-d2v")] = {
            "value": float(fmt_number(sensor.average_temperature(), 1)) if sensor.average_temperature() is not None else 0
        }
        state[ids.get("humidity", "num-m74")] = {
            "value": int(float(fmt_number(sensor.humidity, 0))) if sensor.humidity is not None else 0
        }
        return state

    def blinker_partial_json(keys):
        full = blinker_state_dict()
        out = {}
        for key in keys:
            if key in full:
                out[key] = full[key]
        return json.dumps(out if out else full)

    def handle_blinker_json(data):
        if not isinstance(data, dict):
            return "ERR json type"
        ids = config.get("blinker", {})
        power_id = ids.get("power", "btn-0fh")
        screen_id = ids.get("screen", "btn-1hh")
        status_id = ids.get("status", "btn-7j2")
        fan_id = ids.get("fan", "ran-5hc")
        temp_id = ids.get("target_temperature", "ran-egl")
        if data.get("get") == "state":
            return blinker_state_json()
        if "rt" in data and isinstance(data.get("rt"), list):
            return blinker_partial_json(data.get("rt"))
        changed = []
        for key in data:
            low = str(key).lower()
            value = data[key]
            text = str(value).lower()
            if key == power_id or low in ("switch", "power", "pwr", "acfree", "ac_free"):
                climate.set_power(text in ("on", "true", "1", "tap", "press"))
                changed.append(power_id)
            elif key == screen_id:
                if text in ("tap", "press", "on", "1", "true"):
                    oled.wake()
                changed.append("tex-status")
            elif key == status_id:
                if text in ("tap", "press", "on", "1", "true"):
                    local_os.show_status()
                changed.append("tex-status")
            elif key == fan_id or (str(key).startswith("ran-") and float(value) <= 6):
                fan_value = int(float(value))
                if fan_value <= 1:
                    climate.set_fan_mode("fan_1")
                elif fan_value == 2:
                    climate.set_fan_mode("fan_2")
                elif fan_value == 3:
                    climate.set_fan_mode("fan_3")
                elif fan_value == 4:
                    climate.set_fan_mode("fan_4")
                elif fan_value == 5:
                    climate.set_fan_mode("fan_5")
                else:
                    climate.set_fan_mode("strong")
                changed.append(fan_id)
                changed.append("tex-status")
            elif key == temp_id or (str(key).startswith("ran-") and float(value) >= 18):
                climate.set_target_temperature(float(value))
                changed.append(temp_id)
            elif low in ("temp", "target", "target_temperature", "sp"):
                climate.set_target_temperature(float(value))
                changed.append(temp_id)
            elif low in ("tempup", "temp_up", "up"):
                climate.adjust_target_temperature(1)
            elif low in ("tempdown", "temp_down", "down"):
                climate.adjust_target_temperature(-1)
            elif low in ("fan", "fan_mode"):
                if text in ("1", "fan1", "fan_1"):
                    climate.set_fan_mode("fan_1")
                elif text in ("2", "fan2", "fan_2"):
                    climate.set_fan_mode("fan_2")
                elif text in ("3", "fan3", "fan_3"):
                    climate.set_fan_mode("fan_3")
                elif text in ("4", "fan4", "fan_4"):
                    climate.set_fan_mode("fan_4")
                elif text in ("5", "fan5", "fan_5"):
                    climate.set_fan_mode("fan_5")
                elif text in ("strong", "6"):
                    climate.set_fan_mode("strong")
            elif low == "strong":
                climate.set_fan_mode("strong")
            elif low in ("screen", "scr"):
                if text in ("on", "true", "1", "tap", "press"):
                    oled.wake()
                else:
                    oled.screen_off()
        save_config(config)
        return blinker_partial_json(changed)

    ble = None
    if config.get("ble", {}).get("enabled", True):
        ble = BleRemote("Blinker", web_state, handle_ble_command)
        ble.start()

    def on_button_short(idx):
        if oled.display and not oled.is_on():
            oled.wake()
            return
        if idx == 0:
            local_os.back()
        elif idx == 1:
            local_os.select()
        elif idx == 2:
            local_os.next()

    def on_button_long(idx):
        if oled.display and not oled.is_on():
            oled.wake()
            return
        if idx == 0:
            local_os.back()
        elif idx == 1:
            local_os.select()
        elif idx == 2:
            local_os.prev()

    buttons = None
    hardware = config.get("hardware", {})
    if hardware.get("buttons_enabled", True):
        buttons = Buttons(hardware.get("button_pins", [15, 4, 16]), on_button_short, on_button_long)

    started_ms = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        if buttons:
            buttons.poll()
        sensor.tick()
        climate_cfg = config.get("climate", {})
        control_avg_ms = int(climate_cfg.get("control_average_ms", 60000))
        direct_blow = sensor.rapid_drop_detected(
            int(climate_cfg.get("direct_blow_window_ms", 30000)),
            float(climate_cfg.get("direct_blow_drop_c", 1.5)),
        )
        climate.update(sensor.average_temperature(control_avg_ms), direct_blow)
        if setup_mode:
            web.poll()
        if ble:
            ble.tick(now)

        oled.update({
            "local_screen": local_os.screen({
                "mode": climate.mode,
                "time": local_time_text(config) if time_synced else "--:--",
                "temperature": fmt_number(sensor.average_temperature(), 1),
                "humidity": fmt_number(sensor.humidity, 0),
                "setup_url": setup_ip or "192.168.4.1",
                "status": climate.status,
            }),
            "setup": setup_mode,
            "ap_ssid": wifi.ap_ssid,
            "ap_pass": "yzc202657",
            "setup_url": setup_ip or "192.168.4.1",
            "mode": climate.mode,
            "time": local_time_text(config) if time_synced else "--:--",
            "temperature": fmt_number(sensor.average_temperature(), 1),
            "humidity": fmt_number(sensor.humidity, 0),
            "target": fmt_number(config.get("climate", {}).get("target_temperature", None), 1),
            "ir": "Strong",
            "wifi": wifi_status,
            "ble": "OK" if ble and ble.enabled else "--",
        })

        time.sleep_ms(10)


main()
