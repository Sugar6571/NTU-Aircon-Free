try:
    import bluetooth
except ImportError:
    bluetooth = None

try:
    import ujson as json
except ImportError:
    import json
import gc
import time

from src.utils import log


IRQ_CENTRAL_CONNECT = 1
IRQ_CENTRAL_DISCONNECT = 2
IRQ_GATTS_WRITE = 3

SERVICE_UUID = 0xFFE0
DATA_UUID = 0xFFE1


HEX_COMMANDS = {
    0x00: "POWER OFF",
    0x01: "POWER ON",
    0x02: "FAN fan_1",
    0x03: "FAN fan_2",
    0x04: "FAN fan_3",
    0x05: "FAN fan_4",
    0x06: "FAN fan_5",
    0x07: "FAN strong",
    0x10: "TEMP_DELTA -1",
    0x11: "TEMP_DELTA 1",
    0x12: "SCREEN ON",
    0x13: "SCREEN OFF",
    0x20: "STATUS",
}


def _hex_command(byte_value):
    if byte_value in HEX_COMMANDS:
        return HEX_COMMANDS[byte_value]
    if 0x30 <= byte_value <= 0x3E:
        return "TEMP " + str(18 + byte_value - 0x30)
    return None


def _looks_like_ascii_command(command):
    upper = command.upper()
    return (
        upper.startswith("POWER ")
        or upper.startswith("MODE ")
        or upper.startswith("TEMP ")
        or upper.startswith("TEMP_DELTA ")
        or upper.startswith("FAN ")
        or upper.startswith("SCREEN ")
        or upper == "STATUS"
    )


def _advertising_payload(name, ble=None):
    payload = bytearray()
    payload += bytes((2, 0x01, 0x06))
    name_bytes = name.encode()
    payload += bytes((len(name_bytes) + 1, 0x09)) + name_bytes
    payload += bytes((3, 0x03, SERVICE_UUID & 0xFF, (SERVICE_UUID >> 8) & 0xFF))
    mfr = _manufacturer_data(ble)
    if mfr:
        payload += bytes((len(mfr) + 1, 0xFF)) + mfr
    return payload


def _manufacturer_data(ble=None):
    try:
        if ble is None:
            return b"HM000000"
        mac = ble.config("mac")[1]
        return b"HM" + mac
    except Exception:
        return b"HM000000"


class BleRemote:
    def __init__(self, name, get_state, handle_command):
        self.name = name or "Blinker"
        self.get_state = get_state
        self.handle_command = handle_command
        self.ble = None
        self.status_handle = None
        self.data_handle = None
        self.conn_handle = None
        self.enabled = False
        self.last_notify_ms = 0
        self.error = ""
        self.pending_command = None
        self.restart_advertise = False
        self.sync_status = False
        self.sync_queue = None

    def start(self):
        if bluetooth is None:
            self.error = "bluetooth module missing"
            log("ble", self.error)
            return False
        try:
            gc.collect()
            time.sleep_ms(500)
            log("ble", "init")
            self.ble = bluetooth.BLE()
            log("ble", "active on")
            self.ble.active(True)
            try:
                self.ble.config(gap_name=self.name)
                log("ble", "gap name " + self.name)
            except Exception as exc:
                log("ble", "gap name skipped: " + str(exc))
            log("ble", "irq")
            self.ble.irq(self._irq)
            flags_write = bluetooth.FLAG_WRITE
            try:
                flags_write |= bluetooth.FLAG_WRITE_NO_RESPONSE
            except AttributeError:
                pass
            log("ble", "register services")
            service = (
                bluetooth.UUID(SERVICE_UUID),
                (
                    (bluetooth.UUID(DATA_UUID), bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY | flags_write),
                ),
            )
            ((self.data_handle,),) = self.ble.gatts_register_services((service,))
            self.status_handle = self.data_handle
            log("ble", "write status")
            self._write_status()
            log("ble", "advertise")
            self._advertise()
            self.enabled = True
            log("ble", "advertising " + self.name + " service=0xFFE0 data=0xFFE1")
            return True
        except Exception as exc:
            self.error = str(exc)
            log("ble", "start failed: " + self.error)
            self.enabled = False
            return False

    def _advertise(self):
        payload = _advertising_payload(self.name, self.ble)
        try:
            self.ble.gap_advertise(100000, adv_data=payload, resp_data=payload)
        except TypeError:
            self.ble.gap_advertise(100000, payload)

    def _irq(self, event, data):
        if event == IRQ_CENTRAL_CONNECT:
            self.conn_handle = data[0]
            log("ble", "connected")
            self.sync_status = True
        elif event == IRQ_CENTRAL_DISCONNECT:
            self.conn_handle = None
            log("ble", "disconnected")
            self.restart_advertise = True
            self.sync_queue = None
        elif event == IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            if attr_handle == self.data_handle:
                self._read_pending_command()

    def _read_pending_command(self):
        try:
            raw = self.ble.gatts_read(self.data_handle)
            if len(raw) == 1:
                command = _hex_command(raw[0])
                if command is None:
                    return
            else:
                command = raw.decode().strip()
                if not command.startswith("{") and not _looks_like_ascii_command(command):
                    return
        except Exception as exc:
            self.error = str(exc)
            return
        if not command:
            return
        self.pending_command = command

    def _process_pending_command(self):
        command = self.pending_command
        self.pending_command = None
        if not command:
            return
        if command == "__STATE__":
            try:
                result = self.handle_command('{"get":"state"}')
                if result:
                    log("ble", result)
                    self._write_text(result)
            except Exception as exc:
                self.error = str(exc)
            return
        log("ble", "cmd " + command)
        try:
            result = self.handle_command(command)
            if result:
                log("ble", result)
                self._write_text(result)
        except Exception as exc:
            self.error = str(exc)
            log("ble", "command error: " + self.error)
            self._write_status()

    def _compact_status(self):
        try:
            state = self.get_state()
        except Exception as exc:
            return {"st": "state error", "err": str(exc)}
        return {
            "m": state.get("mode", ""),
            "t": state.get("temperature", "--"),
            "avg": state.get("temperature_avg", "--"),
            "h": state.get("humidity", "--"),
            "sp": state.get("target_temperature", "--"),
            "fan": state.get("fan_mode", ""),
            "cool": 1 if state.get("active_cooling", False) else 0,
            "ir": state.get("ir_send_count", 0),
            "st": state.get("status", ""),
        }

    def _write_status(self):
        if not self.ble or self.data_handle is None:
            return
        try:
            self.ble.gatts_write(self.data_handle, json.dumps(self._compact_status()))
        except Exception as exc:
            self.error = str(exc)

    def _write_text(self, text):
        if not self.ble or self.data_handle is None:
            return
        try:
            data = (str(text) + "\n").encode()
            if self.conn_handle is None:
                self.ble.gatts_write(self.data_handle, data)
                return
            pos = 0
            while pos < len(data):
                chunk = data[pos:pos + 20]
                self.ble.gatts_write(self.data_handle, chunk)
                try:
                    self.ble.gatts_notify(self.conn_handle, self.data_handle)
                except Exception:
                    pass
                pos += 20
                time.sleep_ms(5)
        except Exception as exc:
            self.error = str(exc)

    def _notify(self):
        if not self.ble or self.data_handle is None or self.conn_handle is None:
            return
        try:
            self.ble.gatts_notify(self.conn_handle, self.data_handle)
        except Exception:
            pass

    def tick(self, now_ms):
        if not self.enabled:
            return
        if self.pending_command:
            self._process_pending_command()
        if self.restart_advertise:
            self.restart_advertise = False
            try:
                self._advertise()
            except Exception as exc:
                self.error = str(exc)
                log("ble", "advertise restart failed: " + self.error)
        if self.sync_status:
            self.sync_status = False
            self.sync_queue = [
                '{"rt":["btn-0fh"]}',
                '{"rt":["ran-5hc"]}',
                '{"rt":["ran-egl"]}',
                '{"rt":["num-d2v","num-m74"]}',
                '{"rt":["tex-status"]}',
            ]
        if self.sync_queue:
            command = self.sync_queue.pop(0)
            try:
                result = self.handle_command(command)
                if result:
                    log("ble", result)
                    self._write_text(result)
            except Exception as exc:
                self.error = str(exc)
                log("ble", "sync failed: " + self.error)
            time.sleep_ms(80)
        # Blinker expects component JSON responses, for example:
        # {"btn-xxx":{"switch":"on"}} or {"ran-xxx":{"value":3}}.
        # Do not push the internal compact status periodically here; it can be
        # interpreted as an unrelated message by the app and delay widget sync.
