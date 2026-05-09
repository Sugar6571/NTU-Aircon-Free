import os

from src.climate_controller import MODE_AC_FREE, MODE_OFF
from src.ir_profiles import ensure_profile, set_command, profile_dir
from src.utils import join_path


FAN_MODES = ("fan_1", "fan_2", "fan_3", "fan_4", "fan_5", "strong")

HOME_ITEMS = (
    ("Status", "status"),
    ("AC-FREE", "ac_free"),
    ("Set Temp", "temp"),
    ("Set Fan", "fan"),
    ("IR Learn", "learn"),
    ("WiFi Setup", "wifi"),
)

LEARN_ITEMS = (
    ("Fan 1", "fan_1"),
    ("Fan 2", "fan_2"),
    ("Fan 3", "fan_3"),
    ("Fan 4", "fan_4"),
    ("Fan 5", "fan_5"),
    ("Strong", "strong"),
)


class LocalOs:
    def __init__(self, config, save_config, climate, oled):
        self.config = config
        self.save_config = save_config
        self.climate = climate
        self.oled = oled
        self.page = "home"
        self.home_index = 0
        self.learn_index = 0

    def open_wifi_setup(self):
        self.page = "wifi"
        self.home_index = 5
        self._wake()

    def show_status(self):
        self.page = "status"
        self._wake()

    def _wake(self):
        self.oled.wake()

    def next(self):
        if self.page == "home":
            self.home_index = (self.home_index + 1) % len(HOME_ITEMS)
        elif self.page == "temp":
            self.climate.adjust_target_temperature(1)
            self.save_config(self.config)
        elif self.page == "fan":
            self.climate.adjust_fan_mode(1)
            self.save_config(self.config)
        elif self.page == "learn":
            self.learn_index = (self.learn_index + 1) % len(LEARN_ITEMS)
        self._wake()

    def prev(self):
        if self.page == "home":
            self.home_index = (self.home_index - 1) % len(HOME_ITEMS)
        elif self.page == "temp":
            self.climate.adjust_target_temperature(-1)
            self.save_config(self.config)
        elif self.page == "fan":
            self.climate.adjust_fan_mode(-1)
            self.save_config(self.config)
        elif self.page == "learn":
            self.learn_index = (self.learn_index - 1) % len(LEARN_ITEMS)
        self._wake()

    def back(self):
        if self.page == "home":
            self.home_index = 0
        else:
            self.page = "home"
        self._wake()

    def idle_before_screen_off(self):
        if self.page == "home":
            self.page = "status"
        return self.page

    def select(self):
        self._wake()
        if self.page == "home":
            _label, action = HOME_ITEMS[self.home_index]
            if action == "status":
                self.page = "status"
            elif action == "ac_free":
                self.climate.set_mode(MODE_OFF if self.climate.mode == MODE_AC_FREE else MODE_AC_FREE)
                self.save_config(self.config)
            elif action in ("temp", "fan", "learn", "wifi"):
                self.page = action
            return

        if self.page == "learn":
            _label, command = LEARN_ITEMS[self.learn_index]
            self.learn(command)
        elif self.page == "wifi":
            self.config["setup"]["skip_wifi"] = True
            self.save_config(self.config)
            self.oled.render_lines(["WIFI SKIPPED", "Hardware only", "B1 Back"])

    def learn_label(self, command):
        if command == "strong":
            return "Strong"
        if command in FAN_MODES:
            return "18C Cool Fan " + command[-1]
        return command

    def learn(self, command):
        profile_name = self.config.get("ir", {}).get("profile", "default")
        filename = "strong.bin" if command == "strong" else "cool_18_" + command + ".bin"
        try:
            try:
                os.mkdir(profile_dir(profile_name))
            except OSError:
                pass
            path = join_path(profile_dir(profile_name), filename)
            old_mode = self.climate.mode
            self.climate.set_mode(MODE_OFF)
            self.oled.render_lines([
                "LEARN IR",
                self.learn_label(command),
                "Press remote",
                "Success replace",
                "Fail keeps old",
            ])
            ok = self.climate.ir.learn_to_file(path, 15000)
            self.climate.set_mode(old_mode)
            if ok:
                profile = ensure_profile(profile_name)
                set_command(profile_name, profile, command, filename, "Learned full-state 18C cool " + command)
                self.oled.render_lines(["LEARN OK", self.learn_label(command), "Saved", filename])
            else:
                self.oled.render_lines(["LEARN FAIL", self.learn_label(command), "Old kept", self.climate.ir.error[:16]])
        except Exception as exc:
            self.oled.render_lines(["LEARN ERROR", self.learn_label(command), "Old kept", str(exc)[:16]])

    def screen(self, runtime):
        mode = runtime.get("mode", "--")
        temp = str(self.config.get("climate", {}).get("target_temperature", 25.0))
        fan = self.config.get("climate", {}).get("fan_mode", "fan_1")
        fan_text = "Strong" if fan == "strong" else "Fan " + fan[-1]
        status = runtime.get("status", "")

        if self.page == "home":
            rows = []
            for label, action in HOME_ITEMS:
                if action == "ac_free":
                    label = "AC-FREE " + ("ON" if mode == MODE_AC_FREE else "OFF")
                rows.append(label)
            return {"rows": rows, "selected": self.home_index}

        if self.page == "status":
            return {"rows": [
                "AC-FREE " + ("ON" if mode == MODE_AC_FREE else "OFF"),
                "Room " + runtime.get("temperature", "--") + " C",
                "Set  " + temp + " C",
                fan_text,
                "IR   " + status[:10],
                "B1 Back",
            ], "selected": -1}

        if self.page == "temp":
            return {"rows": ["SET TEMP", temp + " C", "B3 +1", "Long B3 -1", "Min 18 C", "B1 Back"], "selected": 1}

        if self.page == "fan":
            return {"rows": ["SET FAN", fan_text, "B3 Next", "Long B3 Prev", "1-5 + Strong", "B1 Back"], "selected": 1}

        if self.page == "learn":
            start = 0
            if self.learn_index >= 5:
                start = self.learn_index - 4
            rows = ["LEARN IR"]
            for label, _command in LEARN_ITEMS[start:start + 5]:
                rows.append(label)
            return {"rows": rows, "selected": self.learn_index - start + 1}

        if self.page == "wifi":
            ap_password = self.config.get("setup", {}).get("ap_password", "yzc202657")
            return {"rows": [
                "WIFI SETUP",
                "SSID AC-SETUP",
                "Pass " + ap_password,
                runtime.get("setup_url", "192.168.4.1")[:16],
                "B2 Skip WiFi",
                "2.4GHz only",
            ], "selected": 4}

        return {"rows": ["AC-FREE OS", "B1 Back"], "selected": -1}
