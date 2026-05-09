import network
import time


class WifiManager:
    def __init__(self, device_name="ntu_ac_controller", ap_password="yzc202657"):
        self.device_name = device_name
        self.sta = network.WLAN(network.STA_IF)
        self.ap = network.WLAN(network.AP_IF)
        self.ap_ssid = "AC-SETUP"
        self.ap_password = ap_password

    def connect(self, ssid, password, timeout_ms=20000):
        self.sta.active(True)
        if not self.sta.isconnected():
            self.sta.connect(ssid, password)
        started = time.ticks_ms()
        while not self.sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), started) > timeout_ms:
                return False
            time.sleep_ms(250)
        return True

    def start_ap(self, password=None):
        self.ap_ssid = "AC-SETUP"
        if password is None:
            password = self.ap_password
        self.ap_password = password
        try:
            self.ap.active(False)
            time.sleep_ms(200)
        except Exception:
            pass
        self.ap.active(True)
        try:
            self.ap.config(
                essid=self.ap_ssid,
                password=password,
                authmode=network.AUTH_WPA_WPA2_PSK,
                channel=6,
                hidden=False,
            )
        except Exception:
            try:
                self.ap.config(essid=self.ap_ssid, password=password, channel=6)
            except Exception:
                self.ap.config(essid=self.ap_ssid)
        time.sleep_ms(300)
        print("[WiFi] AP active=" + str(self.ap.active()) + " ssid=" + self.ap_ssid + " ip=" + str(self.ap.ifconfig()[0]))
        return self.ap.ifconfig()[0]

    def ap_is_active(self):
        return self.ap.active()

    def is_connected(self):
        return self.sta.active() and self.sta.isconnected()

    def rssi(self):
        try:
            return self.sta.status("rssi")
        except Exception:
            return None

    def stop_all(self):
        try:
            self.ap.active(False)
        except Exception:
            pass
        try:
            if self.sta.isconnected():
                self.sta.disconnect()
        except Exception:
            pass
        try:
            self.sta.active(False)
        except Exception:
            pass
