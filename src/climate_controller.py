import time


MODE_OFF = "off"
MODE_AC_FREE = "ac_free"
TEMP_MIN_C = 18.0
TEMP_MAX_C = 32.0


class ClimateController:
    def __init__(self, config, ir, command_path):
        self.config = config
        self.ir = ir
        self.command_path = command_path
        climate = config.get("climate", {})
        self.mode = self._normalize_mode(climate.get("mode", MODE_AC_FREE))
        self.power = self.mode == MODE_AC_FREE
        self.active_cooling = False
        self.last_keepalive_ms = 0
        self.status = "boot"
        self.error = ""
        self.missing_fan = False
        self.last_debug_ms = 0
        self.send_count = 0

    def _debug(self, message, min_interval_ms=2000):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_debug_ms) >= min_interval_ms:
            self.last_debug_ms = now
            print("[AC-FREE] " + message)

    def _normalize_mode(self, mode):
        if mode in ("on", "ON", "emergency", "emergency_keepalive", MODE_AC_FREE):
            return MODE_AC_FREE
        return MODE_OFF

    def save_runtime_to_config(self):
        self.config["climate"]["mode"] = self.mode

    def set_mode(self, mode):
        self.mode = self._normalize_mode(mode)
        self.power = self.mode == MODE_AC_FREE
        if not self.power:
            self.active_cooling = False
        self.status = "AC-FREE" if self.power else "off"
        self.save_runtime_to_config()

    def set_power(self, on):
        self.set_mode(MODE_AC_FREE if on else MODE_OFF)

    def set_target_temperature(self, value):
        value = float(value)
        if value < TEMP_MIN_C:
            value = TEMP_MIN_C
        if value > TEMP_MAX_C:
            value = TEMP_MAX_C
        self.config["climate"]["target_temperature"] = value

    def adjust_target_temperature(self, delta):
        current = self.config.get("climate", {}).get("target_temperature", 25.0)
        self.set_target_temperature(float(current) + delta)

    def set_hysteresis(self, value):
        value = float(value)
        self.config["climate"]["hysteresis_upper"] = value
        self.config["climate"]["hysteresis_lower"] = value

    def set_keepalive_interval_seconds(self, value):
        self.config["climate"]["emergency_interval_ms"] = int(float(value) * 1000)

    def set_fan_mode(self, fan_mode):
        if fan_mode not in ("fan_1", "fan_2", "fan_3", "fan_4", "fan_5", "strong"):
            self.status = "bad fan " + str(fan_mode)
            return
        self.config["climate"]["fan_mode"] = fan_mode
        self.status = "fan strong" if fan_mode == "strong" else "fan " + fan_mode[-1]

    def adjust_fan_mode(self, delta):
        modes = ("fan_1", "fan_2", "fan_3", "fan_4", "fan_5", "strong")
        current = self.config.get("climate", {}).get("fan_mode", "fan_1")
        try:
            idx = modes.index(current)
        except ValueError:
            idx = 0
        idx = (idx + delta) % len(modes)
        self.set_fan_mode(modes[idx])

    def _current_ir_path(self):
        fan_mode = self.config.get("climate", {}).get("fan_mode", "fan_1")
        path = self.command_path(fan_mode)
        if path:
            self.missing_fan = False
            return path, fan_mode
        fallback = self.command_path("strong")
        self.missing_fan = True
        return fallback, "strong"

    def _should_send_for_temperature(self, current_temperature, direct_blow=False):
        if current_temperature is None:
            self.status = "wait sensor"
            self._debug("WAIT SENSOR, no IR")
            return False
        climate = self.config.get("climate", {})
        target = float(climate.get("target_temperature", 25.0))
        upper = target + float(climate.get("hysteresis_upper", 0.5))
        lower_window = float(climate.get("hysteresis_lower", 1.0))
        if direct_blow:
            lower_window = float(climate.get("direct_blow_hysteresis_lower", 2.0))
        lower = target - lower_window
        if self.active_cooling:
            if current_temperature <= lower:
                self.active_cooling = False
                self.status = "idle temp ok"
                self._debug("TEMP LOW, no IR avg=" + str(current_temperature))
                return False
            return True
        if current_temperature >= upper:
            self.active_cooling = True
            return True
        self.status = "idle temp ok"
        self._debug("TEMP IDLE, no IR avg=" + str(current_temperature))
        return False

    def send_keepalive_once(self):
        path, label = self._current_ir_path()
        if not path:
            self.status = "missing IR"
            self._debug("MISSING IR, no send")
            return False
        if self.ir.send_file(path, label):
            self.last_keepalive_ms = time.ticks_ms()
            self.send_count += 1
            self.status = "AC-FREE " + label
            if self.missing_fan:
                self.status = "fallback strong"
            print("[AC-FREE] IR SEND #{} 800ms {}".format(self.send_count, label))
            return True
        self.status = self.ir.error
        return False

    def update(self, current_temperature=None, direct_blow=False):
        self.ir.tick()
        if self.mode != MODE_AC_FREE:
            self.power = False
            self.active_cooling = False
            self.status = "off"
            return

        self.power = True
        if not self._should_send_for_temperature(current_temperature, direct_blow):
            return

        interval = int(self.config.get("climate", {}).get("emergency_interval_ms", 800))
        if interval != 800:
            interval = 800
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_keepalive_ms) >= interval and not self.ir.busy():
            self.send_keepalive_once()
