from machine import Pin, UART
import time

try:
    import ubinascii as binascii
except ImportError:
    import binascii

from src.utils import join_path, log


UART_ID = 1
UART_TX_PIN = 23
UART_RX_PIN = 22
UART_BAUDRATE = 9600
IR_CODES_DIR = "/ir_codes"
IRO5T_LEARN_CMD = b"\xFD\xFD\xF1\xF2\xDF"
IRO5T_FRAME_LEN = 236


class IrUart:
    def __init__(self, uart_id=UART_ID, tx_pin=UART_TX_PIN, rx_pin=UART_RX_PIN, baudrate=UART_BAUDRATE):
        log("ir", "UART id=" + str(uart_id) + " tx=GPIO" + str(tx_pin) + " rx=GPIO" + str(rx_pin))
        self.uart = UART(
            uart_id,
            baudrate=baudrate,
            tx=Pin(tx_pin),
            rx=Pin(rx_pin),
            timeout=100,
            timeout_char=50,
        )
        self.last_command = ""
        self.error = ""
        self._seq = None

    def load_binary(self, path):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as exc:
            self.error = "missing command " + path
            log("ir", self.error + ": " + str(exc))
            return None
        if not data:
            self.error = "empty command " + path
            log("ir", self.error)
            return None
        return data

    def send_payload(self, payload, command_name=""):
        if not payload:
            self.error = "empty payload"
            log("ir", self.error)
            return False
        try:
            self.uart.write(payload)
            time.sleep_ms(30)
            self._read_response()
            self.last_command = command_name
            self.error = ""
            return True
        except Exception as exc:
            self.error = "UART write failed"
            log("ir", self.error + ": " + str(exc))
            return False

    def _read_response(self):
        try:
            if self.uart.any():
                response = self.uart.read()
                if response:
                    log("ir", "module response " + str(binascii.hexlify(response[:32])))
        except Exception:
            pass

    def _drain(self):
        try:
            while self.uart.any():
                self.uart.read()
                time.sleep_ms(10)
        except Exception:
            pass

    def _read_exact(self, length, timeout_ms):
        started = time.ticks_ms()
        data = b""
        while time.ticks_diff(time.ticks_ms(), started) < timeout_ms:
            try:
                if self.uart.any():
                    part = self.uart.read()
                    if part:
                        data += part
                        if len(data) >= length:
                            return data[:length]
            except Exception as exc:
                self.error = "UART read failed: " + str(exc)
                return None
            time.sleep_ms(20)
        self.error = "learn timeout, got " + str(len(data)) + " bytes"
        return None

    def learn_iro5t(self, timeout_ms=15000):
        self._seq = None
        self._drain()
        log("ir", "IRO5T learn start")
        try:
            self.uart.write(IRO5T_LEARN_CMD)
        except Exception as exc:
            self.error = "learn command failed: " + str(exc)
            log("ir", self.error)
            return None
        frame = self._read_exact(IRO5T_FRAME_LEN, timeout_ms)
        if not frame:
            log("ir", self.error)
            return None
        if len(frame) != IRO5T_FRAME_LEN:
            self.error = "bad learn length " + str(len(frame))
            log("ir", self.error)
            return None
        self.error = ""
        log("ir", "IRO5T learned " + str(len(frame)) + " bytes")
        return frame

    def learn_to_file(self, path, timeout_ms=15000):
        frame = self.learn_iro5t(timeout_ms)
        if frame is None:
            return False
        try:
            with open(path, "wb") as f:
                f.write(frame)
            self.last_command = "learn:" + path
            return True
        except OSError as exc:
            self.error = "save failed: " + str(exc)
            log("ir", self.error)
            return False

    def send_file(self, path, command_name=""):
        payload = self.load_binary(path)
        if payload is None:
            return False
        return self.send_payload(payload, command_name)

    def send_by_name(self, name):
        return self.send_file(legacy_command_path(name), name)

    def start_sequence(self, paths, names=None, gap_ms=180):
        self._seq = {
            "paths": paths,
            "names": names or paths,
            "idx": 0,
            "gap_ms": gap_ms,
            "next_ms": time.ticks_ms(),
        }

    def tick(self):
        if not self._seq:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._seq["next_ms"]) < 0:
            return
        idx = self._seq["idx"]
        paths = self._seq["paths"]
        if idx >= len(paths):
            self._seq = None
            return
        name = self._seq["names"][idx]
        self.send_file(paths[idx], name)
        idx += 1
        if idx >= len(paths):
            self._seq = None
        else:
            self._seq["idx"] = idx
            self._seq["next_ms"] = now + int(self._seq["gap_ms"])

    def busy(self):
        return self._seq is not None


def from_config(config):
    hardware = config.get("hardware", {})
    return IrUart(
        uart_id=int(hardware.get("ir_uart_id", UART_ID)),
        tx_pin=int(hardware.get("ir_tx_pin", UART_TX_PIN)),
        rx_pin=int(hardware.get("ir_rx_pin", UART_RX_PIN)),
        baudrate=int(hardware.get("ir_baudrate", UART_BAUDRATE)),
    )


def legacy_command_path(filename):
    if not filename.endswith(".bin"):
        filename += ".bin"
    return join_path(IR_CODES_DIR, filename)
