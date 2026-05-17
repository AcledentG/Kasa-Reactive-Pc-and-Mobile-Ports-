"""
audio_analysis.py
=================

Audio analysis with NO numpy dependency.

Polish update: default FFT size dropped from 2048 to 1024. Pure-Python
FFT cost scales as N*log(N), so halving N roughly halves the per-frame
analysis time. Audio quality is essentially unchanged for our use case
because we're doing band averages, not picking out specific frequencies.
"""

from __future__ import annotations

import array
import cmath
import math
import time
from collections import deque
from dataclasses import dataclass, field


BAND_RANGES = {
    "bass":    (20,    180),
    "lowmid":  (180,   500),
    "mid":     (500,   2000),
    "highmid": (2000,  4500),
    "treble":  (4500,  16000),
    "vocal":   (200,   3500),
    "full":    (20,    18000),
}

BAND_ORDER = ["bass", "lowmid", "mid", "highmid", "treble", "vocal", "full"]


def _bit_reverse(n: int, bits: int) -> int:
    result = 0
    for _ in range(bits):
        result = (result << 1) | (n & 1)
        n >>= 1
    return result


def _fft(x: list) -> list:
    n = len(x)
    if n & (n - 1) != 0:
        raise ValueError("FFT size must be power of 2")
    bits = int(math.log2(n))
    out = [0j] * n
    for i in range(n):
        out[_bit_reverse(i, bits)] = complex(x[i])
    size = 2
    while size <= n:
        half = size >> 1
        w_step = cmath.exp(-2j * math.pi / size)
        for start in range(0, n, size):
            w = 1 + 0j
            for k in range(half):
                t = w * out[start + k + half]
                u = out[start + k]
                out[start + k] = u + t
                out[start + k + half] = u - t
                w *= w_step
        size <<= 1
    return out


def _rfft_magnitudes(samples: list, window: list) -> list:
    n = len(samples)
    windowed = [samples[i] * window[i] for i in range(n)]
    spectrum = _fft(windowed)
    half = n // 2 + 1
    return [abs(spectrum[i]) for i in range(half)]


def _hanning(n: int) -> list:
    return [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]


@dataclass
class BandState:
    name: str
    value: float = 0.0
    envelope: float = 0.0
    peak: float = 0.001
    history: deque = field(default_factory=lambda: deque(maxlen=60))


class AudioAnalyzer:
    def __init__(self, sample_rate: int = 44100, fft_size: int = 1024):
        # NOTE: fft_size default lowered from 2048 to 1024 for speed
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.window = _hanning(fft_size)

        bin_count = fft_size // 2 + 1
        bin_freqs = [i * sample_rate / fft_size for i in range(bin_count)]
        self.band_indices = {}
        for name, (lo, hi) in BAND_RANGES.items():
            self.band_indices[name] = [
                i for i, f in enumerate(bin_freqs) if lo <= f < hi
            ]

        self.bands = {name: BandState(name=name) for name in BAND_ORDER}
        self.attack = 0.5
        self.release = 0.08

        self._prev_spectrum: list = []
        self._flux_history = deque(maxlen=43)
        self.beat_now = False
        self._last_beat_time = 0.0
        self._beat_times = deque(maxlen=16)
        self.bpm = 0.0
        self.noise_floor = 0.0005

    def process(self, samples) -> dict:
        if hasattr(samples, "tolist"):
            samples = samples.tolist()
        else:
            samples = list(samples)
        if samples and isinstance(samples[0], (list, tuple)):
            samples = [sum(s) / len(s) for s in samples]
        n = len(samples)
        if n < self.fft_size:
            samples = samples + [0.0] * (self.fft_size - n)
        elif n > self.fft_size:
            samples = samples[-self.fft_size:]

        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        if rms < self.noise_floor:
            for b in self.bands.values():
                b.value = 0.0
                b.envelope *= (1.0 - self.release)
            self.beat_now = False
            return {name: self.bands[name].envelope for name in BAND_ORDER}

        spectrum = _rfft_magnitudes(samples, self.window)

        for name in BAND_ORDER:
            idxs = self.band_indices[name]
            if not idxs:
                continue
            energy = sum(spectrum[i] for i in idxs) / len(idxs)
            b = self.bands[name]
            if energy > b.peak:
                b.peak = energy
            else:
                b.peak = max(b.peak * 0.9995, energy, 0.001)
            normalized = min(1.0, energy / b.peak)
            b.value = normalized
            if normalized > b.envelope:
                b.envelope += (normalized - b.envelope) * self.attack
            else:
                b.envelope += (normalized - b.envelope) * self.release
            b.history.append(b.envelope)

        self._update_beat(spectrum)
        return {name: self.bands[name].envelope for name in BAND_ORDER}

    def _update_beat(self, spectrum: list):
        if not self._prev_spectrum or len(self._prev_spectrum) != len(spectrum):
            self._prev_spectrum = list(spectrum)
            self.beat_now = False
            return
        flux = sum(
            max(spectrum[i] - self._prev_spectrum[i], 0.0)
            for i in range(len(spectrum))
        )
        self._prev_spectrum = list(spectrum)
        self._flux_history.append(flux)
        if len(self._flux_history) < 10:
            self.beat_now = False
            return
        avg = sum(self._flux_history) / len(self._flux_history)
        threshold = avg * 1.5
        now = time.monotonic()
        if flux > threshold and (now - self._last_beat_time) > 0.2:
            self.beat_now = True
            self._beat_times.append(now)
            self._last_beat_time = now
            self._estimate_bpm()
        else:
            self.beat_now = False

    def _estimate_bpm(self):
        if len(self._beat_times) < 4:
            return
        intervals = [self._beat_times[i+1] - self._beat_times[i]
                     for i in range(len(self._beat_times) - 1)]
        intervals = [iv for iv in intervals if 0.25 < iv < 1.5]
        if len(intervals) < 3:
            return
        sorted_iv = sorted(intervals)
        median = sorted_iv[len(sorted_iv) // 2]
        if median > 0:
            self.bpm = 60.0 / median

    def get_levels(self) -> dict:
        return {name: self.bands[name].envelope for name in BAND_ORDER}
