from machine import Pin
import time


DEBOUNCE_MS = 20
LONG_PRESS_MS = 400


class Buttons:
    def __init__(self, pins, on_short, on_long):
        self.buttons = [Pin(pin, Pin.IN, Pin.PULL_UP) for pin in pins]
        self.on_short = on_short
        self.on_long = on_long
        self.prev = [1] * len(self.buttons)
        self.pending = [None] * len(self.buttons)
        self.last_change = [0] * len(self.buttons)
        self.press_t0 = [None] * len(self.buttons)

    def poll(self):
        now = time.ticks_ms()
        for i, button in enumerate(self.buttons):
            value = button.value()
            if self.pending[i] is None:
                if value != self.prev[i]:
                    self.pending[i] = value
                    self.last_change[i] = now
            else:
                if value != self.pending[i]:
                    self.pending[i] = None
                elif time.ticks_diff(now, self.last_change[i]) >= DEBOUNCE_MS:
                    old = self.prev[i]
                    self.prev[i] = self.pending[i]
                    self.pending[i] = None
                    if old == 1 and self.prev[i] == 0:
                        self.press_t0[i] = now
                    elif old == 0 and self.prev[i] == 1:
                        duration = time.ticks_diff(now, self.press_t0[i] or now)
                        if duration >= LONG_PRESS_MS:
                            self.on_long(i)
                        else:
                            self.on_short(i)
                        self.press_t0[i] = None
