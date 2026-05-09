try:
    import ujson as json
except ImportError:
    import json


CONFIG_PATH = "/config.json"
RESET_FLAG_PATH = "/reset_config.txt"


DEFAULT_CONFIG = {
    "device_name": "ntu_ac_controller",
    "timezone_offset_hours": 8,
    "hardware": {
        "board": "esp32",
        "ir_uart_id": 1,
        "ir_tx_pin": 23,
        "ir_rx_pin": 22,
        "ir_baudrate": 9600,
        "dht_pin": 17,
        "oled_spi_id": 2,
        "oled_sck_pin": 5,
        "oled_mosi_pin": 18,
        "oled_res_pin": 19,
        "oled_dc_pin": 21,
        "button_pins": [15, 4, 16],
        "buttons_enabled": True
    },
    "wifi": {"ssid": "", "password": ""},
    "setup": {"skip_wifi": False, "ap_password": "yzc202657"},
    "climate": {
        "target_temperature": 25.0,
        "hysteresis_upper": 0.5,
        "hysteresis_lower": 1.0,
        "direct_blow_hysteresis_lower": 2.0,
        "direct_blow_drop_c": 1.5,
        "direct_blow_window_ms": 30000,
        "control_average_ms": 60000,
        "minimum_on_ms": 180000,
        "minimum_off_ms": 180000,
        "mode": "ac_free",
        "fan_mode": "fan_1",
    },
    "display": {"screen_timeout_ms": 50000, "enabled": True},
    "web": {"enabled": True, "diagnostic_only": True},
    "ble": {"enabled": True, "name": "Blinker"},
    "blinker": {
        "power": "btn-0fh",
        "screen": "btn-1hh",
        "status": "btn-7j2",
        "fan": "ran-5hc",
        "target_temperature": "ran-egl",
        "current_temperature": "num-d2v",
        "humidity": "num-m74",
    },
    "ir": {"profile": "default", "fallback_command": "strong"},
}


def _merge(defaults, loaded):
    result = {}
    for key in defaults:
        if key in loaded:
            if isinstance(defaults[key], dict) and isinstance(loaded[key], dict):
                result[key] = _merge(defaults[key], loaded[key])
            else:
                result[key] = loaded[key]
        else:
            result[key] = defaults[key]
    for key in loaded:
        if key not in result:
            result[key] = loaded[key]
    return result


def load_config(path=CONFIG_PATH):
    if reset_requested():
        return DEFAULT_CONFIG
    try:
        with open(path, "r") as f:
            loaded = json.loads(f.read())
        config = _merge(DEFAULT_CONFIG, loaded)
        _migrate(config)
        return config
    except OSError:
        config = DEFAULT_CONFIG
        _migrate(config)
        return config
    except ValueError:
        config = DEFAULT_CONFIG
        _migrate(config)
        return config


def _migrate(config):
    setup = config.setdefault("setup", {})
    setup.setdefault("skip_wifi", False)
    setup.setdefault("ap_password", "yzc202657")

    climate = config.setdefault("climate", {})
    climate.setdefault("target_temperature", 25.0)
    climate.setdefault("fan_mode", "strong")

    ble = config.setdefault("ble", {})
    ble.setdefault("enabled", True)
    ble.setdefault("name", "Blinker")

    blinker = config.setdefault("blinker", {})
    blinker.setdefault("target_temperature", "ran-egl")
    blinker.setdefault("fan", "ran-5hc")
    blinker.setdefault("power", "btn-0fh")
    blinker.setdefault("screen", "btn-1hh")
    blinker.setdefault("status", "btn-7j2")
    blinker.setdefault("current_temperature", "num-d2v")
    blinker.setdefault("humidity", "num-m74")


def save_config(config, path=CONFIG_PATH):
    with open(path, "w") as f:
        f.write(json.dumps(config))


def config_missing_wifi(config):
    wifi = config.get("wifi", {})
    return not wifi.get("ssid")


def get_hardware(config):
    return config.get("hardware", DEFAULT_CONFIG["hardware"])


def reset_requested(path=RESET_FLAG_PATH):
    try:
        with open(path, "r"):
            return True
    except OSError:
        return False
