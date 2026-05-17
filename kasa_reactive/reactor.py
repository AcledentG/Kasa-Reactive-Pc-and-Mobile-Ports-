"""
reactor.py
==========

The conductor. Runs on its own thread, pulling audio, analyzing,
and dispatching colors to the bulb controller.
"""

from __future__ import annotations

import threading
import time
from typing import Optional, Callable

from .audio_analysis import AudioAnalyzer, BAND_ORDER
from .audio_capture import AudioSource
from .bulb_control import BulbController
from .palettes import Palette, slot_for_bulb


class Reactor:
    def __init__(self, source: AudioSource, controller: BulbController,
                 palette: Palette, update_hz: float = 30.0):
        self.source = source
        self.controller = controller
        self.palette = palette
        self.update_hz = update_hz
        self.levels: dict = {name: 0.0 for name in BAND_ORDER}
        self.bpm: float = 0.0
        self.beat_now: bool = False
        self.on_beat: Optional[Callable[[], None]] = None
        self._analyzer: Optional[AudioAnalyzer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        if self._thread is not None:
            return
        self._stop_event.clear()
        self.source.start()
        self._analyzer = AudioAnalyzer(
            sample_rate=self.source.sample_rate, fft_size=1024,
        )
        self.controller.start()
        self._thread = threading.Thread(
            target=self._run, name="kasa-reactor", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        try: self.source.stop()
        except Exception: pass
        try: self.controller.stop()
        except Exception: pass

    def _run(self):
        period = 1.0 / self.update_hz
        next_tick = time.monotonic()
        while not self._stop_event.is_set():
            try:
                block = self.source.read()
            except Exception as e:
                print(f"[reactor] audio read error: {e}", flush=True)
                time.sleep(0.1)
                continue
            levels = self._analyzer.process(block)
            self.levels = levels
            self.bpm = self._analyzer.bpm
            self.beat_now = self._analyzer.beat_now

            for i, b in enumerate(self.controller.bulbs):
                if b.status != "ok":
                    continue
                env = levels.get(b.band, 0.0)
                hue, sat = slot_for_bulb(self.palette, i)
                val = int(5 + env * 95)
                self.controller.set_color_threadsafe(i, hue, sat, val)

            if self.beat_now and self.on_beat is not None:
                try: self.on_beat()
                except Exception: pass

            next_tick += period
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_tick = time.monotonic()
