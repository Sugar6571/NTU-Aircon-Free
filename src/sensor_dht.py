from machine import Pin
import time


DHT_PIN = 17
SENSOR_PERIOD_MS = 2000
TEMP_HISTORY_MS = 90000
TEMP_AVG_MS = 60000


class DhtSensor:
    def __init__(self, pin=DHT_PIN):
        self.pin_no = pin
        self.temperature = None
        self.humidity = None
        self.error = ""
        self.last_read_ms = 0
        self.history = []
        self.impl = None
        try:
            import dht
            self.impl = dht.DHT11(Pin(pin))
            self.soft = False
        except Exception:
            self.soft = True
            self.pin = Pin(pin, Pin.OUT, Pin.PULL_UP)

    def _soft_read(self):
        import machine
        pin = self.pin
        pin.init(Pin.OUT, Pin.PULL_UP)
        pin.value(0)
        time.sleep_ms(20)
        pin.value(1)
        pin.init(Pin.IN, Pin.PULL_UP)
        if machine.time_pulse_us(pin, 0, 1000) < 0:
            return None
        if machine.time_pulse_us(pin, 1, 1000) < 0:
            return None
        bits = []
        for _ in range(40):
            if machine.time_pulse_us(pin, 0, 1000) < 0:
                return None
            pulse = machine.time_pulse_us(pin, 1, 2000)
            if pulse < 0:
                return None
            bits.append(1 if pulse > 50 else 0)
        data = [0, 0, 0, 0, 0]
        for i in range(40):
            data[i // 8] = (data[i // 8] << 1) | bits[i]
        if ((data[0] + data[1] + data[2] + data[3]) & 0xFF) != data[4]:
            return None
        return data[2], data[0]

    def read_now(self):
        try:
            if self.impl:
                self.impl.measure()
                result = (self.impl.temperature(), self.impl.humidity())
            else:
                result = self._soft_read()
        except Exception as exc:
            self.error = str(exc)
            return False

        if not result:
            self.error = "read failed"
            return False

        now = time.ticks_ms()
        self.temperature = float(result[0])
        self.humidity = float(result[1])
        self.error = ""
        self.history.append((now, self.temperature))
        while self.history and time.ticks_diff(now, self.history[0][0]) > TEMP_HISTORY_MS:
            self.history.pop(0)
        return True

    def tick(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_read_ms) >= SENSOR_PERIOD_MS:
            self.last_read_ms = now
            self.read_now()

    def average_temperature(self, window_ms=TEMP_AVG_MS):
        now = time.ticks_ms()
        values = []
        for ts, value in self.history:
            if time.ticks_diff(now, ts) <= window_ms:
                values.append(value)
        if values:
            total = 0
            for value in values:
                total += value
            return total / len(values)
        return self.temperature

    def rapid_drop_detected(self, window_ms=30000, drop_c=1.5):
        if len(self.history) < 2:
            return False
        now = time.ticks_ms()
        latest = self.history[-1][1]
        oldest = None
        for ts, value in self.history:
            if time.ticks_diff(now, ts) <= window_ms:
                oldest = value
                break
        if oldest is None:
            return False
        return (oldest - latest) >= drop_c


def from_config(config):
    hardware = config.get("hardware", {})
    return DhtSensor(pin=int(hardware.get("dht_pin", DHT_PIN)))
