"""
audio_capture.py
================

Cross-platform audio capture. Same structure as before — abstract
AudioSource with desktop and Android implementations. Returns plain
Python lists instead of numpy arrays now.
"""

from __future__ import annotations

import os
import threading


def _is_android() -> bool:
    if "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ:
        return True
    try:
        import jnius  # noqa: F401
        return True
    except Exception:
        return False


IS_ANDROID = _is_android()


class AudioSource:
    sample_rate: int = 44100
    block_size: int = 1024

    def start(self): raise NotImplementedError
    def stop(self): raise NotImplementedError
    def read(self) -> list: raise NotImplementedError


class DesktopLoopbackSource(AudioSource):
    """Captures system audio via the soundcard library."""

    def __init__(self, sample_rate: int = 44100, block_size: int = 1024,
                 device_name: str = ""):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device_name = device_name
        self._recorder = None

    def start(self):
        import soundcard as sc
        if self.device_name:
            mics = [m for m in sc.all_microphones(include_loopback=True)
                    if self.device_name.lower() in m.name.lower()]
            if not mics:
                raise RuntimeError(f"No loopback device matching '{self.device_name}'")
            mic = mics[0]
        else:
            speaker = sc.default_speaker()
            mic = sc.get_microphone(speaker.name, include_loopback=True)
        self._recorder = mic.recorder(
            samplerate=self.sample_rate, blocksize=self.block_size
        )
        self._recorder.__enter__()

    def read(self) -> list:
        data = self._recorder.record(numframes=self.block_size)
        # data is (frames, channels); mix to mono and convert to list
        if data.ndim == 2 and data.shape[1] > 1:
            return [float(sum(row) / len(row)) for row in data]
        return [float(s) for s in data.flatten()]

    def stop(self):
        if self._recorder is not None:
            try:
                self._recorder.__exit__(None, None, None)
            except Exception:
                pass
            self._recorder = None


class AndroidMicSource(AudioSource):
    """Mic capture via Android's AudioRecord through pyjnius."""

    def __init__(self, sample_rate: int = 44100, block_size: int = 1024):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._record = None
        self._java_buf = None
        self._lock = threading.Lock()

    def start(self):
        from jnius import autoclass
        AudioRecord = autoclass("android.media.AudioRecord")
        AudioFormat = autoclass("android.media.AudioFormat")
        MediaRecorder = autoclass("android.media.MediaRecorder$AudioSource")
        channel_config = AudioFormat.CHANNEL_IN_MONO
        audio_format = AudioFormat.ENCODING_PCM_16BIT
        min_buf_bytes = AudioRecord.getMinBufferSize(
            self.sample_rate, channel_config, audio_format
        )
        buf_bytes = max(min_buf_bytes * 10, self.block_size * 2 * 10)
        self._record = AudioRecord(
            MediaRecorder.MIC, self.sample_rate,
            channel_config, audio_format, buf_bytes,
        )
        self._record.startRecording()
        self._java_buf = [0] * self.block_size

    def read(self) -> list:
        if self._record is None:
            return [0.0] * self.block_size
        n = self._record.read(self._java_buf, 0, self.block_size)
        if n <= 0:
            return [0.0] * self.block_size
        return [s / 32768.0 for s in self._java_buf[:n]]

    def stop(self):
        with self._lock:
            if self._record is not None:
                try:
                    self._record.stop()
                    self._record.release()
                except Exception:
                    pass
                self._record = None


def make_default_source(sample_rate: int = 44100, block_size: int = 1024,
                        device_name: str = "") -> AudioSource:
    if IS_ANDROID:
        return AndroidMicSource(sample_rate=44100, block_size=block_size)
    return DesktopLoopbackSource(
        sample_rate=sample_rate, block_size=block_size, device_name=device_name,
    )
