from machine import Pin, SPI
import framebuf
import time


OLED_SCK = 5
OLED_MOSI = 18
OLED_RES = 19
OLED_DC = 21
OLED_SPI_ID = 2
OLED_CHIP = "SSD1306"


class RawOled:
    def __init__(self, config, width=128, height=64, baudrate=1000000):
        hardware = config.get("hardware", {})
        self.config = config
        self.w = width
        self.h = height
        self.pages = height // 8
        self.buf = bytearray(self.w * self.pages)
        self.fb = framebuf.FrameBuffer(self.buf, self.w, self.h, framebuf.MONO_VLSB)
        self.spi = SPI(
            int(hardware.get("oled_spi_id", OLED_SPI_ID)),
            baudrate=baudrate,
            polarity=0,
            phase=0,
            sck=Pin(int(hardware.get("oled_sck_pin", OLED_SCK))),
            mosi=Pin(int(hardware.get("oled_mosi_pin", OLED_MOSI))),
        )
        self.dc = Pin(int(hardware.get("oled_dc_pin", OLED_DC)), Pin.OUT, value=0)
        self.res = Pin(int(hardware.get("oled_res_pin", OLED_RES)), Pin.OUT, value=1)
        self.chip = config.get("display", {}).get("chip", OLED_CHIP)
        self.display_on = True
        self.last_wake_ms = time.ticks_ms()
        self._reset()
        if self.chip == "SH1106":
            self._init_sh1106()
        else:
            self._init_ssd1306()

    def _reset(self):
        self.res.value(0)
        time.sleep_ms(15)
        self.res.value(1)
        time.sleep_ms(15)

    def _cmd(self, byte):
        self.dc.value(0)
        self.spi.write(bytearray([byte & 0xFF]))

    def _init_ssd1306(self):
        for byte in [
            0xAE, 0x20, 0x00, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0,
            0x40, 0x8D, 0x14, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF,
            0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF,
        ]:
            self._cmd(byte)

    def _init_sh1106(self):
        for byte in [
            0xAE, 0xD5, 0x50, 0xA8, 0x3F, 0xD3, 0, 0x40, 0xAD,
            0x8B, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0x80, 0xA4, 0xA6,
            0xAF,
        ]:
            self._cmd(byte)

    def show(self):
        if self.chip == "SH1106":
            col_off = 2
            for page in range(self.pages):
                self._cmd(0xB0 | page)
                self._cmd(0x00 | (col_off & 0x0F))
                self._cmd(0x10 | ((col_off >> 4) & 0x0F))
                start = page * self.w
                end = start + self.w
                self.dc.value(1)
                self.spi.write(self.buf[start:end])
        else:
            self._cmd(0x21)
            self._cmd(0)
            self._cmd(self.w - 1)
            self._cmd(0x22)
            self._cmd(0)
            self._cmd(self.pages - 1)
            self.dc.value(1)
            self.spi.write(self.buf)

    def power_off(self):
        self._cmd(0xAE)
        self.display_on = False

    def power_on(self):
        self._cmd(0xAF)
        self.display_on = True
        self.last_wake_ms = time.ticks_ms()

    def wake(self):
        if not self.display_on:
            self.power_on()
        self.last_wake_ms = time.ticks_ms()


class OledUi:
    def __init__(self, config):
        self.config = config
        self.display = None
        self.error = ""
        self.last_render_ms = 0
        self.on_before_auto_off = None

    def init(self):
        try:
            self.display = RawOled(self.config)
            self.wake()
            return True
        except Exception as exc:
            self.display = None
            self.error = str(exc)
            return False

    def wake(self):
        if self.display:
            self.display.wake()

    def screen_off(self):
        if self.display:
            self.display.power_off()

    def is_on(self):
        return bool(self.display and self.display.display_on)

    def render_lines(self, lines):
        if not self.display:
            return
        self.wake()
        fb = self.display.fb
        fb.fill(0)
        y = 0
        for line in lines[:6]:
            fb.text(str(line)[:16], 0, y)
            y += 10
        self.display.show()
        self.last_render_ms = time.ticks_ms()

    def _draw_rows(self, rows, selected=-1):
        fb = self.display.fb
        y = 0
        for i, line in enumerate(rows[:6]):
            text = str(line)[:16]
            if i == selected:
                fb.fill_rect(0, y, self.display.w, 10, 1)
                fb.text(text, 0, y, 0)
            else:
                fb.text(text, 0, y, 1)
            y += 10

    def update(self, state):
        if not self.display:
            return
        now = time.ticks_ms()
        timeout = int(self.config.get("display", {}).get("screen_timeout_ms", 50000))
        if self.display.display_on and time.ticks_diff(now, self.display.last_wake_ms) > timeout:
            if self.on_before_auto_off:
                try:
                    self.on_before_auto_off()
                except Exception:
                    pass
            self.display.power_off()
            return
        if not self.display.display_on:
            return
        if time.ticks_diff(now, self.last_render_ms) < 1000:
            return
        self.last_render_ms = now

        fb = self.display.fb
        fb.fill(0)
        if state.get("local_screen"):
            screen = state.get("local_screen")
            self._draw_rows(screen.get("rows", []), int(screen.get("selected", -1)))
            self.display.show()
            return

        if state.get("setup"):
            fb.text("SETUP MODE", 0, 0)
            fb.text("WiFi: " + state.get("ap_ssid", "setup")[:10], 0, 12)
            fb.text("Pass: " + state.get("ap_pass", "yzc202657")[:10], 0, 24)
            fb.text("Open browser:", 0, 36)
            fb.text(state.get("setup_url", "192.168.4.1")[:16], 0, 48)
            self.display.show()
            return

        if state.get("local_lines"):
            self._draw_rows(state.get("local_lines", []), -1)
            self.display.show()
            return

        mode = state.get("mode", "off")
        if mode == "ac_free":
            fb.text("AC-FREE", 0, 0)
        else:
            fb.text("OFF", 0, 0)
        fb.text("Time " + state.get("time", "--:--"), 0, 12)
        fb.text("Temp " + state.get("temperature", "--") + " C", 0, 24)
        fb.text("Hum  " + state.get("humidity", "--") + " %", 0, 36)
        fb.text("IR " + state.get("ir", "Strong")[:10], 0, 48)
        fb.text("W:" + state.get("wifi", "-") + " B:" + state.get("ble", "-"), 72, 48)
        self.display.show()
