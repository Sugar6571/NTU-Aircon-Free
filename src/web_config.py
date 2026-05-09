import socket

try:
    import ujson as json
except ImportError:
    import json

from src.utils import log


def _url_decode(value):
    value = value.replace("+", " ")
    parts = value.split("%")
    out = parts[0]
    for part in parts[1:]:
        if len(part) >= 2:
            try:
                out += chr(int(part[:2], 16)) + part[2:]
            except ValueError:
                out += "%" + part
        else:
            out += "%" + part
    return out


def _escape_attr(value):
    return str(value).replace("&", "&amp;").replace("'", "&#39;").replace('"', "&quot;")


def _escape_text(value):
    return _escape_attr(value).replace("<", "&lt;").replace(">", "&gt;")


def _parse_form(body):
    data = {}
    for pair in body.split("&"):
        if not pair:
            continue
        bits = pair.split("=", 1)
        if len(bits) == 2:
            data[_url_decode(bits[0])] = _url_decode(bits[1])
    return data


def _parse_request(raw):
    head, body = raw.split("\r\n\r\n", 1) if "\r\n\r\n" in raw else (raw, "")
    lines = head.split("\r\n")
    first = lines[0].split()
    method = first[0] if len(first) > 0 else "GET"
    target = first[1] if len(first) > 1 else "/"
    return method, target, body


def _split_target(target):
    if "?" in target:
        path, query = target.split("?", 1)
        return path, _parse_form(query)
    return target, {}


def _response(body, content_type="text/html"):
    return (
        "HTTP/1.0 200 OK\r\nContent-Type: "
        + content_type
        + "\r\nConnection: close\r\n\r\n"
        + body
    )


def _json_response(data):
    return _response(json.dumps(data), "application/json")


def _redirect(path):
    return "HTTP/1.0 303 See Other\r\nLocation: " + path + "\r\nConnection: close\r\n\r\n"


def _no_content():
    return "HTTP/1.0 204 No Content\r\nConnection: close\r\n\r\n"


def _html_page(title, body):
    return _response(
        "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>" + title + "</title>"
        "<style>"
        "body{font-family:sans-serif;margin:0;background:#101418;color:#eef3f7}"
        "main{max-width:560px;margin:auto;padding:14px}.card{background:#182028;border:1px solid #2b3844;border-radius:8px;padding:12px;margin:10px 0}"
        "h1{font-size:22px;margin:8px 0}.time{font-size:58px;line-height:1;font-weight:bold;text-align:center}"
        ".muted{color:#9fb0bf;font-size:13px}input{width:100%;box-sizing:border-box;border-radius:6px;border:1px solid #354554;background:#0f1419;color:#fff;padding:10px}"
        "label{display:block;margin:10px 0}button{border:0;border-radius:8px;padding:12px 14px;margin:4px 0;background:#1d8f6f;color:#fff;font-weight:bold}"
        "button.secondary{background:#2b3a46}a{color:#72c8ff}"
        "</style></head><body><main>"
        + body
        + "</main></body></html>"
    )


def _send_all(conn, response):
    if isinstance(response, str):
        response = response.encode()
    pos = 0
    length = len(response)
    while pos < length:
        try:
            sent = conn.send(response[pos:pos + 256])
        except OSError:
            break
        if not sent:
            break
        pos += sent


class WebConfigServer:
    def __init__(self, config, save_config, get_state=None):
        self.config = config
        self.save_config = save_config
        self.get_state = get_state
        self.sock = None
        self.error = ""

    def start(self, port=80):
        try:
            self.sock = socket.socket()
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            self.sock.bind(("0.0.0.0", port))
            self.sock.listen(1)
            self.sock.settimeout(0)
            log("web", "listening on :" + str(port))
            return True
        except Exception as exc:
            self.error = str(exc)
            log("web", "start failed: " + self.error)
            return False

    def poll(self):
        if not self.sock:
            return
        try:
            conn, _addr = self.sock.accept()
        except Exception:
            return
        try:
            conn.settimeout(0)
            try:
                raw_bytes = conn.recv(1024)
            except OSError:
                raw_bytes = b""
            if not raw_bytes:
                try:
                    conn.close()
                except Exception:
                    pass
                return
            method, target, body = _parse_request(raw_bytes.decode())
            log("web", method + " " + target)
            _send_all(conn, self.handle(method, target, body))
        except Exception as exc:
            try:
                log("web", "request error: " + str(exc))
                _send_all(conn, _response("Error: " + str(exc), "text/plain"))
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass

    def handle(self, method, target, body):
        path, _query = _split_target(target)
        if path == "/favicon.ico":
            return _no_content()
        if path == "/api/status":
            return _json_response(self._state())
        if path == "/save" and method == "POST":
            return self.save_settings(body)
        if path == "/skip_wifi" and method == "POST":
            self.config["setup"]["skip_wifi"] = True
            self.save_config(self.config)
            return _redirect("/")
        return self.index_page()

    def _state(self):
        if self.get_state:
            try:
                return self.get_state()
            except Exception:
                pass
        return {"time": "--:--", "wifi": "--", "ip": "192.168.4.1"}

    def index_page(self):
        wifi = self.config.get("wifi", {})
        state = self._state()
        body = (
            "<h1>AC-FREE Setup</h1>"
            "<div class='card'><b>Time</b><div class='time'>" + _escape_text(state.get("time", "--:--")) + "</div>"
            "<p class='muted'>Wi-Fi is only used for NTP time display. AC control uses OLED buttons and Blinker BLE.</p></div>"
            "<div class='card'><b>Wi-Fi</b><p>Status: " + _escape_text(state.get("wifi", "--")) + "</p>"
            "<p>IP: " + _escape_text(state.get("ip", "192.168.4.1")) + "</p><p>2.4GHz only.</p></div>"
            "<div class='card'><b>Provisioning</b><form method='POST' action='/save'>"
            "<label>Device name<input name='device_name' value='" + _escape_attr(self.config.get("device_name", "")) + "'></label>"
            "<label>Wi-Fi SSID<input name='ssid' value='" + _escape_attr(wifi.get("ssid", "")) + "'></label>"
            "<label>Wi-Fi password<input name='wifi_password' type='password' value='" + _escape_attr(wifi.get("password", "")) + "'></label>"
            "<button type='submit'>Save Wi-Fi</button></form>"
            "<form method='POST' action='/skip_wifi'><button class='secondary' type='submit'>Skip Wi-Fi</button></form>"
            "<p class='muted'>After saving Wi-Fi, reboot the ESP32.</p></div>"
        )
        return _html_page("AC-FREE Setup", body)

    def save_settings(self, body):
        form = _parse_form(body)
        self.config["device_name"] = form.get("device_name", self.config.get("device_name", "ntu_ac_controller"))
        self.config["wifi"]["ssid"] = form.get("ssid", "")
        self.config["wifi"]["password"] = form.get("wifi_password", "")
        self.config["setup"]["skip_wifi"] = False
        self.save_config(self.config)
        return _html_page("Saved", "<h1>Saved</h1><p>Reboot ESP32 to use the new Wi-Fi settings.</p><p><a href='/'>Back</a></p>")
