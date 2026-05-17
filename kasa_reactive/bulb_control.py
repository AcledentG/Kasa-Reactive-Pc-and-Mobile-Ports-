"""
kasa_protocol.py
================

Minimal pure-Python Kasa IOT protocol with PERSISTENT TCP sockets.

The previous version opened a fresh socket for every set_hsv call,
which on wifi added 30-100ms of TCP handshake overhead per update.
This version keeps one long-lived socket per bulb and reuses it,
reconnecting transparently if it drops.

Also runs one worker thread per bulb, so slow bulbs don't block fast
ones. TCP_NODELAY disables Nagle's algorithm so small commands send
immediately instead of being buffered.
"""

from __future__ import annotations

import json
import socket
import struct
import threading
from dataclasses import dataclass
from typing import Optional


# ----------------------------------------------------------------------
# Encryption
# ----------------------------------------------------------------------
def _encrypt(payload: str) -> bytes:
    key = 171
    encrypted = bytearray()
    for char in payload.encode("utf-8"):
        key = key ^ char
        encrypted.append(key)
    return struct.pack(">I", len(encrypted)) + bytes(encrypted)


def _decrypt(data: bytes) -> str:
    if len(data) < 4:
        return ""
    payload = data[4:]
    key = 171
    decrypted = bytearray()
    for byte in payload:
        decrypted.append(key ^ byte)
        key = byte
    return decrypted.decode("utf-8", errors="replace")


# ----------------------------------------------------------------------
# One-shot commands (for discovery + initial connection)
# ----------------------------------------------------------------------
def _send_oneshot(ip: str, command: dict, timeout: float = 3.0) -> dict:
    payload = json.dumps(command)
    encrypted = _encrypt(payload)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((ip, 9999))
        sock.sendall(encrypted)
        length_bytes = sock.recv(4)
        if len(length_bytes) < 4:
            return {}
        length = struct.unpack(">I", length_bytes)[0]
        response_bytes = bytearray()
        while len(response_bytes) < length:
            chunk = sock.recv(min(4096, length - len(response_bytes)))
            if not chunk:
                break
            response_bytes.extend(chunk)
    decrypted = _decrypt(length_bytes + bytes(response_bytes))
    return json.loads(decrypted) if decrypted else {}


def get_info(ip: str, timeout: float = 3.0) -> dict:
    try:
        response = _send_oneshot(ip, {"system": {"get_sysinfo": {}}}, timeout)
        return response.get("system", {}).get("get_sysinfo", {})
    except Exception:
        return {}


def is_color_bulb(info: dict) -> bool:
    return bool(info.get("is_color", 0))


def turn_on_oneshot(ip: str, timeout: float = 2.0) -> bool:
    cmd = {
        "smartlife.iot.smartbulb.lightingservice": {
            "transition_light_state": {"on_off": 1, "ignore_default": 1}
        }
    }
    try:
        _send_oneshot(ip, cmd, timeout)
        return True
    except Exception:
        return False


def discover(timeout: float = 4.0) -> list[tuple[str, dict]]:
    discover_cmd = json.dumps({"system": {"get_sysinfo": {}}})
    encrypted = _encrypt(discover_cmd)
    udp_payload = encrypted[4:]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.sendto(udp_payload, ("255.255.255.255", 9999))
    except Exception:
        sock.close()
        return []

    results = []
    seen = set()
    import time as _time
    start = _time.monotonic()
    while _time.monotonic() - start < timeout:
        try:
            sock.settimeout(0.5)
            data, addr = sock.recvfrom(4096)
            ip = addr[0]
            if ip in seen:
                continue
            seen.add(ip)
            key = 171
            decrypted = bytearray()
            for byte in data:
                decrypted.append(key ^ byte)
                key = byte
            try:
                response = json.loads(decrypted.decode("utf-8", errors="replace"))
                sysinfo = response.get("system", {}).get("get_sysinfo", {})
                if sysinfo:
                    results.append((ip, sysinfo))
            except Exception:
                continue
        except socket.timeout:
            break
        except Exception:
            break
    sock.close()
    return results


# ----------------------------------------------------------------------
# BulbEntry
# ----------------------------------------------------------------------
@dataclass
class BulbEntry:
    ip: str = ""
    mac: str = ""
    band: str = "bass"
    alias: str = ""
    status: str = "idle"
    last_error: str = ""


# ----------------------------------------------------------------------
# Persistent socket connection
# ----------------------------------------------------------------------
class PersistentBulbConnection:
    """Holds a long-lived TCP socket to one bulb. Reuses it for every
    command. Reconnects automatically if the connection drops."""

    def __init__(self, ip: str):
        self.ip = ip
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        # TCP_NODELAY: send small packets immediately, don't buffer.
        # Important for keeping individual color commands snappy.
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.connect((self.ip, 9999))
        self._sock = sock

    def _close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def send_command(self, command: dict, timeout: float = 1.5) -> bool:
        with self._lock:
            payload = json.dumps(command)
            encrypted = _encrypt(payload)
            # Try once on existing socket; reconnect and retry if it fails
            for _ in range(2):
                if self._sock is None:
                    try:
                        self._connect()
                    except Exception:
                        return False
                try:
                    self._sock.settimeout(timeout)
                    self._sock.sendall(encrypted)
                    length_bytes = self._sock.recv(4)
                    if len(length_bytes) < 4:
                        self._close()
                        continue
                    length = struct.unpack(">I", length_bytes)[0]
                    received = 0
                    while received < length:
                        chunk = self._sock.recv(min(4096, length - received))
                        if not chunk:
                            break
                        received += len(chunk)
                    return True
                except (socket.error, OSError, socket.timeout):
                    self._close()
                    continue
            return False

    def set_hsv(self, hue: int, sat: int, val: int, timeout: float = 1.0) -> bool:
        cmd = {
            "smartlife.iot.smartbulb.lightingservice": {
                "transition_light_state": {
                    "ignore_default": 1,
                    "on_off": 1,
                    "hue": int(hue) % 360,
                    "saturation": max(0, min(100, int(sat))),
                    "brightness": max(1, min(100, int(val))),
                    "color_temp": 0,
                    "transition_period": 0,
                }
            }
        }
        return self.send_command(cmd, timeout)

    def close(self):
        with self._lock:
            self._close()


# ----------------------------------------------------------------------
# BulbController — one worker thread per bulb
# ----------------------------------------------------------------------
class BulbController:
    """Manages bulbs with one worker thread per bulb. Each bulb has its
    own persistent connection. Slow bulbs don't block fast ones because
    they're not sharing a single round-robin loop anymore."""

    def __init__(self, bulbs: list[BulbEntry], update_hz: float = 20.0,
                 status_callback=None):
        self.bulbs = bulbs
        self.update_hz = update_hz
        self.status_callback = status_callback

        self._threads: list[Optional[threading.Thread]] = [None] * len(bulbs)
        self._connections: list[Optional[PersistentBulbConnection]] = [None] * len(bulbs)
        self._stop_event = threading.Event()
        self._targets: list[Optional[tuple[int, int, int]]] = [None] * len(bulbs)
        self._targets_lock = threading.Lock()

    def start(self):
        if any(t is not None for t in self._threads):
            return
        self._stop_event.clear()
        for i in range(len(self.bulbs)):
            t = threading.Thread(target=self._bulb_worker, args=(i,),
                                 name=f"bulb-{i}", daemon=True)
            self._threads[i] = t
            t.start()

    def stop(self):
        self._stop_event.set()
        for t in self._threads:
            if t is not None:
                t.join(timeout=2.0)
        for conn in self._connections:
            if conn is not None:
                conn.close()
        self._threads = [None] * len(self.bulbs)
        self._connections = [None] * len(self.bulbs)

    def set_color_threadsafe(self, bulb_index: int, h: int, s: int, v: int):
        if 0 <= bulb_index < len(self._targets):
            with self._targets_lock:
                self._targets[bulb_index] = (
                    int(max(0, min(360, h))),
                    int(max(0, min(100, s))),
                    int(max(1, min(100, v))),
                )

    def _notify_status(self, index: int, status: str, err: str = ""):
        if 0 <= index < len(self.bulbs):
            self.bulbs[index].status = status
            self.bulbs[index].last_error = err
        if self.status_callback is not None:
            try:
                self.status_callback(index, status, err)
            except Exception:
                pass

    def _bulb_worker(self, i: int):
        import time as _time

        bulb = self.bulbs[i]
        if not bulb.ip:
            self._notify_status(i, "failed", "no IP")
            return

        self._notify_status(i, "connecting")
        info = get_info(bulb.ip, timeout=3.0)
        if info:
            if not bulb.alias:
                bulb.alias = info.get("alias", "Kasa bulb")
            if not bulb.mac:
                bulb.mac = info.get("mic_mac", info.get("mac", "")).lower()
            turn_on_oneshot(bulb.ip)
        else:
            self._notify_status(i, "failed", "could not reach bulb")
            return

        conn = PersistentBulbConnection(bulb.ip)
        self._connections[i] = conn
        self._notify_status(i, "ok")

        period = 1.0 / self.update_hz
        last_sent: Optional[tuple[int, int, int]] = None
        consecutive_failures = 0

        while not self._stop_event.is_set():
            cycle_start = _time.monotonic()
            with self._targets_lock:
                target = self._targets[i]

            if target is not None and target != last_sent:
                if conn.set_hsv(*target, timeout=1.0):
                    last_sent = target
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        self._notify_status(i, "failed", "lost connection")
                        consecutive_failures = 0
                        conn.close()
                        _time.sleep(0.5)
                        self._notify_status(i, "ok")

            elapsed = _time.monotonic() - cycle_start
            sleep_for = period - elapsed
            if sleep_for > 0:
                _time.sleep(sleep_for)


# ----------------------------------------------------------------------
# Compatibility wrappers
# ----------------------------------------------------------------------
def discover_lan(timeout: float = 4.0) -> list[BulbEntry]:
    found = discover(timeout=timeout)
    entries = []
    for ip, info in found:
        if is_color_bulb(info):
            entries.append(BulbEntry(
                ip=ip,
                mac=info.get("mic_mac", info.get("mac", "")).lower(),
                alias=info.get("alias", "Kasa bulb"),
            ))
    return entries


def cloud_login(username: str, password: str) -> list[BulbEntry]:
    raise NotImplementedError("Cloud login not supported in lean version.")
