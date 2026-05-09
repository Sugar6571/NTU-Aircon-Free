import time


def log(tag, message):
    print("[" + tag + "] " + str(message))


def join_path(a, b):
    if a.endswith("/"):
        return a + b
    return a + "/" + b


def ticks_now():
    return time.ticks_ms()


def ticks_elapsed(start, interval_ms):
    return time.ticks_diff(time.ticks_ms(), start) >= interval_ms


def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value
